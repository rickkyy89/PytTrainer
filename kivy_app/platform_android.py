"""Android-specific Google credential adapters.

This module remains importable on the PC: pyjnius is loaded only when the
production bridge is instantiated on Android.
"""

from __future__ import annotations

from pathlib import Path
import threading

from google.oauth2.credentials import Credentials

from core.platform import CredentialProviderError
from core.video_helper import FrameExtractionError


# MediaMetadataRetriever.OPTION_CLOSEST: frame esatto al timestamp richiesto,
# non solo il keyframe piu' vicino (OPTION_CLOSEST_SYNC). Su video con keyframe
# sparsi, CLOSEST_SYNC fa scattare la preview solo a salti di decine di secondi.
OPTION_CLOSEST = 3


class AndroidCredentialProvider:
    """Expose the access token obtained by the native Google authorization flow."""

    def __init__(self, bridge):
        self._bridge = bridge

    def start_authorization(self) -> None:
        """Start the native consent flow before a Drive request needs its token."""
        self._bridge.start_authorization()

    def riautentica(self, timeout: float = 12.0) -> bool:
        """Riavvia l'autorizzazione nativa e attende un token non vuoto.

        Il consenso e' gia' stato dato in passato, quindi il bridge completa
        in silenzio: serve quando il token nativo (vita ~1 ora) e' scaduto.
        """
        import time

        try:
            self._bridge.start_authorization()
        except Exception:
            return False
        fine = time.monotonic() + timeout
        while time.monotonic() < fine:
            time.sleep(0.3)
            token = self._bridge.get_access_token()
            if isinstance(token, str) and token.strip():
                return True
        return False

    def get_credentials(self, scopes: list[str]) -> Credentials:
        token = self._bridge.get_access_token()
        if not isinstance(token, str) or not token.strip():
            status = self._bridge.get_status()
            raise CredentialProviderError(
                "Autorizzazione Google Android non disponibile. "
                "Accedi con Google e completa il consenso prima di usare Drive "
                f"(stato nativo: {status or 'sconosciuto'})."
            )
        return Credentials(token=token, scopes=scopes)


class PyjniusGoogleBridge:
    """Production adapter for the Java bridge, loaded only on Android."""

    def __init__(self):
        from jnius import autoclass

        self._activity = autoclass("org.kivy.android.PythonActivity").mActivity
        self._bridge = autoclass("org.ptt.pyTrainer.GoogleBridge")

    def start_authorization(self) -> None:
        self._bridge.startAuthorization(self._activity)

    def get_access_token(self) -> str:
        return self._bridge.getAccessToken()

    def get_status(self) -> str:
        return self._bridge.getStatus()


def android_pdf_cache_dir() -> Path:
    """Private cache subtree covered by the manifest FileProvider path."""
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return Path(str(activity.getCacheDir().getAbsolutePath())) / "pdf"


class AndroidFrameExtractor:
    """Frame extraction on the device via android.media.MediaMetadataRetriever.

    The spike (docs/SPIKE-01-android-result.md, risk 2b) validated this native
    path: ffmpeg-kit's maintained artifact is missing a Java dependency, so the
    framework retriever is used instead. ``core.video_helper.extract_frame``
    detects this object through its ``extract`` method and skips ffmpeg.

    ``autoclass`` must run on the main thread, so the Java classes are cached
    on construction and reused by worker threads.
    """

    def __init__(self, autoclass_factory=None):
        if autoclass_factory is None:
            from jnius import autoclass as autoclass_factory  # noqa: F401
        try:
            from jnius import JavaException as self_java_exc
            self._java_exception = self_java_exc
        except ImportError:
            self._java_exception = ()  # PC: nessun JavaException puo' comparire
        self._retriever_cls = autoclass_factory("android.media.MediaMetadataRetriever")
        self._format_cls = autoclass_factory("android.graphics.Bitmap$CompressFormat")
        self._stream_cls = autoclass_factory("java.io.FileOutputStream")
        self._hashmap_cls = autoclass_factory("java.util.HashMap")
        self._retrievers: dict[str, object] = {}
        self._retriever_lock = threading.RLock()

    def extract(self, stream_url, timestamp_seconds, output_path, http_headers=None):
        with self._retriever_lock:
            retriever = self._retriever_per_url(stream_url, http_headers)
            stream = None
            try:
                bitmap = retriever.getFrameAtTime(int(timestamp_seconds * 1_000_000), OPTION_CLOSEST)
                if bitmap is None:
                    raise FrameExtractionError(
                        f"MediaMetadataRetriever: nessun frame al secondo {timestamp_seconds}."
                    )
                stream = self._stream_cls(output_path)
                if not bitmap.compress(self._format_cls.JPEG, 90, stream):
                    raise FrameExtractionError(
                        f"MediaMetadataRetriever: codifica JPEG fallita per {output_path}."
                    )
                stream.flush()
                stream.close()
                return output_path
            except self._java_exception as exc:
                self._scarta_retriever(stream_url)
                raise FrameExtractionError(
                    f"MediaMetadataRetriever ha rifiutato lo stream "
                    f"al secondo {timestamp_seconds}: {exc}"
                ) from exc
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def _retriever_per_url(self, stream_url, http_headers):
        """Return a cached ``MediaMetadataRetriever`` for one stream URL.

        Re-opening the network source for every scrub drag is what made the
        preview look frozen while the retriever re-buffered the stream, so the
        retriever is created once per URL and reused for subsequent seeks.
        """
        cached = self._retrievers.get(stream_url)
        if cached is not None:
            return cached
        retriever = self._retriever_cls()
        try:
            if http_headers:
                hashmap = self._hashmap_cls()
                for name, value in http_headers.items():
                    hashmap.put(name, value)
                retriever.setDataSource(stream_url, hashmap)
            else:
                retriever.setDataSource(stream_url)
        except Exception:
            try:
                retriever.release()
            except Exception:
                pass
            raise
        self._retrievers[stream_url] = retriever
        return retriever

    def _scarta_retriever(self, stream_url):
        """Drop a retriever after a failed seek so the next call restarts cleanly."""
        retriever = self._retrievers.pop(stream_url, None)
        if retriever is not None:
            try:
                retriever.release()
            except Exception:
                pass
