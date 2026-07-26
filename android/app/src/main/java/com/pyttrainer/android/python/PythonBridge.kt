package com.pyttrainer.android.python

import android.util.Log
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.dati.InfoVideo
import com.pyttrainer.android.dati.RisultatoAggiornaMedia
import com.pyttrainer.android.dati.RisultatoAutoEstrai
import com.pyttrainer.android.dati.RisultatoCaricaScheda
import com.pyttrainer.android.dati.RisultatoCercaVideo
import com.pyttrainer.android.dati.RisultatoGenerazioneDocumento
import com.pyttrainer.android.dati.StatoGenerazione
import com.pyttrainer.android.video.EstrattoreFrameNativo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

private const val TAG = "PythonBridge"

/**
 * Errore tipizzato lato Kotlin, mappato 1:1 dai codici dell'envelope di
 * errore restituito da android_bridge.risposta_json() ("VIDEO_SEARCH",
 * "FRAME", "AUTH", "DOCS", "SCHEDA", "VALORE", "IGNOTO"). Estende Exception
 * così da poter essere il fallimento di un Result<T> senza wrapping ulteriore.
 */
sealed class ErroreScheda(val messaggio: String) : Exception(messaggio) {

    /** VIDEO_SEARCH — video_helper.VideoSearchError: ricerca/risoluzione YouTube fallita. */
    class RicercaVideo(messaggio: String) : ErroreScheda(messaggio)

    /** FRAME — video_helper.FrameExtractionError: estrazione frame (nativa o ffmpeg) fallita. */
    class Frame(messaggio: String) : ErroreScheda(messaggio)

    /** AUTH — google_docs_helper.GoogleAuthError: credenziali/token Google mancanti o non validi. */
    class Autenticazione(messaggio: String) : ErroreScheda(messaggio)

    /** DOCS — google_docs_helper.GoogleDocsError: chiamata alle API Docs/Drive fallita. */
    class Documento(messaggio: String) : ErroreScheda(messaggio)

    /** SCHEDA — scheda_file.SchedaFileError: bundle .scheda mancante/corrotto/non valido. */
    class Scheda(messaggio: String) : ErroreScheda(messaggio)

    /** VALORE — ValueError: input non valido (manifest CSV malformato, parametro fuori range, ...). */
    class Valore(messaggio: String) : ErroreScheda(messaggio)

    /** IGNOTO — qualunque altra eccezione non prevista dalla tabella dei codici. */
    class Ignoto(messaggio: String) : ErroreScheda(messaggio)

    companion object {
        /** Mapping dal codice dell'envelope alla sottoclasse corrispondente. */
        fun daCodice(codice: String, messaggio: String): ErroreScheda = when (codice) {
            "VIDEO_SEARCH" -> RicercaVideo(messaggio)
            "FRAME" -> Frame(messaggio)
            "AUTH" -> Autenticazione(messaggio)
            "DOCS" -> Documento(messaggio)
            "SCHEDA" -> Scheda(messaggio)
            "VALORE" -> Valore(messaggio)
            else -> Ignoto(messaggio)
        }
    }
}

/**
 * Oggetto singleton che incapsula il modulo Python android_bridge.py.
 * Ogni funzione pubblica è "suspend", gira su Dispatchers.IO (le chiamate
 * Chaquopy sono sincrone e possono bloccare per rete/IO su file) e restituisce
 * un Result<T>: mai un'eccezione non gestita verso il chiamante Compose,
 * mai un oggetto Python complesso che attraversa il confine (solo stringhe/
 * numeri in ingresso, JSON decodificato in DTO @Serializable in uscita).
 */
object PythonBridge {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    private val modulo: PyObject by lazy {
        Python.getInstance().getModule("android_bridge")
    }

    // ------------------------------------------------------------------
    // Meccanismo generico di chiamata + decodifica dell'envelope
    // ------------------------------------------------------------------

    /**
     * Invoca 'nomeFunzione' su android_bridge passando 'args' così come sono
     * (Chaquopy converte automaticamente String/Int/Double/Boolean/null e gli
     * oggetti Kotlin passati per riferimento, es. EstrattoreFrameNativo).
     * Decodifica l'envelope {"ok":..,"dati":..} / {"ok":false,"codice":..,
     * "messaggio":..} e restituisce Result.success/failure di conseguenza.
     * Qualunque eccezione imprevista (compresa una risposta non-JSON, che
     * non dovrebbe mai accadere visto che risposta_json() la garantisce
     * sempre) diventa un ErroreScheda.Ignoto invece di propagare.
     */
    private suspend fun <T> chiama(
        nomeFunzione: String,
        vararg args: Any?,
        decodifica: (JsonElement) -> T,
    ): Result<T> = withContext(Dispatchers.IO) {
        try {
            val rispostaGrezza = modulo.callAttr(nomeFunzione, *args).toString()
            val busta = json.parseToJsonElement(rispostaGrezza).jsonObject
            val ok = busta["ok"]?.jsonPrimitive?.boolean ?: false
            if (ok) {
                Result.success(decodifica(busta["dati"] ?: JsonNull))
            } else {
                val codice = busta["codice"]?.jsonPrimitive?.contentOrNull ?: "IGNOTO"
                val messaggio = busta["messaggio"]?.jsonPrimitive?.contentOrNull
                    ?: "Errore sconosciuto restituito dal modulo Python."
                // Un errore restituito da Python nell'envelope NON è un'eccezione,
                // quindi senza questa riga non lascerebbe alcuna traccia: l'unico
                // posto in cui comparirebbe è una Snackbar che sparisce dopo pochi
                // secondi. Per operazioni lunghe (generazione del documento, che
                // dura minuti) è facilissimo perdersela, e senza log non resta
                // nulla da diagnosticare.
                Log.w(TAG, "'$nomeFunzione' ha restituito un errore [$codice]: $messaggio")
                Result.failure(ErroreScheda.daCodice(codice, messaggio))
            }
        } catch (eccezione: Exception) {
            Log.e(TAG, "Chiamata a '$nomeFunzione' fallita", eccezione)
            Result.failure(
                ErroreScheda.Ignoto(
                    "Errore di comunicazione con il modulo Python ('$nomeFunzione'): ${eccezione.message}"
                )
            )
        }
    }

    /**
     * Variante "grezza": restituisce l'intero envelope JSON testuale così
     * com'è, senza decodificarlo né mapparne gli errori. Usata solo dalla
     * schermata di verifica del cablaggio (MainActivity), dove l'obiettivo è
     * mostrare la risposta grezza per dimostrare che il giro Kotlin -> Python
     * -> Kotlin funziona, non consumarla in un DTO tipizzato.
     *
     * Cattura comunque qualunque eccezione (es. nome funzione inesistente, un
     * errore che risposta_json() non potrebbe intercettare perché avvenuto
     * prima di entrare nella funzione decorata) e la trasforma in un envelope
     * di errore testuale equivalente, così una chiamata da un Button.onClick
     * senza try/catch non può mai far crashare l'app.
     */
    suspend fun chiamaGrezza(nomeFunzione: String, vararg args: Any?): String =
        withContext(Dispatchers.IO) {
            try {
                modulo.callAttr(nomeFunzione, *args).toString()
            } catch (eccezione: Exception) {
                Log.e(TAG, "Chiamata grezza a '$nomeFunzione' fallita", eccezione)
                """{"ok": false, "codice": "IGNOTO", "messaggio": "${eccezione.message}"}"""
            }
        }

    // ------------------------------------------------------------------
    // Scheda (.scheda) e CSV
    // ------------------------------------------------------------------

    suspend fun carica(percorsoBundle: String, cartellaLavoro: String = ""): Result<RisultatoCaricaScheda> =
        chiama("carica", percorsoBundle, cartellaLavoro) { json.decodeFromJsonElement<RisultatoCaricaScheda>(it) }

    suspend fun salva(esercizi: List<Esercizio>, percorsoBundle: String, statePath: String = ""): Result<Unit> =
        chiama("salva", json.encodeToString(esercizi), percorsoBundle, statePath) { }

    suspend fun importaCsv(percorso: String): Result<List<Esercizio>> =
        chiama("importa_csv", percorso) { json.decodeFromJsonElement<List<Esercizio>>(it) }

    suspend fun esportaCsv(esercizi: List<Esercizio>, percorso: String): Result<Unit> =
        chiama("esporta_csv", json.encodeToString(esercizi), percorso) { }

    suspend fun cartellaFrames(cartellaLavoro: String): Result<String> =
        chiama("cartella_frames", cartellaLavoro) { it.jsonPrimitive.content }

    suspend fun percorsoStato(cartellaLavoro: String): Result<String> =
        chiama("percorso_stato", cartellaLavoro) { it.jsonPrimitive.content }

    suspend fun cartellaLavoroPerBundle(percorso: String): Result<String> =
        chiama("cartella_lavoro_per_bundle", percorso) { it.jsonPrimitive.content }

    /** tipo deve essere "start" o "finish" (vedi android_bridge.percorso_frame). */
    suspend fun percorsoFrame(cartellaLavoro: String, nomeEsercizio: String, tipo: String): Result<String> =
        chiama("percorso_frame", cartellaLavoro, nomeEsercizio, tipo) { it.jsonPrimitive.content }

    // ------------------------------------------------------------------
    // Ricerca video / estrazione frame
    // ------------------------------------------------------------------

    suspend fun cercaVideo(nome: String, maxResults: Int = 3): Result<RisultatoCercaVideo> =
        chiama("cerca_video", nome, maxResults) { json.decodeFromJsonElement<RisultatoCercaVideo>(it) }

    suspend fun infoVideo(url: String): Result<InfoVideo> =
        chiama("info_video", url) { json.decodeFromJsonElement<InfoVideo>(it) }

    suspend fun streamUrl(url: String): Result<String> =
        chiama("stream_url", url) { it.jsonPrimitive.content }

    suspend fun autoEstrai(esercizio: Esercizio, outputDir: String): Result<RisultatoAutoEstrai> =
        chiama("auto_estrai", json.encodeToString(esercizio), outputDir) {
            json.decodeFromJsonElement<RisultatoAutoEstrai>(it)
        }

    /**
     * Ritaglia il frame in place riusando video_helper.crop_frame() (Pillow è
     * tra le dipendenze Chaquopy): stessa matematica e stessa qualità JPEG
     * del desktop, invece di riscrivere il ritaglio con android.graphics.Bitmap
     * e rischiare immagini diverse tra PC e telefono.
     *
     * Al primo ritaglio salva l'originale accanto al frame, così
     * [ripristinaOriginale] può annullare l'operazione. Per l'anteprima live
     * mentre l'utente muove gli slider usa invece [boxRitaglio], che è pura
     * matematica e non tocca il file.
     */
    suspend fun ritaglia(percorso: String, sinistra: Double, alto: Double, destra: Double, basso: Double): Result<String> =
        chiama("ritaglia", percorso, sinistra, alto, destra, basso) { it.jsonPrimitive.content }

    /** Riporta il frame all'originale salvato prima del primo ritaglio. */
    suspend fun ripristinaOriginale(percorso: String): Result<String> =
        chiama("ripristina_originale", percorso) { it.jsonPrimitive.content }

    /** Indica se esiste l'originale pre-ritaglio, per abilitare il comando di ripristino. */
    suspend fun haBackupOriginale(percorso: String): Result<Boolean> =
        chiama("ha_backup_originale", percorso) { it.jsonPrimitive.boolean }

    /** Box di ritaglio in pixel [sinistra, alto, destra, basso], pura matematica (nessuna dipendenza Pillow). */
    suspend fun boxRitaglio(
        larghezza: Int,
        altezza: Int,
        sinistra: Double,
        alto: Double,
        destra: Double,
        basso: Double,
    ): Result<List<Int>> =
        chiama("box_ritaglio_json", larghezza, altezza, sinistra, alto, destra, basso) {
            json.decodeFromJsonElement<List<Int>>(it)
        }

    /**
     * Registra il backend nativo di estrazione frame (sostituisce ffmpeg).
     * Chiamata UNA sola volta da PytTrainerApplication.onCreate(), prima che
     * qualunque schermata possa invocare estrazioni di frame: per questo non
     * è "suspend" (va completata sincronamente prima che l'app sia pronta) e
     * restituisce l'envelope JSON grezzo invece di un Result — un fallimento
     * qui non blocca l'avvio dell'app (viene solo loggato e mostrato nella
     * schermata di verifica): si tradurrebbe più avanti in un normale errore
     * FRAME quando si prova davvero a estrarre un frame.
     */
    fun registraBackendFrameNativo(estrattore: EstrattoreFrameNativo): String {
        val rispostaGrezza = modulo.callAttr("registra_backend_frame", estrattore).toString()
        Log.i(TAG, "registra_backend_frame -> $rispostaGrezza")
        return rispostaGrezza
    }

    // ------------------------------------------------------------------
    // Google Docs
    // ------------------------------------------------------------------

    suspend fun generaDocumento(
        esercizi: List<Esercizio>,
        titolo: String,
        accessToken: String,
        statePath: String = "",
    ): Result<RisultatoGenerazioneDocumento> =
        chiama("genera_documento", json.encodeToString(esercizi), titolo, accessToken, statePath) {
            json.decodeFromJsonElement<RisultatoGenerazioneDocumento>(it)
        }

    suspend fun aggiornaMedia(
        docId: String,
        nomeEsercizio: String,
        videoUrl: String,
        tsStart: Double?,
        tsFinish: Double?,
        accessToken: String,
        statePath: String,
        outputDir: String,
    ): Result<RisultatoAggiornaMedia> =
        chiama(
            "aggiorna_media", docId, nomeEsercizio, videoUrl, tsStart, tsFinish, accessToken, statePath, outputDir
        ) { json.decodeFromJsonElement<RisultatoAggiornaMedia>(it) }

    suspend fun statoGenerazione(statePath: String): Result<StatoGenerazione?> =
        chiama("stato_generazione", statePath) {
            if (it is JsonNull) null else json.decodeFromJsonElement<StatoGenerazione>(it)
        }

    // ------------------------------------------------------------------
    // Diagnostica
    // ------------------------------------------------------------------

    suspend fun versionePython(): Result<String> =
        chiama("versione_python") { it.jsonPrimitive.content }
}
