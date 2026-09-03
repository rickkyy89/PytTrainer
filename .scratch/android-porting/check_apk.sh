#!/usr/bin/env bash
# Verifica applicazione + contenuto sensibile dell'APK (asset private.tar).
set -e
APK=${1:-/mnt/c/PyTrainer/PC/PytTrainer/bin/pyTrainer-0.1-arm64-v8a-debug.apk}
AAPT=$(find /home/rickk -type f -name aapt -path '*build-tools*' 2>/dev/null | tail -1)
echo "== package =="
"$AAPT" dump badging "$APK" | head -1
echo "== contents =="
python3 - "$APK" <<'PY'
import sys, tarfile, io, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = [n.filename for n in z.infolist()]
leak = [n for n in names if any(k in n.lower() for k in
        ("credentials", "token.json", "service_account", "drive-folders"))]
print("apk entries:", len(names))
private = [n for n in names if n.endswith("private.tar")]
if private:
    with z.open(private[0]) as fh:
        inner = tarfile.open(fileobj=io.BytesIO(fh.read()))
    members = inner.getnames()
    print("private files:", len(members))
    bad = [m for m in members if any(k in m.lower() for k in
           ("credentials", "token.json", "service_account", ".work",
            "drive-cache", "frames/"))]
    leak += bad
else:
    print("no private.tar asset")
print("LEAKS:", leak or "none")
PY
