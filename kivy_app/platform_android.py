"""Android-specific Google credential adapters.

This module remains importable on the PC: pyjnius is loaded only when the
production bridge is instantiated on Android.
"""

from __future__ import annotations

from google.oauth2.credentials import Credentials

from core.platform import CredentialProviderError


class AndroidCredentialProvider:
    """Expose the access token obtained by the native Google authorization flow."""

    def __init__(self, bridge):
        self._bridge = bridge

    def start_authorization(self) -> None:
        """Start the native consent flow before a Drive request needs its token."""
        self._bridge.start_authorization()

    def get_credentials(self, scopes: list[str]) -> Credentials:
        token = self._bridge.get_access_token()
        if not isinstance(token, str) or not token.strip():
            status = self._bridge.get_status()
            raise CredentialProviderError(
                "Autorizzazione Google Android non disponibile. "
                "Accedi con Google e completa il consenso prima di usare Drive "
                f"(stato nativo: {status or 'sconosciuto'})."
            )
        return Credentials(token=token, scopes=scopes)


class PyjniusGoogleBridge:
    """Production adapter for the Java bridge, loaded only on Android."""

    def __init__(self):
        from jnius import autoclass

        self._activity = autoclass("org.kivy.android.PythonActivity").mActivity
        self._bridge = autoclass("org.ptt.pyTrainer.GoogleBridge")

    def start_authorization(self) -> None:
        self._bridge.startAuthorization(self._activity)

    def get_access_token(self) -> str:
        return self._bridge.getAccessToken()

    def get_status(self) -> str:
        return self._bridge.getStatus()
