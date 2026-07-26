package com.pyttrainer.android.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import net.openid.appauth.AuthState

private const val TAG = "ArchivioToken"
private const val NOME_FILE_PREFERENZE = "pyttrainer_auth_prefs"
private const val CHIAVE_AUTH_STATE = "auth_state_json"

/**
 * Persistenza dello stato di autenticazione Google (AuthState di AppAuth,
 * serializzato con jsonSerializeString()). Dentro c'è il refresh token: a
 * differenza dell'access token (vive circa un'ora ed è comunque revocabile),
 * il refresh token è una credenziale di lunga durata che resta valida finché
 * l'utente non la revoca esplicitamente da myaccount.google.com. Metterla in
 * SharedPreferences normali significherebbe lasciarla leggibile in chiaro a
 * chiunque ottenga accesso al filesystem dell'app (device rootato, backup
 * ADB non cifrato, ecc.): EncryptedSharedPreferences cifra sia chiavi sia
 * valori con una master key custodita nell'Android Keystore, che non è mai
 * esportabile dal chip di sicurezza del device.
 */
class ArchivioToken(contesto: Context) {

    /**
     * null se l'inizializzazione del keystore fallisce (es. dopo un
     * ripristino del device su hardware diverso, che invalida le chiavi
     * legate al chip precedente): in quel caso l'archivio si comporta come
     * sempre vuoto invece di far crashare l'app, l'utente rifà semplicemente
     * il login.
     */
    private val preferenze: SharedPreferences? = try {
        val masterKey = MasterKey.Builder(contesto)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            contesto,
            NOME_FILE_PREFERENZE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (eccezione: Exception) {
        Log.w(TAG, "EncryptedSharedPreferences non inizializzabile, si riparte da non autenticato", eccezione)
        null
    }

    /** AuthState salvato, o uno stato vuoto (non autorizzato) se assente, illeggibile o corrotto. */
    fun leggi(): AuthState {
        val json = try {
            preferenze?.getString(CHIAVE_AUTH_STATE, null)
        } catch (eccezione: Exception) {
            // Dati presenti ma non decifrabili (keystore invalidato dopo il
            // salvataggio): stesso trattamento del caso "assente".
            Log.w(TAG, "Stato di autenticazione non decifrabile, si riparte da non autenticato", eccezione)
            null
        }
        if (json.isNullOrBlank()) return AuthState()
        return try {
            AuthState.jsonDeserialize(json)
        } catch (eccezione: Exception) {
            Log.w(TAG, "Stato di autenticazione corrotto, si riparte da non autenticato", eccezione)
            AuthState()
        }
    }

    fun salva(authState: AuthState) {
        try {
            preferenze?.edit()?.putString(CHIAVE_AUTH_STATE, authState.jsonSerializeString())?.apply()
        } catch (eccezione: Exception) {
            Log.w(TAG, "Impossibile salvare lo stato di autenticazione", eccezione)
        }
    }

    fun cancella() {
        try {
            preferenze?.edit()?.remove(CHIAVE_AUTH_STATE)?.apply()
        } catch (eccezione: Exception) {
            Log.w(TAG, "Impossibile cancellare lo stato di autenticazione", eccezione)
        }
    }
}
