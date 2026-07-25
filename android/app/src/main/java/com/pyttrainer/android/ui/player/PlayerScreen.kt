package com.pyttrainer.android.ui.player

import android.graphics.Bitmap
import android.view.LayoutInflater
import android.view.TextureView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.FastForward
import androidx.compose.material.icons.filled.FastRewind
import androidx.compose.material.icons.filled.Forward5
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay5
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.pyttrainer.android.R
import com.pyttrainer.android.ui.comune.EventoUi
import com.pyttrainer.android.ui.comune.formattaPosizioneMillisecondi
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.runtime.collectAsState

/**
 * Player video integrato (Fase 5): la funzione per cui esiste questa app. Su
 * telefono/tablet non si può passare da un'app all'altra come sul PC con due
 * schede del browser, quindi la ricerca del punto esatto del movimento
 * avviene qui dentro, con ExoPlayer (Media3) in una AndroidView configurata
 * con surface_type="texture_view" (vedi res/layout/visualizzatore_player.xml):
 * serve a poter leggere i pixel visibili, impossibile con una SurfaceView.
 *
 * Nota per chi tocca questo file: gli stream URL risolti da yt-dlp
 * (PythonBridge.streamUrl) scadono dopo qualche ora. Se la riproduzione
 * fallisce con un errore di rete a metà visione, l'unica via d'uscita è
 * ri-risolvere lo stream (PlayerViewModel.risolviStream()) e ripreparare
 * ExoPlayer con il nuovo URL mantenendo la posizione: è quello che fa
 * l'ascoltatore onPlayerError qui sotto, con un solo ri-tentativo automatico.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(
    url: String,
    nomeEsercizio: String,
    cartellaLavoro: String,
    frameStartIniziale: String?,
    frameFinishIniziale: String?,
    tsStartIniziale: Double?,
    tsFinishIniziale: Double?,
    onIndietro: () -> Unit,
    onConferma: (videoUrl: String, tsStart: Double?, tsFinish: Double?, frameStart: String?, frameFinish: String?) -> Unit,
) {
    val testi = PlayerTesti(
        streamErrore = stringResource(R.string.player_stream_errore),
        catturaOk = stringResource(R.string.player_cattura_ok),
        catturaFallita = stringResource(R.string.player_cattura_fallita),
        erroreGenerico = stringResource(R.string.errore_sconosciuto),
    )
    val viewModel: PlayerViewModel = viewModel(
        key = "$nomeEsercizio:$url",
        factory = PlayerViewModel.factory(
            url, nomeEsercizio, cartellaLavoro,
            frameStartIniziale, frameFinishIniziale, tsStartIniziale, tsFinishIniziale, testi,
        ),
    )
    val stato by viewModel.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val contesto = LocalContext.current
    val ambitoCoroutine = rememberCoroutineScope()

    LaunchedEffect(viewModel) {
        viewModel.eventi.collect { evento ->
            when (evento) {
                is EventoUi.Errore -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.Info -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.EsercizioRimosso -> Unit // non emesso da questo schermo
            }
        }
    }

    // --- ExoPlayer: un'istanza per l'intera vita dello schermo -------------
    val exoPlayer = remember { ExoPlayer.Builder(contesto).build().apply { playWhenReady = false } }
    var vistaPlayer by remember { mutableStateOf<PlayerView?>(null) }
    var posizioneMs by remember { mutableStateOf(0L) }
    var durataMs by remember { mutableStateOf(0L) }
    var inRiproduzione by remember { mutableStateOf(false) }
    var trascinamentoSlider by remember { mutableStateOf<Float?>(null) }
    var velocita by remember { mutableStateOf(1f) }
    var tentativiRipristino by remember { mutableStateOf(0) }

    DisposableEffect(Unit) {
        onDispose { exoPlayer.release() }
    }

    // Schermo sempre acceso mentre si guarda un video.
    val vista = LocalView.current
    DisposableEffect(Unit) {
        vista.keepScreenOn = true
        onDispose { vista.keepScreenOn = false }
    }

    // Pausa quando la schermata va in background (Home, cambio app, ...).
    val proprietarioCiclovita = LocalLifecycleOwner.current
    DisposableEffect(proprietarioCiclovita) {
        val osservatore = LifecycleEventObserver { _, evento ->
            if (evento == Lifecycle.Event.ON_PAUSE || evento == Lifecycle.Event.ON_STOP) {
                exoPlayer.pause()
            }
        }
        proprietarioCiclovita.lifecycle.addObserver(osservatore)
        onDispose { proprietarioCiclovita.lifecycle.removeObserver(osservatore) }
    }

    // (Ri)prepara ExoPlayer ogni volta che lo stream viene (ri)risolto,
    // mantenendo posizione e stato play/pausa precedenti: copre sia il primo
    // caricamento sia il ritentativo dopo uno stream scaduto.
    LaunchedEffect(stato.versioneStream) {
        val nuovoUrl = stato.streamUrl ?: return@LaunchedEffect
        val posizionePrecedente = exoPlayer.currentPosition.coerceAtLeast(0)
        val stavaRiproducendo = exoPlayer.playWhenReady
        exoPlayer.setMediaItem(MediaItem.fromUri(nuovoUrl))
        exoPlayer.prepare()
        if (posizionePrecedente > 0) exoPlayer.seekTo(posizionePrecedente)
        exoPlayer.playWhenReady = stavaRiproducendo
        exoPlayer.setPlaybackSpeed(velocita)
    }

    // Un solo ritentativo automatico su errore di riproduzione: oltre non
    // insiste più, l'errore resta visibile in una Snackbar.
    DisposableEffect(exoPlayer) {
        val ascoltatore = object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                if (tentativiRipristino < 1) {
                    tentativiRipristino += 1
                    viewModel.risolviStream()
                } else {
                    ambitoCoroutine.launch { snackbarHostState.showSnackbar(testi.streamErrore) }
                }
            }
        }
        exoPlayer.addListener(ascoltatore)
        onDispose { exoPlayer.removeListener(ascoltatore) }
    }

    // ExoPlayer non spinge posizione/stato in Compose da solo: un polling
    // leggero (100ms) basta per un orologio fluido a occhio.
    LaunchedEffect(exoPlayer) {
        while (isActive) {
            posizioneMs = exoPlayer.currentPosition.coerceAtLeast(0)
            durataMs = exoPlayer.duration.coerceAtLeast(0)
            inRiproduzione = exoPlayer.isPlaying
            delay(100)
        }
    }

    val fps = exoPlayer.videoFormat?.frameRate?.takeIf { it > 0f }
    val passoFotogrammaMs = if (fps != null) (1000f / fps).toLong().coerceAtLeast(1L) else 33L

    suspend fun bitmapVisibile(): Bitmap? = withContext(Dispatchers.Main) {
        (vistaPlayer?.videoSurfaceView as? TextureView)?.bitmap
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.player_titolo)) },
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
                .verticalScroll(rememberScrollState()),
        ) {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
                AndroidView(
                    factory = { ctx ->
                        (LayoutInflater.from(ctx).inflate(R.layout.visualizzatore_player, null) as PlayerView).apply {
                            player = exoPlayer
                            useController = false
                            vistaPlayer = this
                        }
                    },
                    modifier = Modifier.fillMaxSize(),
                )
                if (stato.risoluzioneInCorso) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Color.White)
                    }
                }
            }

            if (stato.erroreStream != null) {
                Card(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(stato.erroreStream ?: testi.streamErrore, color = MaterialTheme.colorScheme.error)
                        OutlinedButton(onClick = viewModel::risolviStream) {
                            Text(stringResource(R.string.player_riprova))
                        }
                    }
                }
            }

            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    text = if (durataMs > 0) {
                        "${formattaPosizioneMillisecondi(posizioneMs)} / ${formattaPosizioneMillisecondi(durataMs)}"
                    } else {
                        formattaPosizioneMillisecondi(posizioneMs)
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
                Slider(
                    value = trascinamentoSlider ?: posizioneMs.toFloat(),
                    onValueChange = { trascinamentoSlider = it },
                    onValueChangeFinished = {
                        trascinamentoSlider?.let { exoPlayer.seekTo(it.toLong()) }
                        trascinamentoSlider = null
                    },
                    valueRange = 0f..durataMs.toFloat().coerceAtLeast(1f),
                    enabled = durataMs > 0,
                )

                Row(
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    ControlloIcona(Icons.Default.Replay5, stringResource(R.string.player_indietro_5s)) {
                        exoPlayer.seekTo((exoPlayer.currentPosition - 5_000).coerceAtLeast(0))
                    }
                    ControlloIcona(Icons.Default.FastRewind, stringResource(R.string.player_indietro_1s)) {
                        exoPlayer.seekTo((exoPlayer.currentPosition - 1_000).coerceAtLeast(0))
                    }
                    ControlloIcona(
                        icona = if (inRiproduzione) Icons.Default.Pause else Icons.Default.PlayArrow,
                        descrizione = stringResource(R.string.player_play_pausa),
                        grande = true,
                    ) { exoPlayer.playWhenReady = !exoPlayer.playWhenReady }
                    ControlloIcona(Icons.Default.FastForward, stringResource(R.string.player_avanti_1s)) {
                        exoPlayer.seekTo(exoPlayer.currentPosition + 1_000)
                    }
                    ControlloIcona(Icons.Default.Forward5, stringResource(R.string.player_avanti_5s)) {
                        exoPlayer.seekTo(exoPlayer.currentPosition + 5_000)
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(
                        onClick = { exoPlayer.seekTo((exoPlayer.currentPosition - passoFotogrammaMs).coerceAtLeast(0)) },
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.player_fotogramma_indietro)) }
                    OutlinedButton(
                        onClick = { exoPlayer.seekTo(exoPlayer.currentPosition + passoFotogrammaMs) },
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.player_fotogramma_avanti)) }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(0.25f, 0.5f, 1f).forEach { valore ->
                        FilterChip(
                            selected = velocita == valore,
                            onClick = {
                                velocita = valore
                                exoPlayer.setPlaybackSpeed(valore)
                            },
                            label = { Text("${valore}x") },
                        )
                    }
                }

                HorizontalDivider()

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    Button(
                        onClick = {
                            exoPlayer.pause()
                            val streamCorrente = stato.streamUrl ?: return@Button
                            viewModel.cattura("start", exoPlayer.currentPosition, streamCorrente, ::bitmapVisibile)
                        },
                        enabled = stato.streamUrl != null && !stato.catturaInCorso,
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.player_cattura_start)) }
                    Button(
                        onClick = {
                            exoPlayer.pause()
                            val streamCorrente = stato.streamUrl ?: return@Button
                            viewModel.cattura("finish", exoPlayer.currentPosition, streamCorrente, ::bitmapVisibile)
                        },
                        enabled = stato.streamUrl != null && !stato.catturaInCorso,
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.player_cattura_finish)) }
                }
                if (stato.catturaInCorso) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp))
                        Text(stringResource(R.string.player_cattura_in_corso))
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                    MiniaturaCatturata(
                        modifier = Modifier.weight(1f),
                        etichetta = stringResource(R.string.esercizio_frame_start_label),
                        percorso = stato.frameStart,
                        versione = stato.versioneFrameStart,
                    )
                    MiniaturaCatturata(
                        modifier = Modifier.weight(1f),
                        etichetta = stringResource(R.string.esercizio_frame_finish_label),
                        percorso = stato.frameFinish,
                        versione = stato.versioneFrameFinish,
                    )
                }

                Button(
                    onClick = { onConferma(url, stato.tsStart, stato.tsFinish, stato.frameStart, stato.frameFinish) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Default.Check, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(stringResource(R.string.player_conferma))
                }

                Spacer(modifier = Modifier.height(16.dp))
            }
        }
    }
}

@Composable
private fun ControlloIcona(
    icona: ImageVector,
    descrizione: String,
    grande: Boolean = false,
    onClick: () -> Unit,
) {
    IconButton(onClick = onClick, modifier = if (grande) Modifier.size(64.dp) else Modifier.size(48.dp)) {
        Icon(icona, contentDescription = descrizione, modifier = Modifier.size(if (grande) 40.dp else 26.dp))
    }
}

@Composable
private fun MiniaturaCatturata(
    etichetta: String,
    percorso: String?,
    versione: Long,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Text(text = etichetta, style = MaterialTheme.typography.labelLarge)
        if (percorso.isNullOrBlank()) {
            Card(modifier = Modifier.fillMaxWidth().height(90.dp)) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        text = stringResource(R.string.esercizio_frame_assente),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            val richiesta = ImageRequest.Builder(LocalContext.current)
                .data(File(percorso))
                .memoryCacheKey("$percorso#$versione")
                .diskCacheKey("$percorso#$versione")
                .build()
            Card(modifier = Modifier.fillMaxWidth()) {
                AsyncImage(
                    model = richiesta,
                    contentDescription = etichetta,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(90.dp),
                )
            }
        }
    }
}
