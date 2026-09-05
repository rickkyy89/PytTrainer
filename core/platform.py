"""PC implementations of the platform services used by the core package."""

from __future__ import annotations

from pathlib import Path
import subprocess
from urllib.parse import parse_qs, urlparse

def default_base_dir() -> Path:
    """Return the application directory used by legacy PC calls."""
    return Path(__file__).resolve().parent.parent


class CredentialProviderError(Exception):
    """Raised when a credential provider cannot complete authentication."""


class PcFfmpegBackend:
    """Run the system ffmpeg binary on the PC."""

    def run(self, command: list[str], *, timeout: float):
        return subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )


class LocalCredentialsProvider:
    """Read Google credentials and OAuth token cache from an explicit directory."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or default_base_dir()).expanduser().resolve()

    @property
    def credentials_path(self) -> Path:
        return self.base_dir / "credentials.json"

    @property
    def service_account_path(self) -> Path:
        return self.base_dir / "service_account.json"

    @property
    def token_path(self) -> Path:
        return self.base_dir / "token.json"

    def _missing_credentials_error(self) -> CredentialProviderError:
        return CredentialProviderError(
            f"File 'credentials.json' non trovato nella directory base '{self.base_dir}'. "
            "Per configurare l'accesso a Google:\n"
            "1. Vai su https://console.cloud.google.com/ e crea (o seleziona) un progetto.\n"
            "2. Abilita le API 'Google Docs API' e 'Google Drive API'.\n"
            "3. Configura la schermata di consenso OAuth (tipo Esterno, aggiungendo il tuo "
            "account come utente di test se l'app non è pubblicata).\n"
            "4. Crea delle credenziali OAuth di tipo 'Applicazione desktop'.\n"
            "5. Scarica il file JSON generato e rinominalo 'credentials.json', posizionandolo "
            f"nella directory base '{self.base_dir}'.\n"
            "In alternativa, per un uso senza interazione utente, puoi creare un Service Account "
            "e salvare la relativa chiave come 'service_account.json' (i documenti generati "
            "apparterranno però al Service Account e non al tuo account personale)."
        )

    def get_credentials(self, scopes: list[str]):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        if self.service_account_path.exists():
            return service_account.Credentials.from_service_account_file(
                str(self.service_account_path), scopes=scopes
            )

        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), scopes)
            except (ValueError, OSError):
                creds = None

        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self.token_path.write_text(creds.to_json(), encoding="utf-8")
                return creds
            except RefreshError:
                self.token_path.unlink(missing_ok=True)

        if not self.credentials_path.exists():
            raise self._missing_credentials_error()
        flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), scopes)
        creds = flow.run_local_server(port=0)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def get_credentials_manual_flow(self, scopes: list[str], auth_code: str | None = None):
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.credentials_path.exists():
            raise self._missing_credentials_error()

        flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), scopes)
        flow.redirect_uri = "http://localhost"
        if auth_code is None:
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            raise CredentialProviderError(
                "Autenticazione Google richiesta in modalità manuale (nessun browser locale "
                "disponibile in questo ambiente).\n"
                f"1. Apri questo URL in un browser e autorizza l'accesso:\n{auth_url}\n"
                "2. Dopo l'autorizzazione verrai reindirizzato a un URL del tipo "
                "'http://localhost/?code=...': va bene copiarlo anche se la pagina non si carica "
                "(oppure copia solo il valore del parametro 'code').\n"
                "3. Richiama di nuovo get_credentials_manual_flow(auth_code=<code o URL copiato>) "
                "per completare il login."
            )

        code = auth_code
        if "code=" in auth_code:
            params = parse_qs(urlparse(auth_code).query)
            if "code" in params:
                code = params["code"][0]
        flow.fetch_token(code=code)
        creds = flow.credentials
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
