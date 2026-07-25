package com.pyttrainer.android.ui.comune

/**
 * Evento "una tantum" emesso da un ViewModel verso la UI (Snackbar),
 * distinto dallo stato persistente esposto via StateFlow: uno stato
 * ricreerebbe la Snackbar a ogni ricomposizione/rotazione, un evento no.
 */
sealed interface EventoUi {
    data class Errore(val messaggio: String) : EventoUi
    data class Info(val messaggio: String) : EventoUi

    /** Come [Info], ma la Snackbar mostra anche un'azione "Annulla" (swipe-to-delete). */
    data class EsercizioRimosso(val nomeEsercizio: String) : EventoUi
}
