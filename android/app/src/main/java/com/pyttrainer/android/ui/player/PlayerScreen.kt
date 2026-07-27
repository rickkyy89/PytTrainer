package com.pyttrainer.android.ui.player

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.pyttrainer.android.R
import com.pyttrainer.android.ui.comune.formattaPosizionePlayer
import kotlinx.coroutines.delay

/**
 * Anteprima del video dimostrativo con media3/ExoPlayer.
 *
 * [url] è la pagina YouTube dell'esercizio, non uno stream riproducibile: la
 * conversione la fa [PlayerViewModel] tramite yt-dlp. Lo scopo di questa
 * schermata non è "guardare il video" ma scegliere i fotogrammi giusti, per
 * questo sotto al player c'è sempre la posizione corrente anche in secondi
 * decimali, nello stesso formato dei campi Timestamp START/FINISH.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(url: String, onIndietro: () -> Unit) {
    val testi = PlayerTesti(erroreGenerico = stringResource(R.string.errore_sconosciuto))
    val viewModel: PlayerViewModel = viewModel(factory = PlayerViewModel.factory(url, testi))
    val stato by viewModel.stato.collectAsState()

    // Errore segnalato da ExoPlayer durante la riproduzione (distinto da quello
    // di risoluzione dello stream): tenuto qui perché è un fatto del lettore,
    // che vive nella UI, non del ViewModel.
    var erroreRiproduzione by remember { mutableStateOf<String?>(null) }

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
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            val messaggioErrore = erroreRiproduzione ?: stato.errore
            when {
                stato.risoluzioneInCorso -> {
                    CircularProgressIndicator()
                    Text(
                        text = stringResource(R.string.player_risoluzione_in_corso),
                        style = MaterialTheme.typography.bodyMedium,
                        textAlign = TextAlign.Center,
                    )
                }

                messaggioErrore != null -> {
                    Text(
                        text = messaggioErrore,
                        color = MaterialTheme.colorScheme.error,
                        textAlign = TextAlign.Center,
                    )
                    Button(
                        onClick = {
                            // Gli URL prodotti da yt-dlp scadono dopo qualche ora:
                            // il rimedio giusto a un errore di riproduzione non è
                            // ritentare lo stesso URL ma risolverlo di nuovo.
                            erroreRiproduzione = null
                            viewModel.risolviStream()
                        }
                    ) {
                        Text(stringResource(R.string.player_pulsante_riprova))
                    }
                }

                stato.streamUrl != null -> LettoreVideo(
                    streamUrl = stato.streamUrl!!,
                    onErroreRiproduzione = { erroreRiproduzione = it },
                )
            }
        }
    }
}

/**
 * Il lettore vero e proprio. Separato dal resto della schermata perché ha un
 * ciclo di vita proprio: l'istanza di ExoPlayer va creata quando arriva lo
 * stream e RILASCIATA quando si lascia la schermata (tiene un codec hardware e
 * un socket: non rilasciarla si paga con codec esauriti dopo qualche apertura).
 */
@androidx.annotation.OptIn(UnstableApi::class)
@Composable
private fun ColumnScope.LettoreVideo(streamUrl: String, onErroreRiproduzione: (String) -> Unit) {
    val contesto = LocalContext.current

    val lettore = remember(streamUrl) {
        ExoPlayer.Builder(contesto).build().apply {
            setMediaItem(MediaItem.fromUri(streamUrl))
            prepare()
            playWhenReady = true
        }
    }

    DisposableEffect(lettore) {
        val ascoltatore = object : Player.Listener {
            override fun onPlayerError(errore: PlaybackException) {
                onErroreRiproduzione(errore.message ?: errore.errorCodeName)
            }
        }
        lettore.addListener(ascoltatore)
        onDispose {
            lettore.removeListener(ascoltatore)
            lettore.release()
        }
    }

    // Senza questo la riproduzione continua (audio compreso) quando l'app
    // finisce in background: la schermata resta nello stack, quindi il lettore
    // non viene rilasciato e nessuno lo ferma.
    val proprietarioCicloDiVita = LocalLifecycleOwner.current
    DisposableEffect(proprietarioCicloDiVita, lettore) {
        val osservatore = LifecycleEventObserver { _, evento ->
            if (evento == Lifecycle.Event.ON_STOP) lettore.pause()
        }
        proprietarioCicloDiVita.lifecycle.addObserver(osservatore)
        onDispose { proprietarioCicloDiVita.lifecycle.removeObserver(osservatore) }
    }

    // ExoPlayer non espone la posizione come flusso osservabile: va letta a
    // intervalli. 200 ms è abbastanza fitto da sembrare continuo e abbastanza
    // rado da non far ricomporre inutilmente.
    var posizioneMillisecondi by remember { mutableLongStateOf(0L) }
    LaunchedEffect(lettore) {
        while (true) {
            posizioneMillisecondi = lettore.currentPosition
            delay(200)
        }
    }

    // Il video prende lo spazio che AVANZA (weight), non tutto quello che
    // vorrebbe: su tablet in orizzontale un 16:9 a piena larghezza è più alto
    // dello schermo e spingerebbe fuori vista la posizione corrente, che è il
    // motivo per cui questa schermata esiste. matchHeightConstraintsFirst fa
    // ricavare la larghezza dall'altezza disponibile invece del contrario.
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .weight(1f),
        contentAlignment = Alignment.Center,
    ) {
        AndroidView(
            factory = { contestoVista ->
                PlayerView(contestoVista).apply {
                    player = lettore
                    useController = true
                    contentDescription = contestoVista.getString(R.string.player_descrizione)
                }
            },
            modifier = Modifier.aspectRatio(16f / 9f, matchHeightConstraintsFirst = true),
        )
    }

    Text(
        text = stringResource(R.string.player_posizione, formattaPosizionePlayer(posizioneMillisecondi)),
        style = MaterialTheme.typography.titleMedium,
    )
    Text(
        text = stringResource(R.string.player_suggerimento_timestamp),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center,
    )
}
