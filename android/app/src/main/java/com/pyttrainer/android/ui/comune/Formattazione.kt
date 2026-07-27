package com.pyttrainer.android.ui.comune

import java.util.Locale

/**
 * Formatta una durata in secondi come mm:ss, gestendo valori mancanti.
 * Equivalente Kotlin di app.py::_formatta_durata, riprodotta qui perché è
 * pura formattazione UI (non attraversa il bridge Python).
 */
fun formattaDurata(secondi: Double?): String {
    if (secondi == null || secondi <= 0.0) return "durata sconosciuta"
    val totali = secondi.toInt()
    val minuti = totali / 60
    val resto = totali % 60
    return "%02d:%02d".format(minuti, resto)
}

/**
 * Posizione corrente del player come "mm:ss (N,N s)". Il valore in secondi con
 * un decimale non è una ridondanza estetica: è esattamente il formato che i
 * campi Timestamp START/FINISH accettano, quindi chi guarda il video può
 * leggere il numero e riportarlo com'è, senza convertire mm:ss a mente.
 */
fun formattaPosizionePlayer(millisecondi: Long): String {
    val millisecondiNonNegativi = millisecondi.coerceAtLeast(0L)
    val secondiTotali = millisecondiNonNegativi / 1000
    val minuti = secondiTotali / 60
    val resto = secondiTotali % 60
    val secondiConDecimale = millisecondiNonNegativi / 1000.0
    // Locale.ROOT, non il locale del device: con l'italiano "%.1f" produce
    // "19,5", ma i campi Timestamp leggono il valore con toDoubleOrNull(), che
    // accetta SOLO il punto decimale. Un numero copiato con la virgola
    // verrebbe scartato in silenzio (timestamp = null), cioè esattamente il
    // contrario di quello che questa riga serve a fare.
    return "%02d:%02d (%.1f s)".format(Locale.ROOT, minuti, resto, secondiConDecimale)
}
