package com.pyttrainer.android.dati

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * DTO del payload "dati" restituito dalle varie funzioni di android_bridge.py
 * (vedi PythonBridge.kt). Un file a parte da Esercizio.kt perché qui sono
 * tutte forme di risposta, non entità di dominio riusate altrove nella UI.
 */

/** carica() — esercizi del bundle già puntati ai frame estratti nella cartella di lavoro. */
@Serializable
data class RisultatoCaricaScheda(
    val esercizi: List<Esercizio>,
    @SerialName("cartella_lavoro") val cartellaLavoro: String,
)

/** Un singolo risultato di ricerca YouTube (search_youtube). */
@Serializable
data class VideoYoutube(
    val id: String,
    val title: String,
    val thumbnail: String? = null,
    val duration: Double? = null,
    @SerialName("webpage_url") val webpageUrl: String = "",
)

/** Un risultato scartato da filtra_risultati_pertinenti, con il motivo in italiano. */
@Serializable
data class VideoScartato(
    val video: VideoYoutube,
    val motivo: String,
)

/** cerca_video() — risultati pertinenti e scartati (con motivo), da mostrare entrambi all'utente. */
@Serializable
data class RisultatoCercaVideo(
    val pertinenti: List<VideoYoutube>,
    val scartati: List<VideoScartato>,
)

/** info_video() — durata e titolo di un video puntuale (get_video_info). */
@Serializable
data class InfoVideo(
    val duration: Double? = null,
    val title: String = "",
)

/** auto_estrai() — esercizio aggiornato (video/timestamp/frame) più il log delle scelte/scarti. */
@Serializable
data class RisultatoAutoEstrai(
    val esercizio: Esercizio,
    val log: List<String> = emptyList(),
)

/** genera_documento() — esito di create_workout_document. */
@Serializable
data class RisultatoGenerazioneDocumento(
    @SerialName("document_id") val documentId: String,
    val url: String,
    @SerialName("esercizi_inseriti") val eserciziInseriti: List<String> = emptyList(),
)

/** aggiorna_media() — esito di update_exercise_media: i due nuovi frame sostituiti nel documento. */
@Serializable
data class RisultatoAggiornaMedia(
    @SerialName("document_id") val documentId: String,
    val esercizio: String,
    @SerialName("frame_start") val frameStart: String,
    @SerialName("frame_finish") val frameFinish: String,
)

/** Una voce dello stato di ripresa (un esercizio già inserito nel documento). */
@Serializable
data class StatoEsercizioVoce(
    val nome: String,
    val slug: String,
    @SerialName("named_range_id") val namedRangeId: String,
    val gruppo: String = "",
)

/** stato_generazione() — contenuto di state.json, per l'avanzamento della generazione. */
@Serializable
data class StatoGenerazione(
    @SerialName("doc_id") val docId: String,
    val titolo: String,
    val esercizi: List<StatoEsercizioVoce> = emptyList(),
)
