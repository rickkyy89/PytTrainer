package com.pyttrainer.android.ui.comune

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
