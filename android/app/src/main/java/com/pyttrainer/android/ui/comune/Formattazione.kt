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

/**
 * Orologio della posizione corrente del player video (Fase 5), in
 * mm:ss.SSS: a differenza di [formattaDurata] serve la precisione al
 * millisecondo per poter fermarsi sul fotogramma esatto di un movimento
 * veloce.
 */
fun formattaPosizioneMillisecondi(posizioneMs: Long): String {
    val totali = posizioneMs.coerceAtLeast(0)
    val minuti = totali / 60_000
    val secondi = (totali % 60_000) / 1_000
    val millisecondi = totali % 1_000
    return "%02d:%02d.%03d".format(minuti, secondi, millisecondi)
}
