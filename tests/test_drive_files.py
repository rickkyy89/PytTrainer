"""Validation rules for the Drive transfer helper (scripts/drive_files.py)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.drive_files import ALLOWED_TYPES, DriveFilesError, _validate_name


def test_apk_e_un_tipo_consentito_e_valida_nomi_puliti():
    assert ".apk" in ALLOWED_TYPES
    assert _validate_name("pyTrainer-0.2.0.13-arm64-v8a-debug.apk") == (
        "pyTrainer-0.2.0.13-arm64-v8a-debug.apk"
    )


def test_rifiuta_estensioni_non_supportate_e_percorsi():
    with pytest.raises(DriveFilesError):
        _validate_name("note.txt")
    with pytest.raises(DriveFilesError):
        _validate_name("sotto/cartella.apk")
