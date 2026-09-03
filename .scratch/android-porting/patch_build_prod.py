#!/usr/bin/env python
# Patch per la build di produzione (cache .buildozer del progetto, p4a 2026.05):
# aggiunge --platform / --implementation / --python-version / --only-binary
# al comando pip install delle requirements, come gia' fatto per lo spike
# (patch_build.py). Senza queste flags il pip desktop rifiuta i wheel
# cp314-android dei moduli binari.
import io

p = "/mnt/c/PyTrainer/PC/PytTrainer/.buildozer/android/platform/python-for-android/pythonforandroid/build.py"
src = io.open(p, encoding="utf-8").read()

old = (
    '"venv/bin/pip " +\n'
    '                "install -v --target \'{0}\' --no-deps -r requirements.txt"\n'
)
new = (
    '"venv/bin/pip " +\n'
    '                "install -v --target \'{0}\' --no-deps --only-binary=:all: "\n'
    '                "--platform=android_24_arm64_v8a --implementation=cp "\n'
    '                "--python-version=3.14 -r requirements.txt"\n'
)

if "--platform=android_24_arm64_v8a --implementation=cp" in src:
    print("ALREADY PATCHED")
elif old in src:
    src = src.replace(old, new)
    io.open(p, "w", encoding="utf-8").write(src)
    print("PATCHED")
else:
    print("PATTERN NOT FOUND")
