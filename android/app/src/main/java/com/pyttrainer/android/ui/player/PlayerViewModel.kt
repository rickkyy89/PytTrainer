package com.pyttrainer.android.ui.player

import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.pyttrainer.android.python.PythonBridge
import com.pyttrainer.android.ui.comune.EventoUi
import java.io.FileOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Testi che il ViewModel non può leggere da strings.xml direttamente (vedi EsercizioTesti). */
data class PlayerTesti(
    val streamErrore: String,
    val catturaOk: String,
    val catturaFallita: String,
    val erroreGenerico: String,
)

/**
 * Stato della schermata player (Fase 5). [streamUrl] è risolto via
 * PythonBridge.streamUrl e riprepara ExoPlayer ogni volta che cambia (sia al
 * primo caricamento sia dopo un ri-tentativo per URL scaduto): [versioneStream]
 * garantisce che l'effetto scatti anche nel caso raro in cui yt-dlp
 * risolva di nuovo lo STESSO url testuale.
 *
 * [frameStart]/[frameFinish] partono precompilati con gli eventuali frame già
 * presenti sull'esercizio (frame_start/frame_finish nel manifest): l'utente
 * vede subito le miniature di quanto già catturato in precedenza e può
 * ricatturarle. [versioneFrameStart]/[versioneFrameFinish] invalidano la
 * cache Coil quando lo stesso percorso viene sovrascritto da una nuova
 * cattura (stessa convenzione di RitaglioViewModel.versioneImmagine).
 */
data class PlayerUiState(
    val streamUrl: String? = null,
    val versioneStream: Long = 0L,
    val risoluzioneInCorso: Boolean = false,
    val erroreStream: String? = null,
    val frameStart: String? = null,
    val frameFinish: String? = null,
    val tsStart: Double? = null,
    val tsFinish: Double? = null,
    val versioneFrameStart: Long = 0L,
    val versioneFrameFinish: Long = 0L,
    val catturaInCorso: Boolean = false,
)

/**
 * ViewModel del player video (Fase 5). Non tocca [com.pyttrainer.android.ui.scheda.SchedaViewModel]
 * direttamente: l'esercizio aggiornato torna indietro tramite il callback
 * onConferma cablato da MainActivity, come per Ritaglio/Esercizio.
 */
class PlayerViewModel(
    private val url: String,
    private val nomeEsercizio: String,
    private val cartellaLavoro: String,
    frameStartIniziale: String?,
    frameFinishIniziale: String?,
    tsStartIniziale: Double?,
    tsFinishIniziale: Double?,
    private val testi: PlayerTesti,
) : ViewModel() {

    private val _stato = MutableStateFlow(
        PlayerUiState(
            frameStart = frameStartIniziale,
            frameFinish = frameFinishIniziale,
            tsStart = tsStartIniziale,
            tsFinish = tsFinishIniziale,
        )
    )
    val stato: StateFlow<PlayerUiState> = _stato.asStateFlow()

    private val _eventi = MutableSharedFlow<EventoUi>(extraBufferCapacity = 4)
    val eventi: SharedFlow<EventoUi> = _eventi.asSharedFlow()

    init {
        risolviStream()
    }

    /**
     * Risolve (o ri-risolve) l'URL diretto dello stream. Va richiamata anche
     * quando la riproduzione fallisce con un errore di rete a metà visione:
     * gli stream URL risolti da yt-dlp scadono dopo qualche ora, e l'unico
     * modo di riprendere è ottenerne uno nuovo (vedi nota in PlayerScreen).
     */
    fun risolviStream() {
        viewModelScope.launch {
            _stato.update { it.copy(risoluzioneInCorso = true, erroreStream = null) }
            PythonBridge.streamUrl(url).fold(
                onSuccess = { risolto ->
                    _stato.update {
                        it.copy(streamUrl = risolto, versioneStream = it.versioneStream + 1, erroreStream = null)
                    }
                },
                onFailure = { errore ->
                    _stato.update { it.copy(erroreStream = errore.message ?: testi.streamErrore) }
                },
            )
            _stato.update { it.copy(risoluzioneInCorso = false) }
        }
    }

    /**
     * Cattura il fotogramma [tipo] ("start"|"finish") alla posizione
     * [posizioneMs] (millisecondi, come restituito da player.currentPosition):
     * 1) chiede a Python il percorso di destinazione convenzionale, 2) prova
     * MediaMetadataRetriever alla risoluzione nativa sullo stream, 3) in
     * caso di fallimento ricade su [catturaBitmapVisibile] (il contenuto
     * della TextureView, "quel che si vede" — necessario con gli stream
     * adattivi su cui MediaMetadataRetriever a volte non riesce a
     * posizionarsi). Tutto il lavoro IO gira su Dispatchers.IO.
     */
    fun cattura(tipo: String, posizioneMs: Long, streamUrlCorrente: String, catturaBitmapVisibile: suspend () -> Bitmap?) {
        viewModelScope.launch {
            _stato.update { it.copy(catturaInCorso = true) }
            val percorso = PythonBridge.percorsoFrame(cartellaLavoro, nomeEsercizio, tipo).getOrElse { errore ->
                _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico))
                _stato.update { it.copy(catturaInCorso = false) }
                return@launch
            }

            val secondi = posizioneMs / 1000.0
            val riuscito = withContext(Dispatchers.IO) {
                val bitmap = estraiFrameNativo(streamUrlCorrente, posizioneMs) ?: catturaBitmapVisibile()
                bitmap?.let { scriviJpeg(it, percorso) } ?: false
            }

            if (riuscito) {
                _stato.update { stato ->
                    if (tipo == "start") {
                        stato.copy(frameStart = percorso, tsStart = secondi, versioneFrameStart = stato.versioneFrameStart + 1)
                    } else {
                        stato.copy(frameFinish = percorso, tsFinish = secondi, versioneFrameFinish = stato.versioneFrameFinish + 1)
                    }
                }
                _eventi.tryEmit(EventoUi.Info(testi.catturaOk))
            } else {
                _eventi.tryEmit(EventoUi.Errore(testi.catturaFallita))
            }
            _stato.update { it.copy(catturaInCorso = false) }
        }
    }

    /** [risoluzione nativa]: null se il retriever non riesce a decodificare il frame (es. stream adattivo). */
    private fun estraiFrameNativo(streamUrl: String, posizioneMs: Long): Bitmap? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(streamUrl, mapOf<String, String>())
            retriever.getFrameAtTime(posizioneMs * 1000, MediaMetadataRetriever.OPTION_CLOSEST)
        } catch (_: Exception) {
            null
        } finally {
            retriever.release()
        }
    }

    private fun scriviJpeg(bitmap: Bitmap, percorso: String): Boolean =
        try {
            FileOutputStream(percorso).use { output -> bitmap.compress(Bitmap.CompressFormat.JPEG, 90, output) }
            true
        } catch (_: Exception) {
            false
        }

    companion object {
        fun factory(
            url: String,
            nomeEsercizio: String,
            cartellaLavoro: String,
            frameStartIniziale: String?,
            frameFinishIniziale: String?,
            tsStartIniziale: Double?,
            tsFinishIniziale: Double?,
            testi: PlayerTesti,
        ): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    PlayerViewModel(
                        url, nomeEsercizio, cartellaLavoro,
                        frameStartIniziale, frameFinishIniziale, tsStartIniziale, tsFinishIniziale, testi,
                    ) as T
            }
    }
}
