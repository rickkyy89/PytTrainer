package com.pyttrainer.android.lavoro

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.pyttrainer.android.R
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.dati.RisultatoGenerazioneDocumento
import com.pyttrainer.android.python.ErroreScheda
import com.pyttrainer.android.python.PythonBridge
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

/**
 * Genera il Google Doc in background (Fase 7): un CoroutineWorker in primo
 * piano (notifica obbligatoria per un lavoro che può durare minuti — un
 * esercizio alla volta, upload di due immagini su Drive per esercizio) che
 * chiama PythonBridge.generaDocumento() E in parallelo fa polling di
 * PythonBridge.statoGenerazione() per pubblicare l'avanzamento: la chiamata
 * a generaDocumento() è UNA sola sospensione lunga (create_workout_document
 * cicla tutti gli esercizi lato Python senza callback incrementali verso
 * Kotlin), quindi l'unico modo di osservare il progresso "dall'esterno" è
 * rileggere lo stato.json che create_workout_document scrive dopo OGNI
 * esercizio inserito.
 *
 * Se la generazione riparte da un'interruzione precedente (stesso
 * state_path), create_workout_document salta da sé gli esercizi già
 * presenti nello stato: qui non c'è nessuna logica di ripresa da
 * implementare, basta rilanciare il worker con lo stesso stato.
 */
class GenerazioneDocumentoWorker(
    contesto: Context,
    parametri: WorkerParameters,
) : CoroutineWorker(contesto, parametri) {

    private val json = Json { ignoreUnknownKeys = true }

    override suspend fun doWork(): Result {
        val eserciziJson = inputData.getString(KEY_ESERCIZI_JSON)
        val titolo = inputData.getString(KEY_TITOLO)
        val statePath = inputData.getString(KEY_STATE_PATH) ?: ""

        if (eserciziJson.isNullOrBlank() || titolo.isNullOrBlank()) {
            return Result.failure(workDataOf(KEY_ERRORE to "Dati di generazione mancanti."))
        }

        val esercizi: List<Esercizio> = try {
            json.decodeFromString<List<Esercizio>>(eserciziJson)
        } catch (eccezione: Exception) {
            return Result.failure(workDataOf(KEY_ERRORE to "Elenco esercizi non leggibile: ${eccezione.message}"))
        }

        setForeground(creaInfoPrimoPiano(0, esercizi.size))

        return try {
            coroutineScope {
                val pollingAvanzamento = launch { pollaAvanzamento(statePath, esercizi.size) }
                val risultato = try {
                    generaConRitentativoToken(esercizi, titolo, statePath)
                } finally {
                    pollingAvanzamento.cancel()
                }
                risultato.fold(
                    onSuccess = { esito ->
                        Result.success(
                            workDataOf(
                                KEY_URL to esito.url,
                                KEY_DOCUMENT_ID to esito.documentId,
                                KEY_PROGRESSO_FATTI to esercizi.size,
                                KEY_PROGRESSO_TOTALE to esercizi.size,
                            )
                        )
                    },
                    onFailure = { errore -> Result.failure(workDataOf(KEY_ERRORE to (errore.message ?: "Errore sconosciuto."))) },
                )
            }
        } catch (eccezione: Exception) {
            Result.failure(workDataOf(KEY_ERRORE to (eccezione.message ?: "Errore sconosciuto.")))
        }
    }

    /**
     * Chiama PythonBridge.generaDocumento() con un access token fresco. Se
     * fallisce per token scaduto rinnova e riprova UNA volta: la generazione
     * riprende dallo stato.json senza rifare il lavoro già fatto (nessuna
     * modifica a google_docs_helper.py, è già resumibile di suo).
     *
     * Nota sulla condizione di ritentativo: la documentazione del bridge
     * (vedi PythonBridge.ErroreScheda.Autenticazione) prevede un codice
     * "AUTH" per le credenziali scadute, ma su Android
     * android_bridge._servizi_google_da_token costruisce le Credentials col
     * solo access token (senza expiry né refresh token): un token scaduto
     * arriva quindi alle API Google che rispondono 401, la libreria lo
     * incapsula come HttpError e google_docs_helper lo rilancia come
     * GoogleDocsError ("DOCS"), non GoogleAuthError. Per coprire ENTRAMBI i
     * casi (quello documentato e quello osservabile davvero) si ritenta sia
     * su ErroreScheda.Autenticazione sia su un ErroreScheda.Documento il cui
     * messaggio somiglia a un problema di token.
     */
    private suspend fun generaConRitentativoToken(
        esercizi: List<Esercizio>,
        titolo: String,
        statePath: String,
    ): kotlin.Result<RisultatoGenerazioneDocumento> {
        var tentativi = 0
        while (true) {
            val token = try {
                GestoreAccessoGoogle.tokenFresco()
            } catch (eccezione: Exception) {
                return kotlin.Result.failure(eccezione)
            }
            val esito = PythonBridge.generaDocumento(esercizi, titolo, token, statePath)
            val errore = esito.exceptionOrNull()
            val riprovabile = tentativi < 1 && errore != null && sembraTokenScaduto(errore)
            if (esito.isSuccess || !riprovabile) return esito
            tentativi++
            GestoreAccessoGoogle.forzaRinnovoToken()
        }
    }

    private fun sembraTokenScaduto(errore: Throwable): Boolean {
        if (errore is ErroreScheda.Autenticazione) return true
        if (errore !is ErroreScheda.Documento) return false
        val messaggio = errore.messaggio.lowercase()
        return listOf("401", "unauthenticated", "invalid_grant", "invalid credentials", "unauthorized")
            .any { messaggio.contains(it) }
    }

    private suspend fun pollaAvanzamento(statePath: String, totale: Int) {
        if (statePath.isBlank()) return
        while (currentCoroutineContext().isActive) {
            PythonBridge.statoGenerazione(statePath).onSuccess { stato ->
                val fatti = stato?.esercizi?.size ?: 0
                setProgress(workDataOf(KEY_PROGRESSO_FATTI to fatti, KEY_PROGRESSO_TOTALE to totale))
                setForeground(creaInfoPrimoPiano(fatti, totale))
            }
            delay(1_000)
        }
    }

    private fun creaInfoPrimoPiano(fatti: Int, totale: Int): ForegroundInfo {
        val notifica = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setContentTitle(applicationContext.getString(R.string.notifica_generazione_titolo))
            .setContentText(applicationContext.getString(R.string.notifica_generazione_testo, fatti, totale))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .setProgress(totale.coerceAtLeast(1), fatti, totale == 0)
            .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(NOTIFICATION_ID, notifica, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(NOTIFICATION_ID, notifica)
        }
    }

    companion object {
        const val KEY_ESERCIZI_JSON = "esercizi_json"
        const val KEY_TITOLO = "titolo"
        const val KEY_STATE_PATH = "state_path"
        const val KEY_URL = "url"
        const val KEY_DOCUMENT_ID = "document_id"
        const val KEY_ERRORE = "errore"
        const val KEY_PROGRESSO_FATTI = "progresso_fatti"
        const val KEY_PROGRESSO_TOTALE = "progresso_totale"

        const val CHANNEL_ID = "generazione_documento"
        private const val NOTIFICATION_ID = 4210

        /** Da chiamare una sola volta da PytTrainerApplication.onCreate(): il canale va creato prima di setForeground(). */
        fun creaCanaleNotifica(contesto: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val canale = NotificationChannel(
                CHANNEL_ID,
                contesto.getString(R.string.notifica_canale_generazione_nome),
                NotificationManager.IMPORTANCE_LOW,
            )
            val gestoreNotifiche = contesto.getSystemService(NotificationManager::class.java)
            gestoreNotifiche?.createNotificationChannel(canale)
        }

        /** JSON del payload esercizi da passare via workDataOf(KEY_ESERCIZI_JSON to ...). */
        fun serializzaEsercizi(esercizi: List<Esercizio>): String = Json.encodeToString(esercizi)
    }
}
