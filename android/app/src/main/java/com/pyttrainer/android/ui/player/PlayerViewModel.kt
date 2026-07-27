package com.pyttrainer.android.ui.player

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.pyttrainer.android.python.PythonBridge
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Testi che il ViewModel non può leggere da strings.xml (vedi EsercizioTesti):
 * qui serve solo il messaggio di ripiego, perché gli errori del bridge Python
 * arrivano già in italiano dentro ErroreScheda.messaggio.
 */
data class PlayerTesti(val erroreGenerico: String)

data class PlayerUiState(
    /** URL diretto dello stream, risolto da yt-dlp: null finché non è pronto o se la risoluzione è fallita. */
    val streamUrl: String? = null,
    val risoluzioneInCorso: Boolean = false,
    val errore: String? = null,
)

/**
 * Risolve l'URL riproducibile a partire dalla pagina YouTube dell'esercizio.
 *
 * ExoPlayer non sa cosa farsene di un link "watch?v=...": serve l'URL diretto
 * dello stream, che PythonBridge.streamUrl ottiene da yt-dlp chiedendo il
 * formato scelto apposta per Android (mp4 progressivo fino a 720p, vedi
 * FORMATO_ANDROID in android_bridge.py) — lo stesso che usa anche il backend
 * nativo di estrazione frame, così l'anteprima mostra esattamente i fotogrammi
 * da cui verranno presi START e FINISH.
 *
 * La risoluzione è una chiamata di rete di qualche secondo e vive qui, non nel
 * Composable: sopravvive alla ricomposizione e non riparte a ogni rotazione.
 */
class PlayerViewModel(
    private val urlPagina: String,
    private val testi: PlayerTesti,
) : ViewModel() {

    private val _stato = MutableStateFlow(PlayerUiState())
    val stato: StateFlow<PlayerUiState> = _stato.asStateFlow()

    init {
        risolviStream()
    }

    fun risolviStream() {
        if (urlPagina.isBlank()) {
            _stato.update { it.copy(errore = testi.erroreGenerico) }
            return
        }
        viewModelScope.launch {
            _stato.update { it.copy(risoluzioneInCorso = true, errore = null) }
            PythonBridge.streamUrl(urlPagina).fold(
                onSuccess = { url -> _stato.update { it.copy(streamUrl = url, risoluzioneInCorso = false) } },
                onFailure = { errore ->
                    _stato.update {
                        it.copy(
                            streamUrl = null,
                            risoluzioneInCorso = false,
                            errore = errore.message ?: testi.erroreGenerico,
                        )
                    }
                },
            )
        }
    }

    companion object {
        fun factory(urlPagina: String, testi: PlayerTesti): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    PlayerViewModel(urlPagina, testi) as T
            }
    }
}
