package com.pyttrainer.android.ui.scheda

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import com.pyttrainer.android.R
import com.pyttrainer.android.dati.Esercizio

/**
 * Lista esercizi con riordino per trascinamento (sostituisce i pulsanti
 * su/giù del desktop) e rimozione con swipe, come richiesto per la
 * SchedaScreen (Fase 3).
 *
 * Riordino: tenendo premuta l'icona "maniglia" di una riga e trascinandola,
 * si sposta la riga scambiando posizione con quella sotto/sopra il dito non
 * appena il centro della riga trascinata supera il centro della riga
 * attraversata (soglia = metà riga, calcolata dai bound reali via
 * LazyListState.layoutInfo, non da un'altezza fissa presunta).
 */
@Composable
fun ListaEserciziRiordinabile(
    esercizi: List<Esercizio>,
    onEsercizioClick: (String) -> Unit,
    onRiordina: (indiceOrigine: Int, indiceDestinazione: Int) -> Unit,
    onRimuovi: (uid: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val statoLista = rememberLazyListState()
    var indiceTrascinato by remember { mutableStateOf<Int?>(null) }
    var offsetTrascinamento by remember { mutableFloatStateOf(0f) }

    // detectDragGesturesAfterLongPress() gira in un'unica coroutine avviata una
    // sola volta per riga (pointerInput è keyato sull'uid, stabile: non
    // riparte mai a ogni ricomposizione) e resta viva per TUTTI i trascinamenti
    // successivi su quella riga. Senza rememberUpdatedState, "esercizi" e
    // "onRiordina" catturati nella closure resterebbero congelati alla lista
    // vista al primo avvio: dopo un riordino precedente, un trascinamento
    // successivo sulla stessa riga calcolerebbe l'indice di partenza sulla
    // lista sbagliata.
    val eserciziAggiornati by rememberUpdatedState(esercizi)
    val onRiordinaAggiornato by rememberUpdatedState(onRiordina)

    LazyColumn(
        state = statoLista,
        modifier = modifier,
        contentPadding = PaddingValues(vertical = 4.dp),
    ) {
        itemsIndexed(esercizi, key = { _, esercizio -> esercizio.uid }) { indice, esercizio ->
            val questaRigaInTrascinamento = indiceTrascinato == indice
            RigaEsercizio(
                esercizio = esercizio,
                onClick = { onEsercizioClick(esercizio.uid) },
                onRimuovi = { onRimuovi(esercizio.uid) },
                modifier = Modifier
                    .graphicsLayer {
                        translationY = if (questaRigaInTrascinamento) offsetTrascinamento else 0f
                    }
                    .zIndex(if (questaRigaInTrascinamento) 1f else 0f),
                modificatoreManiglia = Modifier.pointerInput(esercizio.uid) {
                    detectDragGesturesAfterLongPress(
                        onDragStart = {
                            indiceTrascinato = eserciziAggiornati.indexOfFirst { it.uid == esercizio.uid }
                            offsetTrascinamento = 0f
                        },
                        onDragEnd = {
                            indiceTrascinato = null
                            offsetTrascinamento = 0f
                        },
                        onDragCancel = {
                            indiceTrascinato = null
                            offsetTrascinamento = 0f
                        },
                        onDrag = { cambiamento, trascinamento ->
                            cambiamento.consume()
                            offsetTrascinamento += trascinamento.y
                            val origine = indiceTrascinato ?: return@detectDragGesturesAfterLongPress
                            val infoOrigine = statoLista.layoutInfo.visibleItemsInfo
                                .firstOrNull { it.index == origine }
                                ?: return@detectDragGesturesAfterLongPress
                            val centroTrascinato = infoOrigine.offset + infoOrigine.size / 2 + offsetTrascinamento
                            val bersaglio = statoLista.layoutInfo.visibleItemsInfo.firstOrNull {
                                it.index != origine && centroTrascinato >= it.offset && centroTrascinato <= it.offset + it.size
                            }
                            if (bersaglio != null) {
                                onRiordinaAggiornato(origine, bersaglio.index)
                                // Il "centro" del trascinamento resta coerente con il dito:
                                // compensiamo l'offset con la differenza fra le due posizioni scambiate.
                                offsetTrascinamento += (infoOrigine.offset - bersaglio.offset).toFloat()
                                indiceTrascinato = bersaglio.index
                            }
                        },
                    )
                },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RigaEsercizio(
    esercizio: Esercizio,
    onClick: () -> Unit,
    onRimuovi: () -> Unit,
    modificatoreManiglia: Modifier,
    modifier: Modifier = Modifier,
) {
    val statoSwipe = rememberSwipeToDismissBoxState(
        confirmValueChange = { valore ->
            if (valore != SwipeToDismissBoxValue.Settled) {
                onRimuovi()
                true
            } else {
                false
            }
        },
    )

    SwipeToDismissBox(
        state = statoSwipe,
        modifier = modifier,
        backgroundContent = {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.errorContainer)
                    .padding(horizontal = 24.dp),
                contentAlignment = Alignment.CenterEnd,
            ) {
                Icon(
                    imageVector = Icons.Default.Delete,
                    contentDescription = stringResource(R.string.riga_esercizio_rimuovi_desc),
                    tint = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        },
    ) {
        Card(
            onClick = onClick,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.DragHandle,
                    contentDescription = stringResource(R.string.riga_esercizio_trascina_desc),
                    modifier = modificatoreManiglia,
                    tint = MaterialTheme.colorScheme.outline,
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = esercizio.nome.ifBlank { stringResource(R.string.riga_esercizio_senza_nome) },
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Medium,
                    )
                    if (esercizio.gruppo.isNotBlank()) {
                        Text(text = esercizio.gruppo, style = MaterialTheme.typography.bodySmall)
                    }
                }
                Icon(
                    imageVector = if (esercizio.pronto) Icons.Default.CheckCircle else Icons.Default.Warning,
                    contentDescription = stringResource(
                        if (esercizio.pronto) {
                            R.string.riga_esercizio_pronto_desc
                        } else {
                            R.string.riga_esercizio_non_pronto_desc
                        }
                    ),
                    tint = if (esercizio.pronto) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.outline
                    },
                )
            }
        }
    }
}
