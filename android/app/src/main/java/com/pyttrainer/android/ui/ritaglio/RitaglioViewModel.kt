package com.pyttrainer.android.ui.ritaglio

import android.graphics.BitmapFactory
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
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

/** Testi che il ViewModel non può leggere da strings.xml direttamente (vedi EsercizioTesti). */
data class RitaglioTesti(
    val ritaglioApplicato: String,
    val originaleRipristinato: String,
    val erroreGenerico: String,
)

/**
 * Stato della schermata di ritaglio (Fase 6). I limiti (ogni percentuale in
 * [0, 45], sinistra+destra e alto+basso sotto 90) sono verificati QUI, prima
 * ancora di interpellare Python: [video_helper.box_ritaglio] li applica
 * comunque server-side, ma la UI deve poter disabilitare "Applica ritaglio"
 * invece di scoprire l'errore solo dopo la chiamata.
 */
data class RitaglioUiState(
    val percorso: String,
    val sinistra: Float = 0f,
    val alto: Float = 0f,
    val destra: Float = 0f,
    val basso: Float = 0f,
    val larghezzaOriginale: Int = 0,
    val altezzaOriginale: Int = 0,
    /** Box in pixel [sinistra, alto, destra, basso] per l'anteprima live, o null finché non calcolato. */
    val boxPixel: List<Int>? = null,
    val haBackup: Boolean = false,
    val operazioneInCorso: Boolean = false,
    /** Incrementata a ogni Applica/Ripristina riuscito: invalida la cache Coil (il file cambia, il percorso no). */
    val versioneImmagine: Long = 0L,
) {
    val sommaOrizzontaleNonValida: Boolean get() = sinistra + destra >= 90f
    val sommaVerticaleNonValida: Boolean get() = alto + basso >= 90f
    val validoPerApplicare: Boolean get() = !sommaOrizzontaleNonValida && !sommaVerticaleNonValida
}

class RitaglioViewModel(
    private val percorso: String,
    private val testi: RitaglioTesti,
) : ViewModel() {

    private val _stato = MutableStateFlow(RitaglioUiState(percorso = percorso))
    val stato: StateFlow<RitaglioUiState> = _stato.asStateFlow()

    private val _eventi = MutableSharedFlow<EventoUi>(extraBufferCapacity = 4)
    val eventi: SharedFlow<EventoUi> = _eventi.asSharedFlow()

    init {
        val opzioni = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(percorso, opzioni)
        _stato.update { it.copy(larghezzaOriginale = opzioni.outWidth, altezzaOriginale = opzioni.outHeight) }

        viewModelScope.launch {
            PythonBridge.haBackupOriginale(percorso).onSuccess { valore ->
                _stato.update { it.copy(haBackup = valore) }
            }
        }
        ricalcolaBox()
    }

    private fun ricalcolaBox() {
        val corrente = _stato.value
        if (corrente.larghezzaOriginale <= 0 || corrente.altezzaOriginale <= 0) return
        if (!corrente.validoPerApplicare) return
        viewModelScope.launch {
            PythonBridge.boxRitaglio(
                corrente.larghezzaOriginale,
                corrente.altezzaOriginale,
                corrente.sinistra.toDouble(),
                corrente.alto.toDouble(),
                corrente.destra.toDouble(),
                corrente.basso.toDouble(),
            ).onSuccess { box -> _stato.update { it.copy(boxPixel = box) } }
        }
    }

    fun impostaSinistra(valore: Float) {
        _stato.update { it.copy(sinistra = valore) }
        ricalcolaBox()
    }

    fun impostaAlto(valore: Float) {
        _stato.update { it.copy(alto = valore) }
        ricalcolaBox()
    }

    fun impostaDestra(valore: Float) {
        _stato.update { it.copy(destra = valore) }
        ricalcolaBox()
    }

    fun impostaBasso(valore: Float) {
        _stato.update { it.copy(basso = valore) }
        ricalcolaBox()
    }

    /** [onFrameModificato] fa risalvare il bundle corrente a SchedaViewModel (checkpoint). */
    fun applicaRitaglio(onFrameModificato: () -> Unit) {
        val corrente = _stato.value
        if (!corrente.validoPerApplicare || corrente.operazioneInCorso) return
        viewModelScope.launch {
            _stato.update { it.copy(operazioneInCorso = true) }
            PythonBridge.ritaglia(percorso, corrente.sinistra.toDouble(), corrente.alto.toDouble(), corrente.destra.toDouble(), corrente.basso.toDouble())
                .fold(
                    onSuccess = {
                        _eventi.tryEmit(EventoUi.Info(testi.ritaglioApplicato))
                        _stato.update {
                            it.copy(
                                sinistra = 0f,
                                alto = 0f,
                                destra = 0f,
                                basso = 0f,
                                boxPixel = null,
                                haBackup = true,
                                versioneImmagine = it.versioneImmagine + 1,
                            )
                        }
                        onFrameModificato()
                    },
                    onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
                )
            _stato.update { it.copy(operazioneInCorso = false) }
        }
    }

    fun ripristinaOriginale(onFrameModificato: () -> Unit) {
        val corrente = _stato.value
        if (!corrente.haBackup || corrente.operazioneInCorso) return
        viewModelScope.launch {
            _stato.update { it.copy(operazioneInCorso = true) }
            PythonBridge.ripristinaOriginale(percorso).fold(
                onSuccess = {
                    _eventi.tryEmit(EventoUi.Info(testi.originaleRipristinato))
                    _stato.update {
                        it.copy(
                            sinistra = 0f,
                            alto = 0f,
                            destra = 0f,
                            basso = 0f,
                            boxPixel = null,
                            versioneImmagine = it.versioneImmagine + 1,
                        )
                    }
                    onFrameModificato()
                },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
            _stato.update { it.copy(operazioneInCorso = false) }
        }
    }

    companion object {
        fun factory(percorso: String, testi: RitaglioTesti): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    RitaglioViewModel(percorso, testi) as T
            }
    }
}
