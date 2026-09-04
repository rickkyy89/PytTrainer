# Sistema UI adattivo Material — guida

Documentazione di riferimento per manutenzione, verifica responsive e
aggiornamento delle baseline. Contratto completo del modulo:
[`08-contratto-modulo-adattivo-material.md`](08-contratto-modulo-adattivo-material.md);
uso del harness geometrico: [`README-responsive-harness.md`](README-responsive-harness.md).

## Architecture (profili, scala, token)

- **`kivy_app/material.py`** — modulo profondo senza Kivy: risolve
  `UiProfile` (categoria 400–599 compact / 600–959 medium / ≥960 expanded,
  scala, target minimi 48dp touch / 40dp pointer, token, `LayoutPlan` per
  schermata) da `ViewportMetrics` iniettabili. Adapter Kivy:
  `profile_for_window(Window)` è l'unico punto che legge la densità reale;
  `input_mode_for_platform()` è l'unico punto che decide touch/pointer.
- **`kivy_app/theme.py`** — unico adapter che tocca gli stili di classe Kivy:
  dipinge i token (dark `#121416`, accento `#55D6BE`, superfici, focus,
  muted) su Window/Button/Label/TextInput/ScrollView/Popup e imposta
  `softinput_mode="below_target"` (il campo attivo non finisce sotto la
  tastiera).
- **`kivy_app/*_layout.py`** (`home_layout`, `editor_layout`, `media_layout`,
  `workout_layout`, `secondary_layout`) — policy pure per schermata: assi
  dei frame START/FINISH, accordion, etichette sopra i campi, colonne della
  griglia, dialoghi. Le schermate consumano solo queste decisioni.
- **Regola d'oro**: una schermata non deve mai leggere `Window.density`,
  indovinare il tipo di input o fissare misure in px; dimensioni e colori
  derivano sempre dal profilo.

## Verifica headless

```text
pytest -q                                  # suite completa (220 test)
pytest -q tests/test_material.py tests/test_responsive_harness.py
python -m compileall -q kivy_app core
```

Il harness (`kivy_app/responsive_harness.py`) valida la geometria (out-of
bounds, overlap, zero-size, testo tagliato, target sotto minimo) su scenari
injectati senza display: telefono 400dp, tablet portrait/landscape, desktop,
ognuno anche a scala 130%.

## Checklist risultati verifica reale (ticket 16–17)

| Ambiente | Esito |
|---|---|
| Windows desktop (pointer) | app avviata (SDL2+OpenGL), home Material dark, target minimi 40dp, mouse e tastiera funzionanti — baseline `baselines/home-windows.png` |
| Lenovo TB336FU Android 16, USB, portrait | APK debug installato, avvio senza crash, tema dark e toolbar 48dp — baseline `baselines/home-lenovo-portrait.png` |
| Profilo compatto simulato | harness: scenari `phone-compact` e `phone-compact-130` verdi su tutte le policy di layout |
| Build | `buildozer android debug` in WSL Ubuntu (`~/.venvs/buildozer`), exit 0, APK `bin/pyTrainer-0.1-arm64-v8a-debug.apk` |

## Procedura di aggiornamento baseline

1. **Screenshot reali** (home, profilo corrente):
   - Windows: avviare `python -m kivy_app`, catturare la finestra "pyTrainer"
     (PowerShell: `Start-Process python -ArgumentList "-m","kivy_app"`, poi
     screenshot mirato con PIL `ImageGrab` sul `GetWindowRect` della finestra)
     e salvare in `.scratch/adaptive-material-ui/baselines/home-windows.png`.
   - Lenovo (USB, nessuna rete necessaria):
     `adb install -r bin\pyTrainer-0.1-arm64-v8a-debug.apk`,
     `adb shell am start -n org.ptt.pytrainer/org.kivy.android.PythonActivity`,
     `adb exec-out screencap -p > baselines\home-lenovo-portrait.png`.
2. **Baseline geometriche SVG**: `render_baseline(scenario, boxes)` +
   `write_baseline(path, content)` del responsive harness (comando e formato
   descritti in `README-responsive-harness.md`).
3. Confronto: una differenza di pixel è una differenza visiva (richiede
   riesame umano); un fallimento di `validate_geometry` è invece una
   regressione e fa fallire la suite.
4. Aggiornare i file in `baselines/` solo dopo approvazione, nello stesso
   commit della modifica che giustifica il cambiamento.

## Manutenzione

- Nuovo colore/misura: aggiungere il token in `material._tokens`, mai il
  valore letterale nella schermata.
- Nuovo comportamento responsive: estendere il `LayoutPlan` della schermata
  interessata e il suo scenario nel harness.
- Credenziali Google e scale: la scala utente è solo locale
  (`ScalePreferenceStore`, dispositivo); non finisce mai nel bundle `.scheda`
  né su Drive.
