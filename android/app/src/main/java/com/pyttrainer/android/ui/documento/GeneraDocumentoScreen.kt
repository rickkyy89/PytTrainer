package com.pyttrainer.android.ui.documento

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.R

/**
 * Segnaposto (Fase 3): la generazione vera del Google Doc — accesso Google
 * (AppAuth), chiamata a PythonBridge.generaDocumento, avanzamento/ripresa
 * via PythonBridge.statoGenerazione — arriva in una fase successiva. Questa
 * schermata esiste solo perché SchedaScreen deve poter navigare da qualche
 * parte quando l'utente preme "Genera Google Doc".
 *
 * TODO(fase successiva): collegare l'accesso Google e PythonBridge.generaDocumento/aggiornaMedia.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GeneraDocumentoScreen(onIndietro: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.genera_documento_titolo)) },
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
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.genera_documento_placeholder),
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
            )
        }
    }
}
