package com.pyttrainer.android.ui.esercizio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.dati.VideoScartato
import com.pyttrainer.android.dati.VideoYoutube
import com.pyttrainer.android.python.PythonBridge
import com.pyttrainer.android.ui.comune.EventoUi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Stato del dettaglio di un esercizio (Fase 4). [tsStartTesto]/[tsFinishTesto]
 * sono tenuti come testo libero (non Double) per permettere il campo vuoto:
 * a differenza del number_input di Streamlit (che non può essere "vuoto"),
 * qui un campo lasciato vuoto lascia il timestamp a null, che
 * scegli_ed_estrai() interpreta come "stima automaticamente" (euristica
 * 10%/50% della durata, vedi video_helper.scegli_ed_estrai). Forzare sempre
 * un numero (com'è il default 0.0/1.0 del desktop) sprecherebbe proprio il
 * pregio dell'orchestrazione automatica lato Android.
 */
data class EsercizioUiState(
    val bozza: Esercizio,
    val tsStartTesto: String,
    val tsFinishTesto: String,
    val risultatiRicerca: List<VideoYoutube> = emptyList(),
    val videoScartati: List<VideoScartato> = emptyList(),
    val sezioneScartatiAperta: Boolean = false,
    val ricercaInCorso: Boolean = false,
    val estrazioneInCorso: Boolean = false,
    val logEstrazione: List<String> = emptyList(),
    /** Correzione mirata (Fase 7): sostituzione dei soli frame di questo esercizio in un documento già generato. */
    val correzioneInCorso: Boolean = false,
) {
    private val tsStartValore: Double? get() = tsStartTesto.trim().toDoubleOrNull()
    private val tsFinishValore: Double? get() = tsFinishTesto.trim().toDoubleOrNull()

    /** true solo se ENTRAMBI i timestamp sono compilati e non validi (finish <= start). */
    val timestampNonValidi: Boolean
        get() {
            val inizio = tsStartValore
            val fine = tsFinishValore
            return inizio != null && fine != null && fine <= inizio
        }
}

/**
 * Messaggi utente che il ViewModel deve poter emettere ma che NON passano
 * dal bridge Python (quindi non arrivano già tradotti da
 * ErroreScheda.messaggio): un ViewModel non può chiamare stringResource(),
 * quindi il Composable chiamante li legge da strings.xml e li inietta qui
 * tramite [EsercizioViewModel.factory], che resta l'unica fonte per questi
 * testi (nessuna stringa hardcoded nei Composable).
 */
data class EsercizioTesti(
    val nomeVuoto: String,
    val nessunRisultato: String,
    val cartellaNonPronta: String,
    val timestampNonValidi: String,
    val estrazioneOk: String,
    val estrazioneSenzaVideo: String,
    val erroreGenerico: String,
    val correzioneOk: String,
)

/**
 * ViewModel del dettaglio di un esercizio. NON è la sorgente di verità della
 * lista (quella resta [com.pyttrainer.android.ui.scheda.SchedaViewModel]):
 * lavora su una copia locale ("bozza") e la propaga verso l'alto solo
 * quando l'utente salva esplicitamente o quando l'estrazione frame
 * completa con successo (vedi [EsercizioScreen]).
 */
class EsercizioViewModel(
    esercizioIniziale: Esercizio,
    private val cartellaFrames: String?,
    private val testi: EsercizioTesti,
) : ViewModel() {

    private val _stato = MutableStateFlow(
        EsercizioUiState(
            bozza = esercizioIniziale,
            tsStartTesto = esercizioIniziale.tsStart?.toString() ?: "",
            tsFinishTesto = esercizioIniziale.tsFinish?.toString() ?: "",
        )
    )
    val stato: StateFlow<EsercizioUiState> = _stato.asStateFlow()

    private val _eventi = MutableSharedFlow<EventoUi>(extraBufferCapacity = 4)
    val eventi: SharedFlow<EventoUi> = _eventi.asSharedFlow()

    /** Esercizio pronto per essere salvato in SchedaViewModel: bozza + timestamp testuali riconvertiti. */
    fun bozzaCorrente(): Esercizio = _stato.value.let {
        it.bozza.copy(
            tsStart = it.tsStartTesto.trim().toDoubleOrNull(),
            tsFinish = it.tsFinishTesto.trim().toDoubleOrNull(),
        )
    }

    fun aggiornaBozza(trasformazione: (Esercizio) -> Esercizio) {
        _stato.update { it.copy(bozza = trasformazione(it.bozza)) }
    }

    fun impostaTsStartTesto(valore: String) {
        _stato.update { it.copy(tsStartTesto = valore) }
    }

    fun impostaTsFinishTesto(valore: String) {
        _stato.update { it.copy(tsFinishTesto = valore) }
    }

    fun impostaSezioneScartatiAperta(aperta: Boolean) {
        _stato.update { it.copy(sezioneScartatiAperta = aperta) }
    }

    fun cercaVideo() {
        val nome = _stato.value.bozza.nome
        if (nome.isBlank()) {
            _eventi.tryEmit(EventoUi.Errore(testi.nomeVuoto))
            return
        }
        viewModelScope.launch {
            _stato.update { it.copy(ricercaInCorso = true) }
            PythonBridge.cercaVideo(nome).fold(
                onSuccess = { risultato ->
                    _stato.update {
                        it.copy(risultatiRicerca = risultato.pertinenti, videoScartati = risultato.scartati)
                    }
                    if (risultato.pertinenti.isEmpty()) {
                        _eventi.tryEmit(EventoUi.Info(testi.nessunRisultato))
                    }
                },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
            _stato.update { it.copy(ricercaInCorso = false) }
        }
    }

    /**
     * Seleziona un video dai risultati di ricerca: riempie lo stesso campo
     * "URL manuale" (esattamente come fa app.py, che precompila il
     * text_input con l'ultimo video_url), così un'eventuale modifica
     * manuale successiva dell'utente lo sovrascrive naturalmente restando
     * comunque "l'ultima parola" sul campo.
     */
    fun selezionaVideo(video: VideoYoutube) {
        aggiornaBozza { it.copy(videoUrl = video.webpageUrl) }
    }

    fun autoEstrai(onEstrazioneCompletata: (Esercizio, persistiCheckpoint: Boolean) -> Unit) {
        val cartella = cartellaFrames
        if (cartella == null) {
            _eventi.tryEmit(EventoUi.Errore(testi.cartellaNonPronta))
            return
        }
        if (_stato.value.timestampNonValidi) {
            _eventi.tryEmit(EventoUi.Errore(testi.timestampNonValidi))
            return
        }
        viewModelScope.launch {
            _stato.update { it.copy(estrazioneInCorso = true) }
            PythonBridge.autoEstrai(bozzaCorrente(), cartella).fold(
                onSuccess = { risultato ->
                    // esercizio.uid è @Transient: non attraversa il bridge Python, quindi
                    // risultato.esercizio torna con un uid nuovo (casuale). Va rimpiazzato
                    // con quello della bozza corrente, altrimenti SchedaViewModel.aggiornaEsercizio
                    // (che confronta per uid) non troverebbe più questo esercizio nella lista.
                    val esercizioAggiornato = risultato.esercizio.copy(uid = _stato.value.bozza.uid)
                    _stato.update {
                        it.copy(
                            bozza = esercizioAggiornato,
                            tsStartTesto = esercizioAggiornato.tsStart?.toString() ?: it.tsStartTesto,
                            tsFinishTesto = esercizioAggiornato.tsFinish?.toString() ?: it.tsFinishTesto,
                            logEstrazione = risultato.log,
                        )
                    }
                    val pronto = esercizioAggiornato.pronto
                    _eventi.tryEmit(EventoUi.Info(if (pronto) testi.estrazioneOk else testi.estrazioneSenzaVideo))
                    onEstrazioneCompletata(esercizioAggiornato, pronto)
                },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
            _stato.update { it.copy(estrazioneInCorso = false) }
        }
    }

    /**
     * Riallinea SOLO i campi media (video/timestamp/frame) della bozza
     * locale a quelli di [sorgente], lasciando intatti eventuali campi
     * testuali non ancora salvati (nome, spiegazione, ...). Usata quando si
     * torna dal player video (Fase 5): a differenza di autoEstrai() (che
     * passa da Python e riceve indietro l'intero esercizio), la cattura nel
     * player scrive le proprie modifiche direttamente in SchedaViewModel
     * (round-trip più corto), quindi qui serve solo un resync mirato. No-op
     * se [sorgente] non porta nulla di nuovo (evita di far "sfarfallare" i
     * timestamp testuali a ogni ricomposizione).
     */
    fun sincronizzaMediaEsterni(sorgente: Esercizio) {
        _stato.update { stato ->
            val bozza = stato.bozza
            if (bozza.videoUrl == sorgente.videoUrl &&
                bozza.tsStart == sorgente.tsStart &&
                bozza.tsFinish == sorgente.tsFinish &&
                bozza.frameStart == sorgente.frameStart &&
                bozza.frameFinish == sorgente.frameFinish
            ) {
                stato
            } else {
                stato.copy(
                    bozza = bozza.copy(
                        videoUrl = sorgente.videoUrl,
                        tsStart = sorgente.tsStart,
                        tsFinish = sorgente.tsFinish,
                        frameStart = sorgente.frameStart,
                        frameFinish = sorgente.frameFinish,
                    ),
                    tsStartTesto = sorgente.tsStart?.toString() ?: "",
                    tsFinishTesto = sorgente.tsFinish?.toString() ?: "",
                )
            }
        }
    }

    /**
     * Correzione mirata (Fase 7): sostituisce SOLO i due frame di questo
     * esercizio in un documento Google Docs già generato, tramite
     * PythonBridge.aggiornaMedia — senza rigenerare il documento. Richiede
     * un [docId] (documento già esistente, vedi SchedaUiState.docId) e uno
     * [statePath] valido (lo stato scritto da create_workout_document).
     * [accessToken] è una funzione sospesa invece di una stringa perché il
     * token va sempre richiesto fresco al momento della chiamata (vedi
     * GestoreAccessoGoogle.tokenFresco).
     */
    fun correzioneMirata(
        docId: String,
        statePath: String,
        outputDir: String,
        nuovoVideoUrl: String,
        nuovoTsStart: Double?,
        nuovoTsFinish: Double?,
        accessToken: suspend () -> String,
        onCorrezioneCompletata: (Esercizio, persistiCheckpoint: Boolean) -> Unit,
    ) {
        viewModelScope.launch {
            _stato.update { it.copy(correzioneInCorso = true) }
            val token = try {
                accessToken()
            } catch (eccezione: Exception) {
                _eventi.tryEmit(EventoUi.Errore(eccezione.message ?: testi.erroreGenerico))
                _stato.update { it.copy(correzioneInCorso = false) }
                return@launch
            }
            PythonBridge.aggiornaMedia(
                docId, _stato.value.bozza.nome, nuovoVideoUrl, nuovoTsStart, nuovoTsFinish, token, statePath, outputDir,
            ).fold(
                onSuccess = { risultato ->
                    val aggiornato = _stato.value.bozza.copy(
                        videoUrl = nuovoVideoUrl,
                        tsStart = nuovoTsStart,
                        tsFinish = nuovoTsFinish,
                        frameStart = risultato.frameStart,
                        frameFinish = risultato.frameFinish,
                    )
                    _stato.update {
                        it.copy(
                            bozza = aggiornato,
                            tsStartTesto = nuovoTsStart?.toString() ?: "",
                            tsFinishTesto = nuovoTsFinish?.toString() ?: "",
                        )
                    }
                    _eventi.tryEmit(EventoUi.Info(testi.correzioneOk))
                    onCorrezioneCompletata(aggiornato, true)
                },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
            _stato.update { it.copy(correzioneInCorso = false) }
        }
    }

    companion object {
        fun factory(
            esercizioIniziale: Esercizio,
            cartellaFrames: String?,
            testi: EsercizioTesti,
        ): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    EsercizioViewModel(esercizioIniziale, cartellaFrames, testi) as T
            }
    }
}
