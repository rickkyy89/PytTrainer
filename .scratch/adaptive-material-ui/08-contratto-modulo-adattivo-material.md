# Contratto 08 — Modulo adattivo Material

## Scopo e seam

Il modulo `kivy_app.material` è la seam unica tra metriche della piattaforma e
schermate. È un modulo profondo: le schermate chiedono un `UiProfile` e token
già risolti, senza leggere `Window.density`, distinguere Android/Windows o
ripetere soglie di larghezza.

L'interfaccia pubblica è:

```text
profile = adaptive_profile(metrics, preferences)
profile.category       # COMPACT, MEDIUM oppure EXPANDED
profile.scale          # scala finale in pixel/logical dp
profile.touch_target   # minimo target per il modo di input
profile.tokens         # tipografia, spaziature, colori e dimensioni
profile.layout(name)   # decisione di reflow per una schermata
```

`metrics` è un valore iniettato, non `Window`: contiene almeno `width_dp`,
`height_dp`, `system_density` e `input_mode` (`touch` o `pointer`).
`preferences` contiene solo la scelta di scala locale (`auto`, `100`, `115`,
`130`). Nessuna schermata conserva una propria euristica.

## Profili e scala

La categoria usa la larghezza logica disponibile dopo il padding esterno:

| Categoria | Larghezza | Comportamento base |
|---|---:|---|
| `COMPACT` | 400–599 dp | una colonna, sezioni verticali, contenuto scrollabile |
| `MEDIUM` | 600–959 dp | reflow a due colonne dove utile, senza ridurre testo |
| `EXPANDED` | almeno 960 dp | contenuto centrato e master-detail quando previsto |

Viewport sotto 400 dp non introduce un quarto profilo: resta `COMPACT` e la
UI mantiene il minimo leggibile, lasciando scorrere il contenuto. Il profilo
si ricalcola a ogni cambio di viewport o orientamento senza perdere stato.

La scala finale è `system_density` in modalità Auto, oppure
`system_density * 1.00`, `* 1.15` o `* 1.30` per le scelte esplicite. I valori
di scala sono preferenze del dispositivo e non entrano nel bundle `.scheda`,
nel manifest o nello stato Drive. Cambiare scala aggiorna il profilo e i
widget alla prossima emissione di stato, senza riavvio.

I target minimi sono 48 dp per `touch` e 40 dp per `pointer`. Il valore è un
minimo geometrico, non una dimensione fisica derivata ad hoc. Testo e icone
possono avere dimensioni diverse, ma il contenitore interattivo deve rispettare
il target.

## Token Material centralizzati

`UiTokens` è immutabile e comprende almeno:

```text
colors: background, surface, surface_variant, text, muted, accent,
        error, focus, disabled
typography: title, section, body, label, caption
spacing: xxs, xs, sm, md, lg, xl
dimensions: toolbar_height, field_height, card_radius, border_width,
            content_max_width, dialog_max_width, frame_min_height
icons: family, size_sm, size_md, size_lg
```

Il tema usa superfici dark, accento verde acqua, contrasto leggibile, bordi
sottili e stati focus/disabled/error espliciti. Font e icone sono asset
bundled e il modulo fornisce il fallback quando un asset non è disponibile.
Le schermate non definiscono colori, font o dimensioni proprie salvo eccezioni
documentate per immagini e contenuti utente.

## Reflow e tastiera

Ogni schermata espone al modulo solo il proprio nome e riceve un `LayoutPlan`:

- `COMPACT`: label sopra i campi, card/azioni impilate, START e FINISH
  verticali, menu secondari in overflow;
- `MEDIUM`: colonne o righe solo se ogni figlio conserva il proprio minimo;
- `EXPANDED`: contenuto con `content_max_width`, liste e dettaglio affiancati
  quando la schermata lo prevede.

Un reflow non ricrea il modello di dominio e non resetta focus, scroll o dati
del campo. Il contenitore principale è sempre scrollabile quando la somma delle
altezze supera il viewport. Quando compare la tastiera, il modulo calcola
l'area visibile residua, porta il campo attivo sopra di essa e lascia visibile
la barra d'azione fissa; non usa offset costanti in pixel.

Alla rotazione si ricalcolano categoria, colonne, orientamento dei frame e
`LayoutPlan`. La sessione, cronologia, esercizio selezionato e testo attivo
restano gli stessi.

## Contenuto e larghezze

Su desktop il contenuto leggibile è centrato e limitato a
`content_max_width`; su telefono occupa la larghezza disponibile meno spacing.
Testo lungo usa altezza automatica e wrapping, mai `shorten` come unica
protezione. Dialoghi e menu hanno `dialog_max_width`, corpo scrollabile e
azioni sempre raggiungibili.

## Persistenza delle preferenze

`ScalePreferenceStore` è un adapter locale iniettato dal launcher:

```text
load_scale() -> "auto" | "100" | "115" | "130"
save_scale(value) -> None
```

Il modulo valida i quattro valori, usa `auto` se il file manca o è corrotto e
scrive in modo atomico. L'adapter Android usa l'area privata dell'app; quello
Windows usa la configurazione utente. Il modulo non accede al bundle e non
sincronizza la preferenza su Drive.

## Harness di test

Il test harness costruisce `ViewportMetrics` finti e invoca la stessa
`adaptive_profile` usata dalla UI. Non importa `Window` e non richiede un
display. La matrice minima è:

| Caso | Assert |
|---|---|
| 400, 599, 600, 959, 960 dp | categoria corretta e soglie inclusive |
| density 1/2/3 + Auto | scala basata solo sulla density fornita |
| 100/115/130 | moltiplicatori corretti e persistibili |
| touch/pointer | target rispettivamente >=48/40 dp |
| portrait/landscape | piano di reflow coerente senza perdita di stato |
| scala corrotta/mancante | fallback Auto |
| testo lungo | altezza automatica e nessun clipping previsto dal piano |
| tastiera | area utile e campo attivo sopra l'inset |

Il harness verifica geometria (bounds, minimi, overlap, larghezze non nulle)
separatamente dagli screenshot. Gli screenshot dei ticket successivi usano
questo stesso profilo deterministico e non diventano parte dell'interfaccia del
modulo.

## Decisioni chiuse per l'implementazione

Luna deve implementare un solo risolutore di profilo, un solo set di token e un
solo adapter di preferenze. Non sono ammessi controlli diretti di densità nelle
schermate, soglie locali, unità fisiche o temi duplicati. I provider reali
(Window/Kivy, Android e Windows) sono adapter sottili della seam; fake metriche
e fake store sono sufficienti per tutti i test automatici.
