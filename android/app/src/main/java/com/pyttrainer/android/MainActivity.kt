package com.pyttrainer.android

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.pyttrainer.android.nav.Rotta
import com.pyttrainer.android.ui.documento.GeneraDocumentoScreen
import com.pyttrainer.android.ui.esercizio.EsercizioScreen
import com.pyttrainer.android.ui.player.PlayerScreen
import com.pyttrainer.android.ui.ritaglio.RitaglioScreen
import com.pyttrainer.android.ui.scheda.SchedaScreen
import com.pyttrainer.android.ui.scheda.SchedaViewModel
import com.pyttrainer.android.ui.theme.PytTrainerTheme

/**
 * Activity unica dell'app (Fase 3/4/6): ospita il NavHost con le rotte
 * tipizzate definite in [Rotta]. [SchedaViewModel] è creato una sola volta
 * qui, scoped all'Activity (sopravvive alla navigazione e alle rotazioni),
 * ed è l'unica sorgente di verità della lista esercizi: ogni schermata di
 * dettaglio (Esercizio, Ritaglio) legge/scrive attraverso di esso, mai una
 * copia propria.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Uri di un .scheda aperto da un'altra app (vedi gli intent-filter VIEW
        // nel manifest): se presente, va caricato subito all'avvio.
        val uriSchedaCondivisa = intent?.takeIf { it.action == Intent.ACTION_VIEW }?.data
        setContent {
            PytTrainerTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    PytTrainerApp(uriSchedaIniziale = uriSchedaCondivisa)
                }
            }
        }
    }
}

@Composable
private fun PytTrainerApp(uriSchedaIniziale: Uri? = null) {
    val contesto = LocalContext.current
    val schedaViewModel: SchedaViewModel = viewModel(
        factory = ViewModelProvider.AndroidViewModelFactory.getInstance(contesto.applicationContext as Application),
    )
    val statoScheda by schedaViewModel.stato.collectAsState()
    val navController = rememberNavController()

    LaunchedEffect(uriSchedaIniziale) {
        uriSchedaIniziale?.let(schedaViewModel::apriScheda)
    }

    NavHost(navController = navController, startDestination = Rotta.Scheda) {
        composable<Rotta.Scheda> {
            SchedaScreen(
                viewModel = schedaViewModel,
                onEsercizioClick = { uid -> navController.navigate(Rotta.Esercizio(uid)) },
                onGeneraDocumentoClick = { navController.navigate(Rotta.GeneraDocumento) },
            )
        }

        composable<Rotta.Esercizio> { backStackEntry ->
            val rotta: Rotta.Esercizio = backStackEntry.toRoute()
            val esercizio = statoScheda.esercizi.firstOrNull { it.uid == rotta.uid }
            if (esercizio == null) {
                // L'esercizio è sparito dalla lista (rimosso altrove) mentre questa
                // schermata era sullo stack: non c'è nulla da mostrare, si torna indietro.
                LaunchedEffect(Unit) { navController.popBackStack() }
            } else {
                EsercizioScreen(
                    esercizioIniziale = esercizio,
                    cartellaFrames = statoScheda.cartellaFrames,
                    onIndietro = { navController.popBackStack() },
                    onSalva = { aggiornato, persistiCheckpoint ->
                        schedaViewModel.aggiornaEsercizio(aggiornato, persistiCheckpoint)
                    },
                    onRitagliaClick = { tipo, percorso ->
                        navController.navigate(Rotta.Ritaglio(rotta.uid, tipo, percorso))
                    },
                    onPlayerClick = { url -> navController.navigate(Rotta.Player(url)) },
                )
            }
        }

        composable<Rotta.Ritaglio> { backStackEntry ->
            val rotta: Rotta.Ritaglio = backStackEntry.toRoute()
            RitaglioScreen(
                percorso = rotta.percorso,
                tipo = rotta.tipo,
                onIndietro = { navController.popBackStack() },
                onFrameModificato = { schedaViewModel.persistiCheckpointDopoRitaglio() },
            )
        }

        composable<Rotta.GeneraDocumento> {
            GeneraDocumentoScreen(
                esercizi = statoScheda.esercizi,
                titolo = statoScheda.titolo,
                cartellaLavoro = statoScheda.cartellaLavoro,
                gestoreAccessoGoogle = schedaViewModel.gestoreAccessoGoogle,
                onIndietro = { navController.popBackStack() },
                onDocumentoGenerato = { schedaViewModel.persistiCheckpointDopoGenerazione() },
            )
        }

        composable<Rotta.Player> { backStackEntry ->
            val rotta: Rotta.Player = backStackEntry.toRoute()
            PlayerScreen(url = rotta.url, onIndietro = { navController.popBackStack() })
        }
    }
}
