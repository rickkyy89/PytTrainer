#!/usr/bin/env python
import py_compile

src = "/home/rickk/spike-builder/app/.buildozer/android/platform/build-arm64-v8a/build/python-installs/pttspike/arm64-v8a/jnius/reflect.py"
cfile = "/home/rickk/spike-builder/app/.buildozer/android/platform/build-arm64-v8a/build/python-installs/pttspike/arm64-v8a/jnius/reflect.pyc"
py_compile.compile(src, cfile=cfile)
print("pyc recompiled")
