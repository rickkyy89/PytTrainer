#!/usr/bin/env bash
# Crea l'app Kivy spike throwaway in /home/rickk/spike-builder/app
set -e
APP=/home/rickk/spike-builder/app
mkdir -p "$APP"

cat > "$APP/main.py" <<'PY'
import os
import io
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.image import AsyncImage
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.core.window import Window
from kivy.logger import Logger

# ---- yt-dlp ----
def yt_search(query):
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlist_items": "1-5",
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch5:{query}", download=False)
    out = []
    for e in info.get("entries", []):
        out.append({
            "title": e.get("title"),
            "duration": e.get("duration"),
            "id": e.get("id"),
            "thumbnail": e.get("thumbnail"),
        })
    return out

def yt_stream_url(video_url):
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "player_client": "android",
        "format": "bv*+ba/b",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    for f in info.get("formats", []):
        if f.get("vcodec") not in (None, "none") and f.get("protocol") in ("https", "http"):
            return f["url"]
    return info["url"]

# ---- ffmpeg-kit via pyjnius: carica classi con classloader dell'app, invoca via java.lang.reflect ----
def _app_cls(name):
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity.getClassLoader().loadClass(name)


def _ensure_reflect_helpers():
    """Fonde invoke()/get() (statici) nelle classi reflect di pyjnius se mancanti."""
    from jnius import JavaMultipleMethod
    from jnius.reflect import Method, Field
    if not hasattr(Method, "invoke"):
        Method.invoke = JavaMultipleMethod([
            ("(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;", True, False),
            ("(Ljava/lang/Object;)Ljava/lang/Object;", True, False),
            ("()Ljava/lang/Object;", True, False),
        ])
    if not hasattr(Field, "get"):
        Field.get = JavaMultipleMethod([
            ("(Ljava/lang/Object;)Ljava/lang/Object;", True, False),
            ("()Ljava/lang/Object;", True, False),
        ])


def extract_frame_ffmpegkit(stream_url, ts, out_path):
    from jnius import autoclass
    _ensure_reflect_helpers()
    FFmpegKit_cls = _app_cls("com.arthenica.ffmpegkit.FFmpegKit")
    ReturnCode_cls = _app_cls("com.arthenica.ffmpegkit.ReturnCode")
    java_String = autoclass("java.lang.String")
    cmd = (
        "-y -ss {ts} -i {url} -vframes 1 -q:v 2 {out}"
    ).format(ts=ts, url=stream_url, out=out_path)

    # trova il metodo statico execute(String) via reflection dei metodi
    session = None
    Object = autoclass("java.lang.Object")
    Array = autoclass("java.lang.reflect.Array")
    for m in FFmpegKit_cls.getMethods():
        if m.getName() == "execute":
            params = m.getParameterTypes()
            if len(params) == 1 and params[0].getName() == "java.lang.String":
                try:
                    args_arr = Array.newInstance(Object, 1)
                    args_arr[0] = java_String(cmd)
                    session = m.invoke(None, args_arr)
                except Exception as e:
                    print("SPIKE invoke execute error: %s" % e, flush=True)
                break
    if session is None:
        raise RuntimeError("FFmpegKit.execute(String) not found or failed")

    rc_m = None
    empty = Array.newInstance(Object, 0)
    for m in session.getClass().getMethods():
        if m.getName() == "getReturnCode" and m.getParameterTypes().length == 0:
            rc_m = m
            break
    rc = rc_m.invoke(session, empty)

    success = None
    for f in ReturnCode_cls.getFields():
        if f.getName() == "SUCCESS":
            success = f.get(None).getValue()
            break
    return rc.getValue() == success

class SpikeRoot(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.query = TextInput(text="squat", size_hint_y=0.08)
        self.status = Label(text="ready", size_hint_y=0.06)
        self.btn_search = Button(text="1) Search (yt-dlp)", size_hint_y=0.08)
        self.video_url = TextInput(text="", hint_text="url video scelto", size_hint_y=0.08)
        self.slider = Slider(min=0, max=60, value=10, size_hint_y=0.06)
        self.btn_frame = Button(text="2) Extract frame", size_hint_y=0.08)
        self.image = AsyncImage(size_hint_y=0.5)
        self.btn_search.bind(on_release=lambda *a: self.threaded(self.do_search))
        self.btn_frame.bind(on_release=lambda *a: self.threaded(self.do_frame))
        sv = ScrollView()
        sv.add_widget(self.image)
        self.add_widget(self.query)
        self.add_widget(self.btn_search)
        self.add_widget(self.video_url)
        self.add_widget(self.slider)
        self.add_widget(self.btn_frame)
        self.add_widget(sv)
        self.add_widget(self.status)
        self.result = None

    def threaded(self, fn):
        threading.Thread(target=lambda: self.with_status(fn)).start()

    def with_status(self, fn):
        try:
            self.set_status("working...")
            fn()
        except Exception as e:
            Logger.exception("spike")
            self.set_status("ERR: %s" % e)

    def set_status(self, msg):
        Clock.schedule_once(lambda *a: setattr(self.status, "text", msg))

    def do_search(self):
        print("SPIKE search START query=%r" % self.query.text, flush=True)
        results = yt_search(self.query.text)
        if not results:
            self.set_status("no results")
            print("SPIKE search NO RESULTS", flush=True)
            return
        top = results[0]
        self.result = top
        url = "https://www.youtube.com/watch?v=%s" % top["id"]
        Clock.schedule_once(lambda *a: setattr(self.video_url, "text", url))
        Clock.schedule_once(
            lambda *a: self.image.__setattr__("source", top.get("thumbnail") or ""))
        self.set_status("OK %d results | dur=%s | %s" % (
            len(results), top.get("duration"), top.get("title")))
        print("SPIKE search OK n=%d title=%r dur=%s url=%s" % (
            len(results), top.get("title"), top.get("duration"), url), flush=True)

    def do_frame(self):
        url = self.video_url.text.strip()
        if not url:
            self.set_status("set a video url first")
            print("SPIKE frame NO URL", flush=True)
            return
        out = "/sdcard/frame_result.jpg"
        print("SPIKE frame stream RESOLVE %s" % url, flush=True)
        stream = yt_stream_url(url)
        print("SPIKE frame got stream %s..." % stream[:60], flush=True)
        self.set_status("stream=%s..." % stream[:40])
        chunk = self.extract_frame(stream, float(self.slider.value), out)
        print("SPIKE frame result %s -> %s" % (chunk, out), flush=True)
        Clock.schedule_once(lambda *a: self.image.__setattr__("source", chunk))
        self.set_status("frame OK -> %s" % chunk)

    def auto_test(self):
        import time
        time.sleep(3)
        try:
            self.do_search()
        except Exception as e:
            Logger.exception("spike-auto")
            print("SPIKE auto ERR %s" % e, flush=True)
        time.sleep(5)
        try:
            self.set_url("https://www.youtube.com/watch?v=my0tLDaWyDU")
            self.do_frame()
        except Exception as e:
            Logger.exception("spike-frame")
            print("SPIKE frame ERR %s" % e, flush=True)

    def set_url(self, url):
        Clock.schedule_once(lambda *a: setattr(self.video_url, "text", url), 0)
        import time
        time.sleep(1.5)

    def extract_frame(self, stream_url, ts, out_path):
        return extract_frame_ffmpegkit(stream_url, ts, out_path)

class SpikeApp(App):
    def build(self):
        self.title = "PytTrainer Spike"
        root = SpikeRoot()
        threading.Timer(3.0, root.auto_test).start()
        return root

if __name__ == "__main__":
    SpikeApp().run()
PY

cat > "$APP/buildozer.spec" <<'SPEC'
[app]
title = PytTrainerSpike
package.name = pttspike
package.domain = org.ptt
version = 0.1
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas
requirements = python3,kivy,yt-dlp,pyjnius
icon.filename =
orientation = all
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.gradle_dependencies = dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7
android.accept_sdk_license = True
android.allow_backup = True
p4a.source_exts = py,png,jpg,jpeg,kv,atlas

[buildozer]
log_level = 1
warn_on_root = 1
SPEC

echo "created:"
ls -la "$APP"
