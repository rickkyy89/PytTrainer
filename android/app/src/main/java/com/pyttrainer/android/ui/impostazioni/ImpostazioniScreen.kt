package com.pyttrainer.android.ui.impostazioni

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.R
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import kotlinx.coroutines.launch

/**
 * Accesso Google, package name e impronta SHA-1 (Fase 7): dati che
 * l'utente deve inserire in Google Cloud Console per registrare il client
 * OAuth "Android" (redirect com.pyttrainer.android:/oauth2redirect, scope
 * documents + drive.file). Non automatizzabile: qui ci limitiamo a
 * mostrarli in chiaro, pronti da copiare.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImpostazioniScreen(onIndietro: () -> Unit) {
    val stato by GestoreAccessoGoogle.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val ambitoCoroutine = rememberCoroutineScope()

    val lanciatoreAccesso = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { risultato ->
        ambitoCoroutine.launch {
            GestoreAccessoGoogle.gestisciRispostaAccesso(risultato.data).onFailure { errore ->
                snackbarHostState.showSnackbar(errore.message ?: "Accesso Google non riuscito.")
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.impostazioni_titolo)) },
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
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(stringResource(R.string.impostazioni_sezione_google), style = MaterialTheme.typography.titleMedium)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = if (stato.connesso) Icons.Default.CloudDone else Icons.Default.CloudOff,
                            contentDescription = null,
                            tint = if (stato.connesso) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = if (stato.connesso) {
                                stringResource(R.string.scheda_google_connesso)
                            } else {
                                stringResource(R.string.scheda_google_non_connesso)
                            },
                        )
                    }
                    if (stato.connesso) {
                        OutlinedButton(onClick = GestoreAccessoGoogle::esci, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(R.string.impostazioni_esci))
                        }
                    } else {
                        Button(
                            onClick = { GestoreAccessoGoogle.avviaAccesso(lanciatoreAccesso) },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.impostazioni_accedi))
                        }
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        stringResource(R.string.impostazioni_sezione_configurazione_oauth),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        stringResource(R.string.impostazioni_configurazione_oauth_spiegazione),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    RigaValoreCopiabile(
                        etichetta = stringResource(R.string.impostazioni_package_name),
                        // Fisso: android.defaultConfig.applicationId in app/build.gradle.kts.
                        // (BuildConfig non è abilitato in questo modulo: niente buildFeatures.buildConfig
                        // in più solo per una stringa già nota e fissa a build time.)
                        valore = "com.pyttrainer.android",
                    )
                    RigaValoreCopiabile(
                        etichetta = stringResource(R.string.impostazioni_impronta_sha1),
                        valore = "59:50:55:5A:D7:D4:FB:B1:43:02:8F:D5:88:25:A4:31:89:5A:A0:86",
                    )
                }
            }
        }
    }
}

@Composable
private fun RigaValoreCopiabile(etichetta: String, valore: String) {
    Column {
        Text(text = etichetta, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Medium)
        Text(text = valore, style = MaterialTheme.typography.bodySmall)
    }
}
