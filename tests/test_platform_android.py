"""Android credential provider tests that do not require Android or pyjnius."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.platform import CredentialProviderError
from kivy_app.platform_android import AndroidCredentialProvider


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
