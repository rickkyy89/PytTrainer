package com.pyttrainer.android.python

/**
 * Esito (envelope JSON grezzo) dell'ultima registrazione del backend nativo
 * di estrazione frame, eseguita una sola volta da
 * PytTrainerApplication.onCreate(). Un semplice singleton in-memory: per un
 * valore impostato una sola volta all'avvio del processo non serve un
 * ViewModel/StateFlow, basta per la schermata di verifica di questa fase.
 */
object EsitoAvvio {
    var rispostaRegistrazioneBackend: String = "Registrazione non ancora eseguita."
        internal set
}
