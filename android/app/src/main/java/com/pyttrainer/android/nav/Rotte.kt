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

    /** Generazione del Google Doc (Fase 7): titolo/esercizi/cartellaLavoro letti da [SchedaViewModel]. */
    @Serializable
    data object GeneraDocumento : Rotta

    /**
     * Player video (Fase 5): guarda [url] e cattura i fotogrammi START/FINISH
     * per l'esercizio [uid]/[nomeEsercizio]. [cartellaLavoro] serve a
     * PythonBridge.percorsoFrame per calcolare la destinazione dei frame
     * catturati (mai ricalcolata in Kotlin). Gli iniziali (frame già
     * presenti, timestamp già scelti) sono passati come stringhe — vuota =
     * assente — così la rotta resta interamente fatta di tipi primitivi
     * serializzabili senza dover marcare campi nullable.
     */
    @Serializable
    data class Player(
        val uid: String,
        val url: String,
        val nomeEsercizio: String,
        val cartellaLavoro: String,
        val frameStartIniziale: String = "",
        val frameFinishIniziale: String = "",
        val tsStartIniziale: String = "",
        val tsFinishIniziale: String = "",
    ) : Rotta

    /** Accesso Google, package name e impronta SHA-1 per la configurazione OAuth (Fase 7). */
    @Serializable
    data object Impostazioni : Rotta
}
