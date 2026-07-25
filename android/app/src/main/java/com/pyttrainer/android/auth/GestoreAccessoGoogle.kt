package com.pyttrainer.android.auth

import android.app.Application
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.pyttrainer.android.BuildConfig
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
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
import org.json.JSONException

/** Stato osservabile dell'accesso Google (Fase 7): letto da SchedaScreen e ImpostazioniScreen. */
data class StatoAccessoGoogle(
    val connesso: Boolean = false,
    /**
     * Sempre null con gli scope attuali (documents/drive.file, niente
     * openid/email): Google non restituisce un id_token da cui leggere
     * l'indirizzo. Il campo resta per mostrare un'eventuale email in futuro
     * senza dover cambiare la UI che lo consuma.
     */
    val email: String? = null,
)

/**
 * Accesso Google via AppAuth (OAuth 2.0 PKCE, client "Android": nessun
 * client secret). L'AuthState (incluso il refresh token) è persistito in
 * EncryptedSharedPreferences, così l'utente fa login una sola volta e
 * sopravvive al riavvio dell'app.
 *
 * Singleton di processo (come PythonBridge/EsitoAvvio): [inizializza] va
 * chiamato una sola volta da PytTrainerApplication.onCreate(), così sia le
 * schermate Compose sia GenerazioneDocumentoWorker (che gira fuori da
 * qualunque Activity, in un contesto WorkManager) condividono lo stesso
 * AuthState senza bisogno di dependency injection.
 *
 * Il refresh del token è interamente qui: ad android_bridge.py (tramite
 * PythonBridge) passiamo sempre e solo un access token già fresco (vedi
 * [tokenFresco]) — non esiste nessun credentials.json/token.json sul
 * telefono, la Fase 7 lo sostituisce del tutto con AppAuth.
 */
object GestoreAccessoGoogle {

    // Endpoint OAuth 2.0 di Google: fissi, non serve discovery ".well-known".
    private val CONFIGURAZIONE_SERVIZIO = AuthorizationServiceConfiguration(
        Uri.parse("https://accounts.google.com/o/oauth2/v2/auth"),
        Uri.parse("https://oauth2.googleapis.com/token"),
    )

    /**
     * Client ID OAuth di tipo "Android" (PKCE, nessun client secret) da
     * registrare in Google Cloud Console con package name
     * "com.pyttrainer.android" e impronta SHA-1 del keystore di debug
     * committato ("59:50:55:5A:D7:D4:FB:B1:43:02:8F:D5:88:25:A4:31:89:5A:A0:86",
     * vedi ImpostazioniScreen). NON è automatizzabile (richiede l'account
     * Google Cloud dell'utente): il valore vive fuori dal sorgente Kotlin, in
     * BuildConfig.CLIENT_ID_OAUTH (generato da app/build.gradle.kts a partire
     * da pyttrainer.oauth.clientId in gradle.properties o local.properties,
     * vedi android/README.md). Finché resta vuoto, [avviaAccesso] non apre
     * nemmeno il browser: fallisce subito con un messaggio chiaro (vedi
     * [clientIdConfigurato]) invece di far arrivare all'utente un errore di
     * configurazione da Google poco comprensibile.
     */
    private val CLIENT_ID = BuildConfig.CLIENT_ID_OAUTH

    /** Messaggio mostrato/sollevato quando manca il client ID OAuth (vedi [avviaAccesso]). */
    const val MESSAGGIO_CLIENT_ID_NON_CONFIGURATO =
        "Client OAuth non configurato: imposta pyttrainer.oauth.clientId in " +
            "android/gradle.properties (o android/local.properties) con il client ID " +
            "\"Android\" creato su Google Cloud Console. Istruzioni in android/README.md, " +
            "sezione \"Configurazione dell'accesso Google\"."

    /** True se un client ID OAuth è stato configurato in fase di build (vedi [MESSAGGIO_CLIENT_ID_NON_CONFIGURATO]). */
    fun clientIdConfigurato(): Boolean = CLIENT_ID.isNotBlank()

    // Deve corrispondere esattamente a manifestPlaceholders["appAuthRedirectScheme"]
    // in app/build.gradle.kts (senza quello, l'intent-filter di
    // RedirectUriReceiverActivity — dichiarato dalla libreria AppAuth stessa
    // — non si registra e il redirect dal browser non torna mai all'app).
    private const val SCHEMA_REDIRECT = "com.pyttrainer.android"
    private val REDIRECT_URI = Uri.parse("$SCHEMA_REDIRECT:/oauth2redirect")

    // Esattamente gli scope usati da google_docs_helper.SCOPES (vedi CLAUDE.md):
    // qualunque scope in più renderebbe il consenso Google più invasivo senza motivo.
    private const val SCOPE_DOCUMENTS = "https://www.googleapis.com/auth/documents"
    private const val SCOPE_DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"

    private const val PREFS_NOME = "accesso_google_secure"
    private const val CHIAVE_AUTH_STATE = "auth_state"

    private lateinit var servizioAutorizzazione: AuthorizationService
    private lateinit var preferenze: SharedPreferences
    private var authState: AuthState = AuthState()
    private var inizializzato = false

    private val _stato = MutableStateFlow(StatoAccessoGoogle())
    val stato: StateFlow<StatoAccessoGoogle> = _stato.asStateFlow()

    @Synchronized
    fun inizializza(applicazione: Application) {
        if (inizializzato) return
        inizializzato = true

        servizioAutorizzazione = AuthorizationService(applicazione)

        val chiavePrincipale = MasterKey.Builder(applicazione)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        preferenze = EncryptedSharedPreferences.create(
            applicazione,
            PREFS_NOME,
            chiavePrincipale,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )

        authState = caricaAuthState()
        aggiornaStato()
    }

    private fun caricaAuthState(): AuthState {
        val serializzato = preferenze.getString(CHIAVE_AUTH_STATE, null) ?: return AuthState()
        return try {
            AuthState.jsonDeserialize(serializzato)
        } catch (_: JSONException) {
            AuthState()
        }
    }

    private fun persistiAuthState() {
        preferenze.edit().putString(CHIAVE_AUTH_STATE, authState.jsonSerializeString()).apply()
    }

    private fun aggiornaStato() {
        _stato.value = StatoAccessoGoogle(connesso = authState.isAuthorized)
    }

    /**
     * Intent di login da lanciare con un ActivityResultLauncher (vedi
     * ImpostazioniScreen). Solleva IllegalStateException con
     * [MESSAGGIO_CLIENT_ID_NON_CONFIGURATO] se manca il client ID OAuth,
     * SENZA aprire il browser: niente crash, il chiamante mostra il
     * messaggio (es. in una Snackbar) esattamente come farebbe con un
     * qualunque altro errore di accesso.
     */
    fun avviaAccesso(lanciatore: androidx.activity.result.ActivityResultLauncher<Intent>) {
        check(clientIdConfigurato()) { MESSAGGIO_CLIENT_ID_NON_CONFIGURATO }
        val richiesta = AuthorizationRequest.Builder(
            CONFIGURAZIONE_SERVIZIO, CLIENT_ID, ResponseTypeValues.CODE, REDIRECT_URI,
        )
            .setScopes(SCOPE_DOCUMENTS, SCOPE_DRIVE_FILE)
            .setAdditionalParameters(mapOf("access_type" to "offline", "prompt" to "consent"))
            .build()
        lanciatore.launch(servizioAutorizzazione.getAuthorizationRequestIntent(richiesta))
    }

    /**
     * Completa il login a partire dall'Intent restituito dall'
     * ActivityResultLauncher usato in [avviaAccesso]: scambia il code PKCE
     * con la coppia access/refresh token e persiste il risultato.
     */
    suspend fun gestisciRispostaAccesso(dati: Intent?): Result<Unit> {
        val risposta = dati?.let(AuthorizationResponse::fromIntent)
        val eccezioneRisposta = dati?.let(AuthorizationException::fromIntent)
        if (risposta == null) {
            return Result.failure(eccezioneRisposta ?: IllegalStateException("Accesso annullato o risposta non valida."))
        }
        authState.update(risposta, eccezioneRisposta)

        return suspendCancellableCoroutine { continuazione ->
            servizioAutorizzazione.performTokenRequest(risposta.createTokenExchangeRequest()) { rispostaToken, eccezioneToken ->
                authState.update(rispostaToken, eccezioneToken)
                persistiAuthState()
                aggiornaStato()
                if (eccezioneToken != null) {
                    continuazione.resume(Result.failure(eccezioneToken))
                } else {
                    continuazione.resume(Result.success(Unit))
                }
            }
        }
    }

    /**
     * Access token sempre fresco: rinnovato automaticamente se AuthState lo
     * ritiene scaduto (performActionWithFreshTokens). È l'unico input Google
     * che attraversa il bridge Python — vedi android_bridge._servizi_google_da_token,
     * che costruisce Credentials(token=access_token) senza refresh token: il
     * refresh resta interamente responsabilità di questa funzione.
     */
    suspend fun tokenFresco(): String {
        check(authState.isAuthorized) { "Accesso Google non ancora effettuato: vai in Impostazioni." }
        return suspendCancellableCoroutine { continuazione ->
            authState.performActionWithFreshTokens(servizioAutorizzazione) { accessToken, _, eccezione ->
                persistiAuthState()
                aggiornaStato()
                when {
                    eccezione != null -> continuazione.resumeWithException(eccezione)
                    accessToken.isNullOrBlank() ->
                        continuazione.resumeWithException(IllegalStateException("Token di accesso Google non disponibile."))
                    else -> continuazione.resume(accessToken)
                }
            }
        }
    }

    /**
     * Forza il prossimo [tokenFresco] a rinnovare il token anche se
     * AuthState lo considera ancora valido: usato da GenerazioneDocumentoWorker
     * quando Google rifiuta un token che avremmo creduto valido (orologio
     * del device sfasato, revoca lato server, ...) — il fallimento arriva
     * dal bridge come errore "DOCS" con un 401 nel messaggio, non come
     * errore "AUTH" (vedi commento nel worker).
     */
    fun forzaRinnovoToken() {
        authState.needsTokenRefresh = true
    }

    fun esci() {
        authState = AuthState()
        if (::preferenze.isInitialized) persistiAuthState()
        aggiornaStato()
    }
}
