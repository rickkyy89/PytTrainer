package com.pyttrainer.android.ui.documento

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.getWorkInfoByIdFlow
import androidx.work.workDataOf
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.lavoro.GenerazioneDocumentoWorker
import com.pyttrainer.android.python.PythonBridge
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Testi che il ViewModel non può leggere da strings.xml direttamente (vedi EsercizioTesti). */
data class GeneraDocumentoTesti(
    val nessunEsercizioPronto: String,
    val googleNonConnesso: String,
    val erroreGenerico: String,
)

data class GeneraDocumentoUiState(
    val totale: Int,
    val statoGoogleConnesso: Boolean = GestoreAccessoGoogle.stato.value.connesso,
    val generazioneAvviata: Boolean = false,
    val fatti: Int = 0,
    val url: String? = null,
    val errore: String? = null,
    val terminato: Boolean = false,
)

/**
 * Guida la generazione del documento (Fase 7): incapsula tutto ciò che serve
 * a costruire ed enqueuare GenerazioneDocumentoWorker e a osservarne
 * l'avanzamento tramite WorkManager, senza che GeneraDocumentoScreen debba
 * conoscerne i dettagli (nomi delle chiavi Data, ecc.).
 *
 * Non tocca SchedaViewModel direttamente: MainActivity osserva
 * [GeneraDocumentoUiState.url] (via LaunchedEffect in GeneraDocumentoScreen)
 * e a quel punto fa risalvare il bundle con lo stato aggiornato, esattamente
 * come Ritaglio/Esercizio fanno con i loro callback onFrameModificato/onSalva.
 */
class GeneraDocumentoViewModel(
    applicazione: Application,
    private val eserciziPronti: List<Esercizio>,
    private val titolo: String,
    private val cartellaLavoro: String?,
    private val testi: GeneraDocumentoTesti,
) : AndroidViewModel(applicazione) {

    private val gestoreLavoro = WorkManager.getInstance(applicazione)

    private val _stato = MutableStateFlow(GeneraDocumentoUiState(totale = eserciziPronti.size))
    val stato: StateFlow<GeneraDocumentoUiState> = _stato.asStateFlow()

    init {
        viewModelScope.launch {
            GestoreAccessoGoogle.stato.collect { accesso ->
                _stato.update { it.copy(statoGoogleConnesso = accesso.connesso) }
            }
        }
    }

    fun avviaGenerazione() {
        if (_stato.value.generazioneAvviata) return
        if (eserciziPronti.isEmpty()) {
            _stato.update { it.copy(errore = testi.nessunEsercizioPronto) }
            return
        }
        if (!GestoreAccessoGoogle.stato.value.connesso) {
            _stato.update { it.copy(errore = testi.googleNonConnesso) }
            return
        }

        _stato.update { it.copy(generazioneAvviata = true, errore = null, terminato = false, fatti = 0, url = null) }

        viewModelScope.launch {
            val statePath = cartellaLavoro?.let { PythonBridge.percorsoStato(it).getOrNull() } ?: ""
            val dati = workDataOf(
                GenerazioneDocumentoWorker.KEY_ESERCIZI_JSON to GenerazioneDocumentoWorker.serializzaEsercizi(eserciziPronti),
                GenerazioneDocumentoWorker.KEY_TITOLO to titolo,
                GenerazioneDocumentoWorker.KEY_STATE_PATH to statePath,
            )
            val richiesta = OneTimeWorkRequestBuilder<GenerazioneDocumentoWorker>()
                .setInputData(dati)
                .build()
            gestoreLavoro.enqueue(richiesta)
            osservaLavoro(richiesta.id)
        }
    }

    private fun osservaLavoro(id: UUID) {
        viewModelScope.launch {
            gestoreLavoro.getWorkInfoByIdFlow(id).collect { info ->
                if (info == null) return@collect

                val fatti = info.progress.getInt(GenerazioneDocumentoWorker.KEY_PROGRESSO_FATTI, _stato.value.fatti)
                val totale = info.progress.getInt(GenerazioneDocumentoWorker.KEY_PROGRESSO_TOTALE, _stato.value.totale)
                _stato.update { it.copy(fatti = fatti, totale = totale.takeIf { t -> t > 0 } ?: it.totale) }

                when (info.state) {
                    WorkInfo.State.SUCCEEDED -> {
                        val url = info.outputData.getString(GenerazioneDocumentoWorker.KEY_URL)
                        _stato.update {
                            it.copy(url = url, terminato = true, generazioneAvviata = false, fatti = it.totale)
                        }
                    }
                    WorkInfo.State.FAILED -> {
                        val errore = info.outputData.getString(GenerazioneDocumentoWorker.KEY_ERRORE) ?: testi.erroreGenerico
                        _stato.update { it.copy(errore = errore, terminato = true, generazioneAvviata = false) }
                    }
                    WorkInfo.State.CANCELLED -> {
                        _stato.update { it.copy(terminato = true, generazioneAvviata = false) }
                    }
                    else -> Unit
                }
            }
        }
    }

    companion object {
        fun factory(
            applicazione: Application,
            eserciziPronti: List<Esercizio>,
            titolo: String,
            cartellaLavoro: String?,
            testi: GeneraDocumentoTesti,
        ): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T =
                    GeneraDocumentoViewModel(applicazione, eserciziPronti, titolo, cartellaLavoro, testi) as T
            }
    }
}
