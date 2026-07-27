package com.pyttrainer.android

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.pyttrainer.android.python.EsitoAvvio
import com.pyttrainer.android.python.PythonBridge
import com.pyttrainer.android.video.EstrattoreFrameNativo

/**
 * Application di PytTrainer: avvia l'interprete Python (Chaquopy) una sola
 * volta per l'intero processo e registra subito il backend nativo di
 * estrazione frame (sostituisce ffmpeg, assente su Android), così ogni
 * schermata dell'app può usare [PythonBridge] senza doversi preoccupare
 * dell'inizializzazione.
 */
class PytTrainerApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Sostituisce ffmpeg con MediaMetadataRetriever: da questo momento in
        // poi video_helper.extract_frame() (e quindi scegli_ed_estrai(),
        // extract_start_finish_frames(), ecc.) usa il backend nativo per
        // qualunque chiamata Python, senza che il resto del codice Python se
        // ne accorga. L'esito (envelope JSON grezzo) viene tenuto da parte
        // solo per mostrarlo nella schermata di verifica del cablaggio.
        EsitoAvvio.rispostaRegistrazioneBackend =
            PythonBridge.registraBackendFrameNativo(EstrattoreFrameNativo())
    }
}
