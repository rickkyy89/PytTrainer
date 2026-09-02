#!/usr/bin/env python
# Patch temporanea di python-for-android/build.py:
# aggiunge --platform / --implementation / --python-version / --only-binary
# al comando pip install delle requirements, come gia' fa per la risoluzione.
import io, os, re

p = "/home/rickk/spike-builder/app/.buildozer/android/platform/python-for-android/pythonforandroid/build.py"
src = io.open(p, encoding="utf-8").read()

old = (
    'pip " +\n'
    '                "install -v --target \'{0}\' --no-deps -r requirements.txt"\n'
)
new = (
    'pip " +\n'
    '                "install -v --target \'{0}\' --no-deps --only-binary=:all: "\n'
    '                "--platform=android_24_arm64_v8a --implementation=cp "\n'
    '                "--python-version=3.14 -r requirements.txt"\n'
)

if old in src:
    src = src.replace(old, new)
    io.open(p, "w", encoding="utf-8").write(src)
    print("PATCHED")
else:
    print("PATTERN NOT FOUND")
