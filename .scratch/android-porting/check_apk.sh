#!/usr/bin/env bash
set -e
APK=/mnt/c/PyTrainer/PC/PytTrainer/bin/pyTrainer-0.1-arm64-v8a-debug.apk
AAPT=$(find /home/rickk -type f -name aapt -path '*build-tools*' 2>/dev/null | tail -1)
if [ -z "$AAPT" ]; then AAPT=$(find / -type f -name aapt -path '*build-tools*' -not -path '/mnt/*' 2>/dev/null | tail -1); fi
echo "AAPT=$AAPT"
"$AAPT" dump badging "$APK" | head -2
