#!/usr/bin/env python
# Patch per la cache p4a di produzione (build.py, p4a 2026.05):
# 1) pin pip<25 nel bootstrap del venv host (pip 26 in aggiornamento
#    mescola versioni nel site-packages e rompe se stesso);
# 2) mantiene la patch cross-install --platform/--python-version.
# Uso: python3 patch_build_prod2.py   (idempotente)
import io
import shutil

BASE = "/mnt/c/PyTrainer/PC/PytTrainer/.buildozer/android/platform"
P = BASE + "/python-for-android/pythonforandroid/build.py"
VENV = BASE + "/build-arm64-v8a/build/venv"

src = io.open(P, encoding="utf-8").read()

old = '"source venv/bin/activate && pip install -U pip"'
new = '"source venv/bin/activate && pip install -U \'pip<25\'"'

if old in src:
    src = src.replace(old, new)
    io.open(P, "w", encoding="utf-8").write(src)
    print("PATCHED pip pin")
elif new in src:
    print("ALREADY PATCHED")
else:
    print("PATTERN NOT FOUND")

if src.count("--platform=android_24_arm64_v8a --implementation=cp") >= 1:
    print("CROSS-INSTALL OK")
else:
    print("CROSS-INSTALL MISSING")

shutil.rmtree(VENV, ignore_errors=True)
print("VENV RESET")
