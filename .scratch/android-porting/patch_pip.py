#!/usr/bin/env python
# Patch temporanea: limita pip alla versione <25 nel venv host di p4a,
# perche' pip 26 ha rimosso BuildDependencyInstallError.
import io

p = "/home/rickk/spike-builder/app/.buildozer/android/platform/python-for-android/pythonforandroid/build.py"
src = io.open(p, encoding="utf-8").read()

old = '"source venv/bin/activate && pip install -U pip"'
new = '"source venv/bin/activate && pip install -U \'pip<25\'"'

if old in src:
    src = src.replace(old, new)
    io.open(p, "w", encoding="utf-8").write(src)
    print("PATCHED pip pin")
else:
    print("PATTERN NOT FOUND")
