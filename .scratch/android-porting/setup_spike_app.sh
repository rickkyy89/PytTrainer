#!/usr/bin/env bash
# Crea l'app Kivy spike throwaway in /home/rickk/spike-builder/app
set -e
APP=/home/rickk/spike-builder/app
mkdir -p "$APP"
mkdir -p "$APP/java/org/ptt/spike"
cp /mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/GoogleBridge.java "$APP/java/org/ptt/spike/GoogleBridge.java"

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

PythonActivity = None
GoogleBridge = None

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

# ---- ffmpeg-kit: le classi vanno risolte con autoclass SUL MAIN THREAD ----
# FindClass da un thread Python secondario usa il classloader di sistema e non
# vede i dex dell'app; sul main thread (dove Kivy fa il bootstrap) invece li vede.
# Quindi cachiamo le classi all'avvio e le riusiamo dai worker thread.
FFMPEG_CLASSES = {}


def cache_ffmpeg_classes():
    from jnius import autoclass
    FFMPEG_CLASSES["FFmpegKit"] = autoclass("com.arthenica.ffmpegkit.FFmpegKit")
    FFMPEG_CLASSES["ReturnCode"] = autoclass("com.arthenica.ffmpegkit.ReturnCode")
    print("SPIKE ffmpeg classes cached on main thread", flush=True)


def extract_frame_ffmpegkit(stream_url, ts, out_path):
    FFmpegKit = FFMPEG_CLASSES["FFmpegKit"]
    ReturnCode = FFMPEG_CLASSES["ReturnCode"]
    cmd = (
        "-y -ss {ts} -i {url} -vframes 1 -q:v 2 {out}"
    ).format(ts=ts, url=stream_url, out=out_path)
    session = FFmpegKit.execute(cmd)
    return session.getReturnCode().getValue() == ReturnCode.SUCCESS.getValue()


def extract_frame_mediaretriever(stream_url, ts, out_path):
    from jnius import autoclass
    Retriever = autoclass("android.media.MediaMetadataRetriever")
    CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
    FileOutputStream = autoclass("java.io.FileOutputStream")
    retriever = Retriever()
    stream = None
    try:
        retriever.setDataSource(stream_url)
        bitmap = retriever.getFrameAtTime(int(ts * 1000000), 2)
        if bitmap is None:
            raise RuntimeError("MediaMetadataRetriever returned no frame")
        stream = FileOutputStream(out_path)
        if not bitmap.compress(CompressFormat.JPEG, 90, stream):
            raise RuntimeError("Could not encode frame as JPEG")
        stream.flush()
        return out_path
    finally:
        if stream is not None:
            stream.close()
        retriever.release()

class SpikeRoot(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.query = TextInput(text="squat", size_hint_y=0.08)
        self.status = Label(text="ready", size_hint_y=0.06)
        self.btn_search = Button(text="1) Search (yt-dlp)", size_hint_y=0.08)
        self.video_url = TextInput(text="", hint_text="url video scelto", size_hint_y=0.08)
        self.slider = Slider(min=0, max=60, value=10, size_hint_y=0.06)
        self.btn_frame = Button(text="2) Extract frame", size_hint_y=0.08)
        self.btn_google = Button(text="3) Google authorization", size_hint_y=0.08)
        self.btn_picker = Button(text="4) Drive picker", size_hint_y=0.08)
        self.image = AsyncImage(size_hint_y=0.5)
        self.btn_search.bind(on_release=lambda *a: self.threaded(self.do_search))
        self.btn_frame.bind(on_release=lambda *a: self.threaded(self.do_frame))
        self.btn_google.bind(on_release=lambda *a: self.start_google())
        self.btn_picker.bind(on_release=lambda *a: self.start_picker())
        sv = ScrollView()
        sv.add_widget(self.image)
        self.add_widget(self.query)
        self.add_widget(self.btn_search)
        self.add_widget(self.video_url)
        self.add_widget(self.slider)
        self.add_widget(self.btn_frame)
        self.add_widget(self.btn_google)
        self.add_widget(self.btn_picker)
        self.add_widget(sv)
        self.add_widget(self.status)
        self.result = None
        Clock.schedule_interval(self.poll_google, 0.5)

    def start_google(self):
        Clock.schedule_once(self._start_google, 0)

    def _start_google(self, *_args):
        if GoogleBridge is None:
            self.set_status("Google bridge unavailable")
            return
        GoogleBridge.startAuthorization(PythonActivity.mActivity)
        self.set_status("Google authorization started")

    def start_picker(self):
        if GoogleBridge is None:
            self.set_status("Google bridge unavailable")
            return
        GoogleBridge.openDrivePicker(PythonActivity.mActivity)

    def poll_google(self, *_args):
        if GoogleBridge is None:
            return
        state = str(GoogleBridge.getStatus())
        if state == "authorized":
            length = GoogleBridge.getTokenLength()
            self.set_status("Google OK | token=%d chars | drive.file + documents" % length)
            print("SPIKE google authorized token_length=%d" % length, flush=True)
        elif state == "picked":
            uri = str(GoogleBridge.getPickedUri())
            self.set_status("Drive picker OK | %s" % uri[:70])
            print("SPIKE drive picker OK uri=%s" % uri, flush=True)
        elif state.startswith("error") or state.endswith("cancelled"):
            self.set_status("Google %s" % state)
            print("SPIKE google %s" % state, flush=True)

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
        out = os.path.join(os.environ.get("ANDROID_PRIVATE", "/tmp"), "frame_result.jpg")
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
        if FFMPEG_CLASSES:
            try:
                if extract_frame_ffmpegkit(stream_url, ts, out_path):
                    return out_path
                print("SPIKE ffmpegkit non-zero return code -> fallback MediaMetadataRetriever", flush=True)
            except Exception as e:
                print("SPIKE ffmpegkit ERR %s -> fallback MediaMetadataRetriever" % e, flush=True)
        return extract_frame_mediaretriever(stream_url, ts, out_path)

class SpikeApp(App):
    def build(self):
        self.title = "pyTrainer Spike"
        root = SpikeRoot()
        global PythonActivity, GoogleBridge
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            GoogleBridge = autoclass("org.ptt.spike.GoogleBridge")
            print("SPIKE google bridge cached on main thread", flush=True)
        except Exception as e:
            print("SPIKE cache google bridge ERR %s" % e, flush=True)
        try:
            cache_ffmpeg_classes()
        except Exception as e:
            print("SPIKE cache ffmpeg classes ERR %s" % e, flush=True)
        threading.Timer(3.0, root.auto_test).start()
        return root

if __name__ == "__main__":
    SpikeApp().run()
PY

cat > "$APP/buildozer.spec" <<'SPEC'
[app]
title = pyTrainerSpike
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
android.gradle_dependencies = dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7,com.google.android.gms:play-services-auth:21.6.0
android.add_src = java
android.accept_sdk_license = True
android.allow_backup = True
p4a.source_exts = py,png,jpg,jpeg,kv,atlas

[buildozer]
log_level = 1
warn_on_root = 1
SPEC

echo "created:"
ls -la "$APP"
