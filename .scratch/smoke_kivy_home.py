import os
import sys

os.environ["KIVY_GL_BACKEND"] = "mock"
os.environ.setdefault("KIVY_NO_ARGS", "1")
sys.path.insert(0, r"C:\PyTrainer\PC\PytTrainer")

from kivy.app import App
from kivy.clock import Clock

import kivy_app.editor_screen  # noqa: F401  (verify module imports on PC)
import kivy_app.main as m

Clock.schedule_once(lambda dt: App.get_running_app().stop(), 2.0)
m.run()
print("SMOKE OK")
