import os
import sys

os.environ["KIVY_GL_BACKEND"] = "mock"
os.environ.setdefault("KIVY_NO_ARGS", "1")
sys.path.insert(0, r"C:\PyTrainer\PC\PytTrainer")

from kivy.app import App
from kivy.clock import Clock

import kivy_app.editor_screen  # noqa: F401  (verify module imports on PC)
import kivy_app.main as m

from types import SimpleNamespace


def build_side_screens():
    from kivy_app.editor_screen import EditorScreen
    from kivy_app.export import DocExportController
    from kivy_app.export_screen import ExportScreen
    from kivy_app.media import MediaFlowController
    from kivy_app.media_screen import MediaScreen

    esercizio = {"nome": "Squat", "spiegazione": "", "note": "", "ripetizioni": "",
                 "recupero": "", "gruppo": "", "video_url": "https://youtu.be/x",
                 "ts_start": 5.0, "ts_finish": 25.0, "frame_start": None,
                 "frame_finish": None}
    editor = SimpleNamespace(esercizi=[esercizio], output_frames=lambda: ".",
                             marca_modifica=lambda: None, duplicati_slug=lambda: {},
                             sporco=False, gruppi_esistenti=list, titolo=None,
                             percorso_bundle="s.scheda", cartella_lavoro=None,
                             salva=lambda: None)
    remote = SimpleNamespace(name="s.scheda", id="one")
    controller = SimpleNamespace(refresh=lambda: [remote])
    screen = EditorScreen(controller, editor, remote, on_back=lambda: None,
                          open_media=lambda ed, i: None, on_export=lambda ed: None)
    media = MediaFlowController(esercizio, ".", search=lambda n: [],
                                extractor=lambda *a, **k: ("a.jpg", "b.jpg"))
    media_screen = MediaScreen(media, on_back=lambda: None)
    export = DocExportController(editor, credential_provider="CP")
    export_screen = ExportScreen(export, on_back=lambda: None)
    from kivy_app.workout import WorkoutSessionController
    from kivy_app.workout_screen import WorkoutScreen
    session = WorkoutSessionController(
        [{"nome": "Squat", "ripetizioni": "3x12", "recupero": "90 SEC",
          "note": "Tieni la schiena.", "frame_start": None, "frame_finish": None}])
    workout_screen = WorkoutScreen(session, on_back=lambda: None,
                                   notifier=lambda *a: None)
    workout_screen._tick()
    return screen, media_screen, export_screen, workout_screen


def _probe(dt):
    screen, media_screen, export_screen, workout_screen = build_side_screens()
    print("SIDES OK", bool(screen.children), bool(media_screen),
          bool(export_screen), bool(workout_screen.children))
    App.get_running_app().stop()


Clock.schedule_once(_probe, 1.5)
m.run()
print("SMOKE OK")
