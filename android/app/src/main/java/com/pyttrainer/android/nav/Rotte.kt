package com.pyttrainer.android.nav

import kotlinx.serialization.Serializable

/**
 * Rotte tipizzate del grafo di navigazione (Navigation Compose 2.8+, basato
 * su kotlinx.serialization: ogni oggetto/classe qui sotto è sia la
 * destinazione sia i suoi argomenti, niente stringhe di rotta scritte a
 * mano). [SchedaViewModel] resta l'unica sorgente di verità della lista
 * esercizi: le rotte con parametri portano solo l'identificativo (uid) o un
 * percorso di file, mai una copia dei dati, per non rischiare che la UI mostri
 * uno stato disallineato da quello del ViewModel condiviso.
 */
sealed interface Rotta {

    /** Schermata principale: titolo scheda, elenco esercizi, menu file. */
    @Serializable
    data object Scheda : Rotta

    /** Dettaglio di un esercizio (Fase 4), identificato dal suo [uid] stabile lato UI. */
    @Serializable
    data class Esercizio(val uid: String) : Rotta

    /**
     * Ritaglio di un frame (Fase 6). [percorso] è il percorso assoluto del
     * frame già estratto (esercizio.frameStart/frameFinish): non va MAI
     * ricalcolato in Kotlin, viene passato così com'è da chi naviga qui.
     * [tipo] è "start" o "finish", solo per etichettare la schermata.
     */
    @Serializable
    data class Ritaglio(val uid: String, val tipo: String, val percorso: String) : Rotta

    /**
     * Generazione del Google Doc (accesso Google via AppAuth + PythonBridge.generaDocumento).
     * Nessun parametro: esercizi/titolo/cartella di lavoro vengono letti da
     * [com.pyttrainer.android.ui.scheda.SchedaViewModel] al momento della
     * navigazione (vedi MainActivity), non serializzati nella rotta.
     */
    @Serializable
    data object GeneraDocumento : Rotta

    /**
     * Anteprima del video con media3/ExoPlayer. [url] è la PAGINA YouTube
     * dell'esercizio (esercizio.video_url), non uno stream diretto: la
     * risoluzione tramite yt-dlp avviene in PlayerViewModel, così la rotta
     * resta stabile anche quando lo stream scade.
     */
    @Serializable
    data class Player(val url: String) : Rotta
}
