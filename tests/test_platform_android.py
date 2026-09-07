"""Android credential provider tests that do not require Android or pyjnius."""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.platform import CredentialProviderError
from core.video_helper import FrameExtractionError
from kivy_app.platform_android import AndroidCredentialProvider, AndroidFrameExtractor


class FakeBridge:
    def __init__(self, token="", status="idle"):
        self.token = token
        self.status = status
        self.authorization_started = 0

    def start_authorization(self):
        self.authorization_started += 1

    def get_access_token(self):
        return self.token

    def get_status(self):
        return self.status


def test_android_provider_creates_google_credentials_from_native_access_token():
    credentials = AndroidCredentialProvider(FakeBridge("native-access-token", "authorized")) \
        .get_credentials(["scope-one"])

    assert credentials.token == "native-access-token"
    assert credentials.scopes == ["scope-one"]


def test_android_provider_starts_native_authorization():
    bridge = FakeBridge()

    AndroidCredentialProvider(bridge).start_authorization()

    assert bridge.authorization_started == 1


@pytest.mark.parametrize("token,status", [("", "idle"), ("   ", "consent_required"), (None, "error: ApiException")])
def test_android_provider_reports_clear_error_when_native_authorization_is_unavailable(token, status):
    with pytest.raises(CredentialProviderError, match="Autorizzazione Google Android.*" + status):
        AndroidCredentialProvider(FakeBridge(token, status)).get_credentials(["scope-one"])


def test_android_provider_import_does_not_load_pyjnius():
    assert "jnius" not in sys.modules


class _FakeBitmap:
    def __init__(self, payload=b"jpeg"):
        self.payload = payload
        self.compress_writes = 0

    def compress(self, fmt, quality, stream):
        self.compress_writes += 1
        stream.write(self.payload)
        return True


class _FakeCompressFormat:
    JPEG = object()


class _FakeStream:
    def __init__(self, path):
        self.path = path
        Path(path).write_bytes(b"")
        self._closed = False

    def write(self, data):
        with open(self.path, "ab") as fh:
            fh.write(data)

    def flush(self):
        pass

    def close(self):
        self._closed = True


class _FakeHashMap:
    def __init__(self):
        self.data = {}

    def put(self, key, value):
        self.data[key] = value


class _FakeRetriever:
    created = 0
    released = 0

    def __init__(self):
        _FakeRetriever.created += 1
        self.source = None
        self.headers = None
        self.fail_seek = False
        self.last_option = None

    def setDataSource(self, source, headers=None):
        self.source = source
        self.headers = headers

    def getFrameAtTime(self, time_us, option):
        self.last_option = option
        if self.fail_seek:
            raise _FakeJavaException("seek boom")
        return _FakeBitmap()

    def release(self):
        _FakeRetriever.released += 1


class _FakeJavaException(Exception):
    pass


@pytest.fixture
def fake_retriever_cls():
    _FakeRetriever.created = 0
    _FakeRetriever.released = 0
    return _FakeRetriever


def _headless_extractor(fake_retriever_cls):
    def factory(name):
        return {
            "android.media.MediaMetadataRetriever": fake_retriever_cls,
            "android.graphics.Bitmap$CompressFormat": _FakeCompressFormat,
            "java.io.FileOutputStream": _FakeStream,
            "java.util.HashMap": _FakeHashMap,
        }[name]

    return AndroidFrameExtractor(autoclass_factory=factory)


def test_android_extractor_riusa_un_solo_retriever_per_url(fake_retriever_cls, tmp_path):
    extractor = _headless_extractor(fake_retriever_cls)
    headers = {"User-Agent": "fake"}

    out1 = extractor.extract("stream://a", 10.0, str(tmp_path / "a.jpg"), headers)
    out2 = extractor.extract("stream://a", 20.0, str(tmp_path / "b.jpg"), headers)
    out3 = extractor.extract("stream://b", 5.0, str(tmp_path / "c.jpg"), headers)

    assert Path(out1).exists() and Path(out2).exists() and Path(out3).exists()
    # stesso URL -> un solo retriever; URL diverso -> una seconda istanza
    assert fake_retriever_cls.created == 2
    # un seek riuscito non rilascia mai il retriever (serve a riusarlo)
    assert fake_retriever_cls.released == 0
    assert extractor._retrievers["stream://a"] is extractor._retrievers["stream://a"]


def test_android_extractor_chiede_il_frame_esatto_non_il_keyframe(fake_retriever_cls, tmp_path):
    # OPTION_CLOSEST (3): la preview e "estrai frame" devono aggiornarsi a ogni
    # secondo, non solo quando il timestamp scavalca un keyframe.
    extractor = _headless_extractor(fake_retriever_cls)

    extractor.extract("stream://a", 15.0, str(tmp_path / "f.jpg"))

    assert extractor._retrievers["stream://a"].last_option == 3


def test_android_extractor_scarta_il_retriever_dopo_un_seek_fallito(fake_retriever_cls, tmp_path):
    extractor = _headless_extractor(fake_retriever_cls)
    extractor._java_exception = _FakeJavaException

    extractor.extract("stream://a", 1.0, str(tmp_path / "ok.jpg"))
    assert "stream://a" in extractor._retrievers

    extractor._retrievers["stream://a"].fail_seek = True
    with pytest.raises(FrameExtractionError):
        extractor.extract("stream://a", 2.0, str(tmp_path / "ko.jpg"))

    assert "stream://a" not in extractor._retrievers
    assert fake_retriever_cls.released >= 1


def test_core_platform_import_does_not_load_desktop_crypto_stack():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import core.platform; "
            "assert 'google.auth.crypt' not in sys.modules",
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )

    assert result.returncode == 0


def test_android_manifest_declares_google_runtime_dependencies():
    requirements_line = next(
        line for line in (PROJECT_ROOT / "buildozer.spec").read_text(encoding="utf-8").splitlines()
        if line.startswith("requirements = ")
    )
    requirements = requirements_line.split("=", 1)[1].split(",")
    declared = {item.split("==", 1)[0] for item in requirements}

    assert {
        "cachetools",
        "google-api-core",
        "googleapis-common-protos",
        "httplib2",
        "proto-plus",
        "protobuf",
        "pyasn1",
        "pyasn1-modules",
        "pyparsing",
        "rsa",
        "uritemplate",
    } <= declared
    assert "google-auth==2.23.4" in requirements
    assert "cryptography" not in declared
