#!/usr/bin/env python
# Aggiunge invoke()/get()/set() alle classi reflect.Method/Field/Constructor di pyjnius
# cosi' il codice Python puo' invocare metodi/fonti per reflection.
import io

paths = [
    "/home/rickk/spike-builder/app/.buildozer/android/platform/build-arm64-v8a/build/other_builds/pyjnius-sdl2/arm64-v8a__ndk_target_24/pyjnius/jnius/reflect.py",
    "/home/rickk/spike-builder/app/.buildozer/android/platform/build-arm64-v8a/build/python-installs/pttspike/arm64-v8a/jnius/reflect.py",
]

# snippet da iniettare: i metodi invoke/get/set mancanti
METHOD_ADD = """
    invoke = JavaMultipleMethod([
        ("(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;", True, False),
        ("(Ljava/lang/Object;)Ljava/lang/Object;", True, False),
        ("()Ljava/lang/Object;", True, False),
    ])
"""

FIELD_ADD = """
    get = JavaMultipleMethod([
        ("(Ljava/lang/Object;)Ljava/lang/Object;", True, False),
        ("()Ljava/lang/Object;", True, False),
    ])
    set = JavaMultipleMethod([
        ("(Ljava/lang/Object;Ljava/lang/Object;)V", True, False),
        ("(Ljava/lang/Object;)V", True, False),
    ])
"""

for p in paths:
    try:
        src = io.open(p, encoding="utf-8").read()
    except OSError:
        print("SKIP (not found):", p)
        continue

    changed = False
    # Method: aggiungi invoke prima della riga "class Field"
    if "invoke = JavaMultipleMethod" not in src and "class Field(" in src:
        src = src.replace("class Field(", METHOD_ADD + "\n\nclass Field(", 1)
        changed = True
    # Field: aggiungi get/set prima della riga "class Constructor"
    if 'get = JavaMultipleMethod' not in src and "class Constructor(" in src:
        src = src.replace("class Constructor(", FIELD_ADD + "\n\nclass Constructor(", 1)
        changed = True
    if changed:
        io.open(p, "w", encoding="utf-8").write(src)
        print("PATCHED:", p)
    else:
        print("NO-CHANGE:", p)
