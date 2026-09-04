# Harness responsive

Verifica headless:

```text
pytest -q tests/test_material.py tests/test_responsive_harness.py
```

Gli adapter delle schermate restituiscono `WidgetBox` per il `UiProfile`
ricevuto da `run_scenario`. `validate_geometry` distingue `out-of-bounds`,
`overlap`, `zero-size`, `text-clipped` e `target-too-small` dalle differenze
visive delle baseline SVG.

Per aggiornare una baseline si invoca esplicitamente `render_baseline` e si
scrive il risultato con `write_baseline`; il formato SVG è deterministico e
leggibile nel diff. Gli scenari coprono telefono, tablet portrait/landscape e
desktop, alle scale Auto e 130%, senza dipendere da Kivy `Window`.
