package com.pyttrainer.android.auth

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.pyttrainer.android.BuildConfig
import kotlin.coroutines.resume
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import net.openid.appauth.AuthState
import net.openid.appauth.AuthorizationException
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues

/**
 * Endpoint OAuth di Google hardcoded invece che scaricati dal discovery
 * document (https://accounts.google.com/.well-known/openid-configuration):
 * sono stabili da anni, e risparmiare quel round-trip di rete evita che
 * l'utente aspetti un fetch extra solo per scoprire due URL che non
 * cambiano mai tra un login e l'altro.
 */
private val CONFIGURAZIONE_SERVIZIO_GOOGLE = AuthorizationServiceConfiguration(
    Uri.parse("https://accounts.google.com/o/oauth2/v2/auth"),
    Uri.parse("https://oauth2.googleapis.com/token"),
)

/**
 * Scope richiesti al login: DEVONO combaciare ESATTAMENTE con SCOPES in
 * ../google_docs_helper.py, perché il token ottenuto qui su Android è lo
 * stesso che genera_documento() passa a google-api-python-client lato
 * Python. Uno scope in meno qui farebbe fallire le chiamate Docs/Drive con
 * un 403 invece che con un errore di login più comprensibile.
 */
private val SCOPE_GOOGLE_DOCS = listOf(
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)

/**
 * Incapsula il login Google via AppAuth (OAuth 2.0 + PKCE S256, che AppAuth
 * applica di default: i client OAuth di tipo "Android" non hanno un client
 * secret, quindi non va aggiunto nessuno). Un'unica istanza vive per tutta
 * la vita di SchedaViewModel (Activity-scoped, vedi SchedaViewModel.kt): un
 * solo AuthorizationService viene tenuto aperto invece di crearne/chiuderne
 * uno per ogni singola operazione, dato che più chiamate ravvicinate (login
 * seguito subito da un refresh per la generazione del documento) sono il
 * caso comune. [chiudi] va invocato da onCleared() del ViewModel che
 * possiede questa istanza.
 */
class GestoreAccessoGoogle(contesto: Context) {

    private val archivio = ArchivioToken(contesto)
    private val servizio = AuthorizationService(contesto)

    private var authState: AuthState = archivio.leggi()

    private val _connesso = MutableStateFlow(authState.isAuthorized)
    val connesso: StateFlow<Boolean> = _connesso.asStateFlow()

    /** false se manca il client OAuth nella build: la UI deve spiegarlo invece di aprire un browser destinato a fallire. */
    fun configurato(): Boolean = BuildConfig.OAUTH_CLIENT_ID.isNotBlank()

    fun intentDiAccesso(): Intent {
        val richiesta = AuthorizationRequest.Builder(
            CONFIGURAZIONE_SERVIZIO_GOOGLE,
            BuildConfig.OAUTH_CLIENT_ID,
            ResponseTypeValues.CODE,
            Uri.parse(BuildConfig.OAUTH_REDIRECT_URI),
        )
            .setScopes(SCOPE_GOOGLE_DOCS)
            // access_type=offline + prompt=consent: senza questi due
            // parametri Google rilascia il refresh token SOLO alla primissima
            // autorizzazione di sempre per quella coppia app+account. Un
            // utente che avesse già autorizzato l'app in passato (anche su
            // un altro device, o prima di una disinstallazione) otterrebbe
            // altrimenti un access token senza refresh token, e dovrebbe
            // rifare login ogni ora invece che una volta sola.
            .setAdditionalParameters(mapOf("access_type" to "offline", "prompt" to "consent"))
            .build()
        return servizio.getAuthorizationRequestIntent(richiesta)
    }

    /** Elabora l'Intent di ritorno dal browser e scambia il codice di autorizzazione con i token. */
    suspend fun completaAccesso(datiRisposta: Intent): Result<Unit> {
        val risposta = AuthorizationResponse.fromIntent(datiRisposta)
        val eccezioneAutorizzazione = AuthorizationException.fromIntent(datiRisposta)
        // Uscita anticipata PRIMA di toccare authState: AuthState.update()
        // pretende che esattamente uno tra risposta ed eccezione sia non-null
        // (checkArgument interno) e solleverebbe IllegalArgumentException se
        // arrivasse un Intent senza né l'una né l'altra — un'eccezione dentro
        // una coroutine, quindi un crash dell'app invece di un errore
        // mostrato all'utente.
        if (risposta == null) {
            return Result.failure(
                Exception(eccezioneAutorizzazione?.errorDescription ?: "Accesso Google annullato o non riuscito.")
            )
        }
        authState.update(risposta, eccezioneAutorizzazione)
        return suspendCancellableCoroutine { continuazione ->
            servizio.performTokenRequest(risposta.createTokenExchangeRequest()) { rispostaToken, eccezioneToken ->
                authState.update(rispostaToken, eccezioneToken)
                archivio.salva(authState)
                _connesso.value = authState.isAuthorized
                if (eccezioneToken != null || rispostaToken == null) {
                    continuazione.resume(
                        Result.failure(
                            Exception(eccezioneToken?.errorDescription ?: "Scambio del codice di accesso non riuscito.")
                        )
                    )
                } else {
                    continuazione.resume(Result.success(Unit))
                }
            }
        }
    }

    /**
     * Access token valido, rinnovandolo se scaduto (performActionWithFreshTokens
     * lo fa in automatico solo se necessario, altrimenti restituisce subito
     * quello corrente).
     */
    suspend fun accessTokenFresco(): Result<String> {
        if (!authState.isAuthorized) {
            return Result.failure(
                Exception("Nessun account Google collegato: usa \"Collega account Google\" prima di generare il documento.")
            )
        }
        return suspendCancellableCoroutine { continuazione ->
            authState.performActionWithFreshTokens(servizio) { accessToken, _, eccezioneToken ->
                if (eccezioneToken != null) {
                    // Un refresh token rifiutato (revocato dall'utente da
                    // myaccount.google.com, o scaduto per inattività
                    // prolungata) non torna MAI più valido: tenerlo salvato
                    // bloccherebbe l'utente in un limbo in cui ogni tentativo
                    // fallisce sempre allo stesso modo, senza che rifare
                    // login risolva finché lo stato vecchio non viene tolto.
                    archivio.cancella()
                    authState = AuthState()
                    _connesso.value = false
                    continuazione.resume(
                        Result.failure(Exception("Sessione Google scaduta o revocata: collega di nuovo l'account."))
                    )
                } else if (accessToken == null) {
                    continuazione.resume(Result.failure(Exception("Impossibile ottenere un token di accesso Google valido.")))
                } else {
                    archivio.salva(authState) // il refresh può aver aggiornato l'access token salvato.
                    continuazione.resume(Result.success(accessToken))
                }
            }
        }
    }

    fun disconnetti() {
        archivio.cancella()
        authState = AuthState()
        _connesso.value = false
    }

    /** Da chiamare in onCleared() del ViewModel proprietario: vedi il commento sulla classe. */
    fun chiudi() {
        servizio.dispose()
    }
}
