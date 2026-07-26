package com.pyttrainer.android.ui.documento

import android.content.Intent
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.dati.RisultatoGenerazioneDocumento
import com.pyttrainer.android.dati.StatoGenerazione
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
 * Testi che il ViewModel non può leggere da strings.xml direttamente (vedi
 * EsercizioTesti/RitaglioTesti): gli errori del bridge Python arrivano già
 * in italiano dentro ErroreScheda.messaggio, quindi qui servono solo i
 * messaggi che questo ViewModel genera da sé (esito login, nessun esercizio
 * pronto, ecc.).
 */
data class GeneraDocumentoTesti(
    val nessunEsercizioPronto: String,
    val erroreGenerico: String,
    val accessoCompletato: String,
    val disconnesso: String,
)

/**
 * Stato della schermata di generazione. [eserciziPronti]/[eserciziTotali]
 * sono un'istantanea presa all'apertura dello schermo (gli esercizi arrivano
 * come parametro immutabile, non come riferimento allo stato live di
 * SchedaViewModel): coerente con come le altre schermate di dettaglio
 * (EsercizioScreen, RitaglioScreen) lavorano su una copia e non su un
 * binding diretto.
 */
data class GeneraDocumentoUiState(
    val titolo: String,
    val eserciziTotali: Int,
    val eserciziPronti: Int,
    val connesso: Boolean = false,
    val configurato: Boolean = true,
    /** Percorso di state.json, risolto in modo asincrono da cartellaLavoro: null finché non è pronto. */
    val statePath: String? = null,
    /**
     * true mentre [statePath] è ancora in corso di risoluzione. Serve a
     * bloccare "Genera" in quella finestra: generare con statePath vuoto
     * significa che create_workout_document() non scrive alcun checkpoint, e
     * un'interruzione a metà non lascerebbe nulla da riprendere — al
     * tentativo successivo verrebbe creato un SECONDO documento invece di
     * completare il primo.
     */
    val statePathInRisoluzione: Boolean = false,
    val statoRipresa: StatoGenerazione? = null,
    val generazioneInCorso: Boolean = false,
    val risultato: RisultatoGenerazioneDocumento? = null,
) {
    val eserciziEsclusi: Int get() = eserciziTotali - eserciziPronti

    /** Condizioni per poter avviare la generazione (usata dal pulsante in GeneraDocumentoScreen). */
    val generabile: Boolean
        get() = connesso && eserciziPronti > 0 && !generazioneInCorso && !statePathInRisoluzione
}

/**
 * ViewModel della generazione del Google Doc (CLAUDE.md, sezione "Flusso
 * automatico completo"): prende un token fresco da [gestoreAccesso], filtra
 * gli esercizi pronti e chiama PythonBridge.generaDocumento. NON possiede
 * [gestoreAccesso] (è condiviso, vive in SchedaViewModel, vedi
 * GestoreAccessoGoogle): per questo non lo chiude in onCleared(), lo farebbe
 * la schermata principale finché resta aperta l'app.
 */
class GeneraDocumentoViewModel(
    esercizi: List<Esercizio>,
    titolo: String,
    cartellaLavoro: String?,
    private val gestoreAccesso: GestoreAccessoGoogle,
    private val testi: GeneraDocumentoTesti,
) : ViewModel() {

    /**
     * Filtrati SUBITO alla creazione, non al momento di "genera()": è la
     * stessa lista che genera_documento() riceverà, così il conteggio
     * mostrato in UI ("pronti / totali") corrisponde esattamente a quanto
     * verrà davvero inserito, mai una stima.
     */
    private val eserciziPronti: List<Esercizio> = esercizi.filter { it.pronto }

    private val _stato = MutableStateFlow(
        GeneraDocumentoUiState(
            titolo = titolo,
            eserciziTotali = esercizi.size,
            eserciziPronti = eserciziPronti.size,
            connesso = gestoreAccesso.connesso.value,
            configurato = gestoreAccesso.configurato(),
        )
    )
    val stato: StateFlow<GeneraDocumentoUiState> = _stato.asStateFlow()

    private val _eventi = MutableSharedFlow<EventoUi>(extraBufferCapacity = 4)
    val eventi: SharedFlow<EventoUi> = _eventi.asSharedFlow()

    init {
        viewModelScope.launch {
            gestoreAccesso.connesso.collect { valore -> _stato.update { it.copy(connesso = valore) } }
        }
        // cartellaLavoro può essere null solo se la scheda non è mai stata
        // aperta/salvata (vedi SchedaViewModel.ricalcolaCartellaLavoro): in
        // quel caso non esiste ancora un bundle a cui agganciare uno
        // state.json, quindi niente ripresa e genera() userà statePath="".
        if (!cartellaLavoro.isNullOrBlank()) {
            _stato.update { it.copy(statePathInRisoluzione = true) }
            viewModelScope.launch {
                try {
                    PythonBridge.percorsoStato(cartellaLavoro).fold(
                        onSuccess = { percorso ->
                            _stato.update { it.copy(statePath = percorso) }
                            PythonBridge.statoGenerazione(percorso).onSuccess { statoGenerazione ->
                                _stato.update { it.copy(statoRipresa = statoGenerazione) }
                            }
                        },
                        onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
                    )
                } finally {
                    // Anche in caso di errore la finestra di blocco va chiusa:
                    // se lo state.json non è risolvibile la generazione resta
                    // possibile (senza ripresa), ma non deve restare bloccata.
                    _stato.update { it.copy(statePathInRisoluzione = false) }
                }
            }
        }
    }

    fun intentDiAccesso(): Intent = gestoreAccesso.intentDiAccesso()

    fun completaAccesso(datiRisposta: Intent) {
        viewModelScope.launch {
            gestoreAccesso.completaAccesso(datiRisposta).fold(
                onSuccess = { _eventi.tryEmit(EventoUi.Info(testi.accessoCompletato)) },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
        }
    }

    fun disconnetti() {
        gestoreAccesso.disconnetti()
        _eventi.tryEmit(EventoUi.Info(testi.disconnesso))
    }

    /** [onDocumentoGenerato] avverte il chiamante di persistere il checkpoint (state.json dentro il bundle). */
    fun genera(onDocumentoGenerato: () -> Unit) {
        if (eserciziPronti.isEmpty()) {
            _eventi.tryEmit(EventoUi.Errore(testi.nessunEsercizioPronto))
            return
        }
        viewModelScope.launch {
            _stato.update { it.copy(generazioneInCorso = true) }
            gestoreAccesso.accessTokenFresco().fold(
                onSuccess = { token ->
                    val statePath = _stato.value.statePath ?: ""
                    PythonBridge.generaDocumento(eserciziPronti, _stato.value.titolo, token, statePath).fold(
                        onSuccess = { risultato ->
                            _stato.update { it.copy(risultato = risultato) }
                            onDocumentoGenerato()
                        },
                        onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
                    )
                },
                onFailure = { errore -> _eventi.tryEmit(EventoUi.Errore(errore.message ?: testi.erroreGenerico)) },
            )
            _stato.update { it.copy(generazioneInCorso = false) }
        }
    }

    companion object {
        fun factory(
            esercizi: List<Esercizio>,
            titolo: String,
            cartellaLavoro: String?,
            gestoreAccesso: GestoreAccessoGoogle,
            testi: GeneraDocumentoTesti,
        ): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    GeneraDocumentoViewModel(esercizi, titolo, cartellaLavoro, gestoreAccesso, testi) as T
            }
    }
}
