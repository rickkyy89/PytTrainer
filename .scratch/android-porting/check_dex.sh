#!/usr/bin/env bash
cd /home/rickk/spike-builder/app
rm -rf /tmp/spx && mkdir -p /tmp/spx && cd /tmp/spx
unzip -o -q /home/rickk/spike-builder/app/bin/pttspike-0.1-arm64-v8a-debug.apk
echo "== dex files =="
ls -la *.dex
echo "== search FFmpegKit =="
for d in *.dex; do
  echo "-- $d --"
  /home/rickk/.buildozer/android/platform/android-sdk/build-tools/37.0.0/dexdump "$d" 2>/dev/null | grep -i "Class descriptor.*FFmpegKit\|Class descriptor.*arthenica" | head -20
done
