package com.pyttrainer.android.ui.ritaglio

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.pyttrainer.android.R
import com.pyttrainer.android.ui.comune.EventoUi
import java.io.File
import androidx.compose.runtime.collectAsState

/**
 * Ritaglio di un frame (Fase 6): quattro slider (0-45%, con i vincoli di
 * video_helper.box_ritaglio verificati anche lato Kotlin prima di chiamare
 * Python) e anteprima live del box calcolato da PythonBridge.boxRitaglio
 * (pura matematica, non tocca il file finché non si preme "Applica").
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RitaglioScreen(
    percorso: String,
    tipo: String,
    onIndietro: () -> Unit,
    onFrameModificato: () -> Unit,
) {
    val testi = RitaglioTesti(
        ritaglioApplicato = stringResource(R.string.ritaglio_applicato),
        originaleRipristinato = stringResource(R.string.ritaglio_ripristinato),
        erroreGenerico = stringResource(R.string.errore_sconosciuto),
    )
    val viewModel: RitaglioViewModel = viewModel(
        key = "$percorso:$tipo",
        factory = RitaglioViewModel.factory(percorso, testi),
    )
    val stato by viewModel.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val contesto = LocalContext.current

    LaunchedEffect(viewModel) {
        viewModel.eventi.collect { evento ->
            when (evento) {
                is EventoUi.Errore -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.Info -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.EsercizioRimosso -> Unit // non emesso da questo schermo
            }
        }
    }

    val titoloEtichetta = if (tipo == "finish") {
        stringResource(R.string.esercizio_frame_finish_label)
    } else {
        stringResource(R.string.esercizio_frame_start_label)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("${stringResource(R.string.ritaglio_titolo)} · $titoloEtichetta") },
                navigationIcon = {
                    IconButton(onClick = onIndietro) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.azione_indietro))
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Spacer(modifier = Modifier.height(4.dp))

            if (stato.larghezzaOriginale > 0 && stato.altezzaOriginale > 0) {
                BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
                    val altezzaVisualizzata = maxWidth * stato.altezzaOriginale / stato.larghezzaOriginale
                    val richiestaImmagine = ImageRequest.Builder(contesto)
                        .data(File(stato.percorso))
                        .memoryCacheKey("${stato.percorso}#${stato.versioneImmagine}")
                        .diskCacheKey("${stato.percorso}#${stato.versioneImmagine}")
                        .build()
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(altezzaVisualizzata),
                    ) {
                        AsyncImage(
                            model = richiestaImmagine,
                            contentDescription = stringResource(R.string.ritaglio_anteprima_desc),
                            contentScale = ContentScale.Fit,
                            modifier = Modifier.fillMaxSize(),
                        )
                        val box = stato.boxPixel
                        if (box != null && box.size == 4) {
                            val coloreBox = MaterialTheme.colorScheme.primary
                            Canvas(modifier = Modifier.fillMaxSize()) {
                                val scalaX = size.width / stato.larghezzaOriginale.toFloat()
                                val scalaY = size.height / stato.altezzaOriginale.toFloat()
                                val sinistraPx = box[0] * scalaX
                                val altoPx = box[1] * scalaY
                                val destraPx = box[2] * scalaX
                                val bassoPx = box[3] * scalaY
                                drawRect(
                                    color = coloreBox,
                                    topLeft = Offset(sinistraPx, altoPx),
                                    size = Size(destraPx - sinistraPx, bassoPx - altoPx),
                                    style = Stroke(width = 3.dp.toPx()),
                                )
                            }
                        }
                    }
                }
            }

            SliderConEtichetta(
                etichetta = stringResource(R.string.ritaglio_slider_sinistra),
                valore = stato.sinistra,
                onValueChange = viewModel::impostaSinistra,
            )
            SliderConEtichetta(
                etichetta = stringResource(R.string.ritaglio_slider_alto),
                valore = stato.alto,
                onValueChange = viewModel::impostaAlto,
            )
            SliderConEtichetta(
                etichetta = stringResource(R.string.ritaglio_slider_destra),
                valore = stato.destra,
                onValueChange = viewModel::impostaDestra,
            )
            SliderConEtichetta(
                etichetta = stringResource(R.string.ritaglio_slider_basso),
                valore = stato.basso,
                onValueChange = viewModel::impostaBasso,
            )

            if (stato.sommaOrizzontaleNonValida) {
                Text(
                    text = stringResource(R.string.ritaglio_errore_somma_orizzontale),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (stato.sommaVerticaleNonValida) {
                Text(
                    text = stringResource(R.string.ritaglio_errore_somma_verticale),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Button(
                onClick = { viewModel.applicaRitaglio(onFrameModificato) },
                enabled = stato.validoPerApplicare && !stato.operazioneInCorso,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.ritaglio_pulsante_applica))
            }
            OutlinedButton(
                onClick = { viewModel.ripristinaOriginale(onFrameModificato) },
                enabled = stato.haBackup && !stato.operazioneInCorso,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.ritaglio_pulsante_ripristina))
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
private fun SliderConEtichetta(
    etichetta: String,
    valore: Float,
    onValueChange: (Float) -> Unit,
) {
    Column {
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(text = etichetta, style = MaterialTheme.typography.bodyMedium)
            Text(text = "${valore.toInt()}%", style = MaterialTheme.typography.bodyMedium)
        }
        Slider(
            value = valore,
            onValueChange = onValueChange,
            valueRange = 0f..45f,
            steps = 44,
        )
    }
}
