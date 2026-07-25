package com.pyttrainer.android.ui.esercizio

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.pyttrainer.android.R
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.dati.VideoYoutube
import com.pyttrainer.android.ui.comune.EventoUi
import com.pyttrainer.android.ui.comune.formattaDurata
import java.io.File
import androidx.compose.runtime.collectAsState

/**
 * Dettaglio di un esercizio (Fase 4): copre quel che nel desktop sta dentro
 * l'expander di ogni esercizio (ricerca video, timestamp, estrazione frame,
 * campi testuali, ritaglio).
 *
 * Non è la sorgente di verità: [onSalva] è l'unico modo in cui le modifiche
 * tornano a SchedaViewModel (mai un accesso diretto da qui).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EsercizioScreen(
    esercizioIniziale: Esercizio,
    cartellaFrames: String?,
    /** Id del documento Google già generato per questa scheda, o null: abilita la correzione mirata (Fase 7). */
    docId: String?,
    /** Percorso di state.json nel bundle: richiesto da PythonBridge.aggiornaMedia. */
    percorsoStato: String?,
    onIndietro: () -> Unit,
    onSalva: (Esercizio, persistiCheckpoint: Boolean) -> Unit,
    onRitagliaClick: (tipo: String, percorso: String) -> Unit,
    onPlayerClick: (Esercizio) -> Unit,
) {
    val testi = EsercizioTesti(
        nomeVuoto = stringResource(R.string.esercizio_nome_vuoto_per_ricerca),
        nessunRisultato = stringResource(R.string.esercizio_nessun_risultato),
        cartellaNonPronta = stringResource(R.string.esercizio_cartella_non_pronta),
        timestampNonValidi = stringResource(R.string.esercizio_ts_errore),
        estrazioneOk = stringResource(R.string.esercizio_estrazione_ok),
        estrazioneSenzaVideo = stringResource(R.string.esercizio_estrazione_senza_video),
        erroreGenerico = stringResource(R.string.errore_sconosciuto),
        correzioneOk = stringResource(R.string.esercizio_correzione_ok),
    )
    val viewModel: EsercizioViewModel = viewModel(
        key = esercizioIniziale.uid,
        factory = EsercizioViewModel.factory(esercizioIniziale, cartellaFrames, testi),
    )
    val stato by viewModel.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    var foglioCorrezioneAperto by remember { mutableStateOf(false) }

    LaunchedEffect(viewModel) {
        viewModel.eventi.collect { evento ->
            when (evento) {
                is EventoUi.Errore -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.Info -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.EsercizioRimosso -> Unit // non emesso da questo schermo
            }
        }
    }

    // Riallinea i campi media della bozza locale ogni volta che quelli in
    // SchedaViewModel cambiano per una via che non passa da questo schermo
    // (cattura nel player, correzione mirata): esercizioIniziale è
    // ricalcolato fresco a ogni ricomposizione da MainActivity, ma il
    // ViewModel esiste già (stessa voce di backstack) quindi il suo
    // costruttore/factory non viene richiamato. Vedi EsercizioViewModel.sincronizzaMediaEsterni.
    LaunchedEffect(esercizioIniziale) {
        viewModel.sincronizzaMediaEsterni(esercizioIniziale)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.esercizio_titolo_dettaglio)) },
                navigationIcon = {
                    IconButton(onClick = {
                        onSalva(viewModel.bozzaCorrente(), false)
                        onIndietro()
                    }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.azione_indietro))
                    }
                },
                actions = {
                    IconButton(onClick = { onSalva(viewModel.bozzaCorrente(), true) }) {
                        Icon(Icons.Default.Check, contentDescription = stringResource(R.string.esercizio_pulsante_salva_desc))
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

            // --- Dettagli testuali -------------------------------------------------
            Text(stringResource(R.string.esercizio_sezione_dettagli), style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                value = stato.bozza.nome,
                onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(nome = valore) } },
                label = { Text(stringResource(R.string.campo_nome)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = stato.bozza.spiegazione,
                onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(spiegazione = valore) } },
                label = { Text(stringResource(R.string.campo_spiegazione)) },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = stato.bozza.note,
                onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(note = valore) } },
                label = { Text(stringResource(R.string.campo_note)) },
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = stato.bozza.ripetizioni,
                    onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(ripetizioni = valore) } },
                    label = { Text(stringResource(R.string.campo_ripetizioni)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = stato.bozza.recupero,
                    onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(recupero = valore) } },
                    label = { Text(stringResource(R.string.campo_recupero)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
            }
            OutlinedTextField(
                value = stato.bozza.gruppo,
                onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(gruppo = valore) } },
                label = { Text(stringResource(R.string.campo_gruppo)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            HorizontalDivider()

            // --- Ricerca video -------------------------------------------------------
            Text(stringResource(R.string.esercizio_sezione_ricerca), style = MaterialTheme.typography.titleMedium)
            OutlinedButton(
                onClick = viewModel::cercaVideo,
                enabled = !stato.ricercaInCorso,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.esercizio_pulsante_cerca))
            }
            if (stato.ricercaInCorso) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    Text(stringResource(R.string.esercizio_ricerca_in_corso))
                }
            }
            if (stato.risultatiRicerca.isNotEmpty()) {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(stato.risultatiRicerca, key = { it.id }) { video ->
                        RisultatoVideoCard(
                            video = video,
                            selezionato = stato.bozza.videoUrl == video.webpageUrl,
                            onClick = { viewModel.selezionaVideo(video) },
                        )
                    }
                }
            }
            if (stato.videoScartati.isNotEmpty()) {
                TextButton(onClick = { viewModel.impostaSezioneScartatiAperta(!stato.sezioneScartatiAperta) }) {
                    Text(stringResource(R.string.esercizio_video_scartati_titolo, stato.videoScartati.size))
                    Icon(
                        imageVector = if (stato.sezioneScartatiAperta) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                    )
                }
                AnimatedVisibility(visible = stato.sezioneScartatiAperta) {
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        stato.videoScartati.forEach { scartato ->
                            Text(
                                text = "${scartato.video.title} — ${scartato.motivo}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
            OutlinedTextField(
                value = stato.bozza.videoUrl,
                onValueChange = { valore -> viewModel.aggiornaBozza { it.copy(videoUrl = valore) } },
                label = { Text(stringResource(R.string.esercizio_url_manuale_label)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            HorizontalDivider()

            // --- Timestamp ed estrazione ----------------------------------------------
            Text(stringResource(R.string.esercizio_sezione_timestamp), style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = stato.tsStartTesto,
                    onValueChange = viewModel::impostaTsStartTesto,
                    label = { Text(stringResource(R.string.esercizio_ts_start_label)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    isError = stato.timestampNonValidi,
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = stato.tsFinishTesto,
                    onValueChange = viewModel::impostaTsFinishTesto,
                    label = { Text(stringResource(R.string.esercizio_ts_finish_label)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    isError = stato.timestampNonValidi,
                    modifier = Modifier.weight(1f),
                )
            }
            if (stato.timestampNonValidi) {
                Text(
                    text = stringResource(R.string.esercizio_ts_errore),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            OutlinedButton(
                onClick = { viewModel.autoEstrai(onSalva) },
                enabled = !stato.estrazioneInCorso && !stato.timestampNonValidi,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.esercizio_pulsante_estrai))
            }
            if (stato.estrazioneInCorso) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    Text(stringResource(R.string.esercizio_estrazione_in_corso))
                }
            }
            if (stato.logEstrazione.isNotEmpty()) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(stringResource(R.string.esercizio_log_titolo), fontWeight = FontWeight.Medium)
                        stato.logEstrazione.forEach { riga ->
                            Text(text = riga, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            // --- Anteprime frame --------------------------------------------------
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                AnteprimaFrame(
                    modifier = Modifier.weight(1f),
                    etichetta = stringResource(R.string.esercizio_frame_start_label),
                    percorso = stato.bozza.frameStart,
                    onRitagliaClick = { percorso -> onRitagliaClick("start", percorso) },
                )
                AnteprimaFrame(
                    modifier = Modifier.weight(1f),
                    etichetta = stringResource(R.string.esercizio_frame_finish_label),
                    percorso = stato.bozza.frameFinish,
                    onRitagliaClick = { percorso -> onRitagliaClick("finish", percorso) },
                )
            }

            OutlinedButton(
                onClick = { onPlayerClick(stato.bozza) },
                enabled = stato.bozza.videoUrl.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.PlayCircle, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text(stringResource(R.string.esercizio_pulsante_player))
            }

            // --- Correzione mirata (Fase 7) ---------------------------------------
            // Visibile solo se esiste già un documento generato per questa scheda:
            // sostituisce i due frame di QUESTO esercizio nel documento senza
            // rigenerarlo (PythonBridge.aggiornaMedia).
            if (docId != null && percorsoStato != null) {
                OutlinedButton(
                    onClick = { foglioCorrezioneAperto = true },
                    enabled = !stato.correzioneInCorso,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Default.Edit, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(stringResource(R.string.esercizio_pulsante_correzione_mirata))
                }
                if (stato.correzioneInCorso) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp))
                        Text(stringResource(R.string.esercizio_correzione_in_corso))
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }

    if (foglioCorrezioneAperto && docId != null && percorsoStato != null) {
        CorrezioneMirataBottomSheet(
            videoUrlIniziale = stato.bozza.videoUrl,
            cartellaFrames = cartellaFrames,
            onAnnulla = { foglioCorrezioneAperto = false },
            onConferma = { nuovoUrl, nuovoTsStart, nuovoTsFinish ->
                viewModel.correzioneMirata(
                    docId = docId,
                    statePath = percorsoStato,
                    outputDir = cartellaFrames ?: "",
                    nuovoVideoUrl = nuovoUrl,
                    nuovoTsStart = nuovoTsStart,
                    nuovoTsFinish = nuovoTsFinish,
                    accessToken = GestoreAccessoGoogle::tokenFresco,
                    onCorrezioneCompletata = onSalva,
                )
                foglioCorrezioneAperto = false
            },
        )
    }
}

/**
 * Foglio modale di correzione mirata (Fase 7): nuovo URL video e/o nuovi
 * timestamp per QUESTO esercizio, senza toccare gli altri campi né gli
 * altri esercizi del documento già generato.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CorrezioneMirataBottomSheet(
    videoUrlIniziale: String,
    cartellaFrames: String?,
    onAnnulla: () -> Unit,
    onConferma: (videoUrl: String, tsStart: Double?, tsFinish: Double?) -> Unit,
) {
    var url by remember { mutableStateOf(videoUrlIniziale) }
    var tsStartTesto by remember { mutableStateOf("") }
    var tsFinishTesto by remember { mutableStateOf("") }
    val statoFoglio = rememberModalBottomSheetState()

    ModalBottomSheet(onDismissRequest = onAnnulla, sheetState = statoFoglio) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(stringResource(R.string.correzione_mirata_titolo), style = MaterialTheme.typography.titleMedium)
            Text(
                stringResource(R.string.correzione_mirata_spiegazione),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text(stringResource(R.string.esercizio_url_manuale_label)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = tsStartTesto,
                    onValueChange = { tsStartTesto = it },
                    label = { Text(stringResource(R.string.esercizio_ts_start_label)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = tsFinishTesto,
                    onValueChange = { tsFinishTesto = it },
                    label = { Text(stringResource(R.string.esercizio_ts_finish_label)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.weight(1f),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = onAnnulla, modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.azione_annulla))
                }
                Button(
                    onClick = {
                        onConferma(url, tsStartTesto.trim().toDoubleOrNull(), tsFinishTesto.trim().toDoubleOrNull())
                    },
                    enabled = url.isNotBlank() && cartellaFrames != null,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.azione_conferma))
                }
            }
        }
    }
}

@Composable
private fun RisultatoVideoCard(
    video: VideoYoutube,
    selezionato: Boolean,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        modifier = Modifier
            .width(160.dp)
            .then(
                if (selezionato) {
                    Modifier.border(2.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(12.dp))
                } else {
                    Modifier
                }
            ),
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            AsyncImage(
                model = video.thumbnail,
                contentDescription = video.title,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(90.dp),
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = video.title, style = MaterialTheme.typography.bodySmall, maxLines = 2)
            Text(
                text = formattaDurata(video.duration),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun AnteprimaFrame(
    etichetta: String,
    percorso: String?,
    onRitagliaClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Text(text = etichetta, style = MaterialTheme.typography.labelLarge)
        if (percorso.isNullOrBlank()) {
            Card(modifier = Modifier.fillMaxWidth().height(120.dp)) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(8.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = stringResource(R.string.esercizio_frame_assente),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column {
                    AsyncImage(
                        model = File(percorso),
                        contentDescription = etichetta,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(120.dp),
                    )
                    TextButton(
                        onClick = { onRitagliaClick(percorso) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Icon(Icons.Default.ContentCut, contentDescription = null)
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(stringResource(R.string.esercizio_pulsante_ritaglia_desc))
                    }
                }
            }
        }
    }
}
