package com.pyttrainer.android.video

import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import java.io.FileOutputStream

/**
 * Backend nativo di estrazione frame: sostituisce ffmpeg (assente su
 * Android). Registrato una sola volta in PytTrainerApplication.onCreate()
 * tramite PythonBridge.registraBackendFrameNativo(), che a sua volta chiama
 * android_bridge.registra_backend_frame(), che chiama
 * video_helper.imposta_backend_frame(): da lì in poi ogni chiamata Python a
 * extract_frame() (quindi anche extract_start_finish_frames() e
 * scegli_ed_estrai()) delega a questa classe invece che a ffmpeg, con la
 * stessa identica firma di contratto (stream_url, timestamp_seconds,
 * output_path) -> str.
 *
 * Chiamata direttamente da Python (Chaquopy espone gli oggetti Kotlin/Java
 * passati a Python come attributi chiamabili): i tipi di ingresso/uscita
 * restano quindi volutamente semplici (String/Double/String), mai oggetti
 * Android complessi.
 */
class EstrattoreFrameNativo {

    /**
     * Estrae il frame più vicino a [timestampSecondi] dallo stream indicato e
     * lo scrive come JPEG (qualità 90) in [percorsoOutput].
     *
     * @return [percorsoOutput], per rispettare lo stesso contratto di
     *   _extract_frame_ffmpeg lato Python (scrive il file e ne restituisce il
     *   percorso).
     * @throws IllegalStateException se MediaMetadataRetriever non riesce a
     *   decodificare un frame all'istante richiesto: video_helper.extract_frame()
     *   la intercetta comunque e la riavvolge in FrameExtractionError prima
     *   che l'errore arrivi all'utente (vedi android_bridge.risposta_json).
     */
    fun estrai(streamUrl: String, timestampSecondi: Double, percorsoOutput: String): String {
        val retriever = MediaMetadataRetriever()
        try {
            // Mappa di header HTTP vuota: lo stream muxato risolto da yt-dlp
            // (vedi android_bridge.FORMATO_ANDROID) è già un URL diretto
            // interrogabile senza intestazioni aggiuntive.
            retriever.setDataSource(streamUrl, mapOf<String, String>())

            val timestampMicrosecondi = (timestampSecondi * 1_000_000).toLong()
            val frame: Bitmap = retriever.getFrameAtTime(
                timestampMicrosecondi,
                MediaMetadataRetriever.OPTION_CLOSEST,
            ) ?: throw IllegalStateException(
                "Impossibile estrarre il frame al secondo $timestampSecondi dallo stream indicato: " +
                    "MediaMetadataRetriever ha restituito un frame nullo."
            )

            FileOutputStream(percorsoOutput).use { output ->
                frame.compress(Bitmap.CompressFormat.JPEG, 90, output)
            }
            frame.recycle()

            return percorsoOutput
        } finally {
            retriever.release()
        }
    }
}
