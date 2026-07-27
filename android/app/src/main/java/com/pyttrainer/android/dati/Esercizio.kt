package com.pyttrainer.android.dati

import java.util.UUID
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient

/**
 * Rappresentazione Kotlin di un esercizio del manifest (stesso dizionario
 * Python con le chiavi nome/spiegazione/note/ripetizioni/recupero/gruppo/
 * video_url/ts_start/ts_finish/frame_start/frame_finish, vedi CLAUDE.md).
 * I nomi delle proprietà sono in camelCase (convenzione Kotlin) con
 * @SerialName sulle chiavi Python snake_case, così la serializzazione verso
 * il bridge (android_bridge.py) resta un dizionario con le chiavi esatte
 * attese da scheda_file/csv_utils/google_docs_helper.
 */
@Serializable
data class Esercizio(
    val nome: String,
    val spiegazione: String,
    val note: String,
    val ripetizioni: String,
    val recupero: String,
    val gruppo: String = "",
    @SerialName("video_url") val videoUrl: String = "",
    @SerialName("ts_start") val tsStart: Double? = null,
    @SerialName("ts_finish") val tsFinish: Double? = null,
    @SerialName("frame_start") val frameStart: String? = null,
    @SerialName("frame_finish") val frameFinish: String? = null,
    // Esiste solo lato UI (es. chiave stabile per le liste Compose):
    // @Transient lo esclude dal JSON scambiato con Python, che non lo conosce
    // e non deve conoscerlo.
    @Transient val uid: String = UUID.randomUUID().toString().take(8),
) {
    /** Un esercizio è pronto per la generazione del documento solo se ha entrambi i frame. */
    val pronto: Boolean
        get() = !frameStart.isNullOrBlank() && !frameFinish.isNullOrBlank()
}
