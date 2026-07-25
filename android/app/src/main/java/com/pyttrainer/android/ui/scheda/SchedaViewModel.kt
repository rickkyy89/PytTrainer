package com.pyttrainer.android.ui.scheda

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.pyttrainer.android.dati.ArchivioSchede
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.python.PythonBridge
import com.pyttrainer.android.ui.comune.EventoUi
import java.io.File
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Stato mostrato da [SchedaScreen] (schermata principale, equivalente della sidebar + lista di app.py). */
data class SchedaUiState(
    val titolo: String = "SCHEDA 1: GAMBE & GLUTEI",
    val esercizi: List<Esercizio> = emptyList(),
    val nomeFileVisualizzato: String? = null,
    val bundleApribile: Boolean = false,
    val caricamento: Boolean = false,
    val cartellaLavoro: String? = null,
    val cartellaFrames: String? = null,
    val statoGoogleConnesso: Boolean = false,
    val anteprimaImportCsv: List<Esercizio>? = null,
) {
    val eserciziPronti: Int
        get() = esercizi.count { it.pronto }
}

/**
 * Sorgente di verità della scheda in modifica. Gli altri ViewModel (Esercizio,
 * Ritaglio) NON duplicano la lista: leggono l'esercizio corrente da qui
 * (tramite [SchedaUiState.esercizi]) e vi scrivono aggiornamenti tramite
 * [aggiornaEsercizio]. L'ordine della lista è significativo (vedi CLAUDE.md:
 * determina l'ordine nel documento generato) e va sempre preservato.
 */
class SchedaViewModel(applicazione: Application) : AndroidViewModel(applicazione) {

    private val archivio = ArchivioSchede(applicazione.applicationContext)

    private val _stato = MutableStateFlow(SchedaUiState())
    val stato: StateFlow<SchedaUiState> = _stato.asStateFlow()

    private val _eventi = MutableSharedFlow<EventoUi>(extraBufferCapacity = 4)
    val eventi: SharedFlow<EventoUi> = _eventi.asSharedFlow()

    /** Uri SAF del bundle attualmente aperto/salvato, o null se la scheda non è mai stata salvata. */
    private var uriCorrente: Uri? = null

    /** Percorso locale (dentro filesDir) da cui/verso cui Python legge/scrive il bundle corrente. */
    private var percorsoLocaleCorrente: File = percorsoBozza()

    /** Ultimo esercizio rimosso, per l'azione "Annulla" della Snackbar dello swipe-to-delete. */
    private var ultimoRimosso: Pair<Esercizio, Int>? = null

    init {
        viewModelScope.launch { ricalcolaCartellaLavoro() }
    }

    private fun percorsoBozza(): File =
        File(getApplication<Application>().filesDir, "schede_saf/bozza.scheda")

    /**
     * Ricalcola cartella di lavoro e cartella frame a partire da
     * [percorsoLocaleCorrente] (sempre un percorso dentro filesDir, mai
     * l'Uri SAF): usata all'avvio (bozza) e dopo ogni Apri/Salva come
     * riuscito, quando il bundle "attivo" cambia.
     */
    private suspend fun ricalcolaCartellaLavoro() {
        val cartella = PythonBridge.cartellaLavoroPerBundle(percorsoLocaleCorrente.absolutePath)
            .getOrElse { emettiErrore(it.message); return }
        val frames = PythonBridge.cartellaFrames(cartella)
            .getOrElse { emettiErrore(it.message); return }
        _stato.update { it.copy(cartellaLavoro = cartella, cartellaFrames = frames) }
    }

    private fun emettiErrore(messaggio: String?) {
        _eventi.tryEmit(EventoUi.Errore(messaggio ?: "Errore sconosciuto."))
    }

    private fun emettiInfo(messaggio: String) {
        _eventi.tryEmit(EventoUi.Info(messaggio))
    }

    private fun impostaCaricamento(valore: Boolean) {
        _stato.update { it.copy(caricamento = valore) }
    }

    // ------------------------------------------------------------------
    // Titolo
    // ------------------------------------------------------------------

    fun impostaTitolo(nuovoTitolo: String) {
        _stato.update { it.copy(titolo = nuovoTitolo) }
    }

    // ------------------------------------------------------------------
    // Apertura / salvataggio del bundle .scheda via SAF
    // ------------------------------------------------------------------

    fun apriScheda(uri: Uri) {
        viewModelScope.launch {
            impostaCaricamento(true)
            try {
                val locale = archivio.copiaDaUri(uri)
                val cartellaBundle = PythonBridge.cartellaLavoroPerBundle(locale.absolutePath)
                    .getOrElse { emettiErrore(it.message); return@launch }
                val risultato = PythonBridge.carica(locale.absolutePath, cartellaBundle)
                    .getOrElse { emettiErrore(it.message); return@launch }
                val frames = PythonBridge.cartellaFrames(risultato.cartellaLavoro)
                    .getOrElse { emettiErrore(it.message); return@launch }

                uriCorrente = uri
                percorsoLocaleCorrente = locale
                _stato.update {
                    it.copy(
                        esercizi = risultato.esercizi,
                        nomeFileVisualizzato = archivio.nomeVisualizzato(uri),
                        bundleApribile = true,
                        cartellaLavoro = risultato.cartellaLavoro,
                        cartellaFrames = frames,
                    )
                }
                emettiInfo("Scheda caricata: ${risultato.esercizi.size} esercizi.")
            } finally {
                impostaCaricamento(false)
            }
        }
    }

    /** Sovrascrive il bundle già aperto/salvato. No-op silenzioso se non c'è ancora un Uri corrente. */
    fun salva() {
        val uri = uriCorrente ?: run {
            emettiErrore("Nessun file scheda ancora scelto: usa \"Salva come\" la prima volta.")
            return
        }
        viewModelScope.launch {
            impostaCaricamento(true)
            try {
                if (!scriviBundleLocale()) return@launch
                try {
                    archivio.copiaSuUri(percorsoLocaleCorrente, uri)
                } catch (errore: Exception) {
                    emettiErrore("Scheda salvata localmente ma non scritta sul file scelto: ${errore.message}")
                    return@launch
                }
                emettiInfo("Scheda salvata (${_stato.value.esercizi.size} esercizi).")
            } finally {
                impostaCaricamento(false)
            }
        }
    }

    /** Salva il bundle su un nuovo Uri scelto dall'utente e lo adotta come bundle corrente. */
    fun salvaCome(uri: Uri) {
        viewModelScope.launch {
            impostaCaricamento(true)
            try {
                archivio.persistiPermesso(uri, scrittura = true)
                val nuovoLocale = archivio.percorsoLocalePer(uri)
                val vecchioLocale = percorsoLocaleCorrente
                percorsoLocaleCorrente = nuovoLocale
                if (!scriviBundleLocale()) {
                    percorsoLocaleCorrente = vecchioLocale
                    return@launch
                }
                try {
                    archivio.copiaSuUri(nuovoLocale, uri)
                } catch (errore: Exception) {
                    emettiErrore("Scheda salvata localmente ma non scritta sul file scelto: ${errore.message}")
                    return@launch
                }
                uriCorrente = uri
                _stato.update { it.copy(bundleApribile = true, nomeFileVisualizzato = archivio.nomeVisualizzato(uri)) }
                ricalcolaCartellaLavoro()
                emettiInfo("Scheda salvata come nuovo file.")
            } finally {
                impostaCaricamento(false)
            }
        }
    }

    /**
     * Scrive il bundle nel file locale attivo ([percorsoLocaleCorrente]),
     * riusando lo state.json della cartella di lavoro CORRENTE (quella prima
     * di un eventuale cambio, vedi [salvaCome]) così lo stato di ripresa
     * della generazione documento non si perde quando si salva con un nuovo
     * nome. Restituisce false (ed emette l'errore) in caso di fallimento.
     */
    private suspend fun scriviBundleLocale(): Boolean {
        val cartellaStato = _stato.value.cartellaLavoro
        val statoPath = if (cartellaStato != null) {
            PythonBridge.percorsoStato(cartellaStato).getOrElse { emettiErrore(it.message); return false }
        } else {
            ""
        }
        return PythonBridge.salva(_stato.value.esercizi, percorsoLocaleCorrente.absolutePath, statoPath)
            .fold(
                onSuccess = { true },
                onFailure = { emettiErrore(it.message); false },
            )
    }

    // ------------------------------------------------------------------
    // Import/export CSV (anteprima + conferma, come il tab CSV di app.py)
    // ------------------------------------------------------------------

    fun importaCsvAnteprima(uri: Uri) {
        viewModelScope.launch {
            impostaCaricamento(true)
            try {
                val locale = archivio.copiaDaUri(uri)
                PythonBridge.importaCsv(locale.absolutePath).fold(
                    onSuccess = { esercizi ->
                        if (esercizi.isEmpty()) {
                            emettiInfo("Nessun esercizio trovato nel CSV.")
                        } else {
                            _stato.update { it.copy(anteprimaImportCsv = esercizi) }
                        }
                    },
                    onFailure = { emettiErrore(it.message) },
                )
            } finally {
                impostaCaricamento(false)
            }
        }
    }

    fun confermaImportCsv() {
        val anteprima = _stato.value.anteprimaImportCsv ?: return
        _stato.update { it.copy(esercizi = it.esercizi + anteprima, anteprimaImportCsv = null) }
        emettiInfo("Importati ${anteprima.size} esercizi.")
    }

    fun annullaImportCsv() {
        _stato.update { it.copy(anteprimaImportCsv = null) }
    }

    fun esportaCsv(uri: Uri) {
        viewModelScope.launch {
            impostaCaricamento(true)
            try {
                val locale = File(getApplication<Application>().cacheDir, "esporta_tmp.csv")
                PythonBridge.esportaCsv(_stato.value.esercizi, locale.absolutePath).fold(
                    onSuccess = {
                        try {
                            archivio.copiaSuUri(locale, uri)
                            emettiInfo("CSV esportato (${_stato.value.esercizi.size} esercizi).")
                        } catch (errore: Exception) {
                            emettiErrore("Esportazione CSV non riuscita: ${errore.message}")
                        }
                    },
                    onFailure = { emettiErrore(it.message) },
                )
            } finally {
                impostaCaricamento(false)
            }
        }
    }

    // ------------------------------------------------------------------
    // Gestione della lista esercizi
    // ------------------------------------------------------------------

    fun svuotaLista() {
        _stato.update { it.copy(esercizi = emptyList()) }
        ultimoRimosso = null
    }

    fun aggiungiEsercizio(esercizio: Esercizio) {
        _stato.update { it.copy(esercizi = it.esercizi + esercizio) }
    }

    /** Aggiorna (per uid) un esercizio già in lista, es. dopo modifica campi o estrazione frame. */
    fun aggiornaEsercizio(nuovo: Esercizio, persistiCheckpoint: Boolean = false) {
        _stato.update { stato ->
            stato.copy(esercizi = stato.esercizi.map { if (it.uid == nuovo.uid) nuovo else it })
        }
        if (persistiCheckpoint) persistiCheckpointSeDisponibile()
    }

    fun rimuoviEsercizio(uid: String) {
        val lista = _stato.value.esercizi
        val indice = lista.indexOfFirst { it.uid == uid }
        if (indice < 0) return
        val esercizio = lista[indice]
        ultimoRimosso = esercizio to indice
        _stato.update { it.copy(esercizi = it.esercizi.filterNot { es -> es.uid == uid }) }
        _eventi.tryEmit(EventoUi.EsercizioRimosso(esercizio.nome.ifBlank { "Esercizio" }))
    }

    fun ripristinaUltimoRimosso() {
        val (esercizio, indice) = ultimoRimosso ?: return
        _stato.update {
            val lista = it.esercizi.toMutableList()
            lista.add(indice.coerceIn(0, lista.size), esercizio)
            it.copy(esercizi = lista)
        }
        ultimoRimosso = null
    }

    /** Riordina per trascinamento: sposta l'esercizio in [indiceOrigine] alla posizione [indiceDestinazione]. */
    fun riordina(indiceOrigine: Int, indiceDestinazione: Int) {
        _stato.update {
            val lista = it.esercizi.toMutableList()
            if (indiceOrigine !in lista.indices || indiceDestinazione !in lista.indices) return@update it
            val elemento = lista.removeAt(indiceOrigine)
            lista.add(indiceDestinazione, elemento)
            it.copy(esercizi = lista)
        }
    }

    /**
     * Risalva silenziosamente il bundle corrente (nessuna Snackbar di
     * successo, solo in caso di errore): usata dopo operazioni che
     * modificano frame o campi di un esercizio (checkpoint), come fa il
     * desktop dopo l'estrazione frame. No-op se la scheda non è mai stata
     * aperta/salvata (niente Uri a cui scrivere): in quel caso le modifiche
     * restano solo in memoria finché l'utente non fa "Salva come".
     */
    private fun persistiCheckpointSeDisponibile() {
        val uri = uriCorrente ?: return
        viewModelScope.launch {
            if (!scriviBundleLocale()) return@launch
            try {
                archivio.copiaSuUri(percorsoLocaleCorrente, uri)
            } catch (errore: Exception) {
                emettiErrore("Checkpoint non salvato sul file: ${errore.message}")
            }
        }
    }

    /** Punto d'ingresso pubblico per i checkpoint dopo il ritaglio di un frame (Fase 6). */
    fun persistiCheckpointDopoRitaglio() = persistiCheckpointSeDisponibile()
}
