#!/usr/bin/env bash
# Stampa i permessi Android realmente dichiarati nell'APK.
APK=${1:-/mnt/c/PyTrainer/PC/PytTrainer/bin/pyTrainer-0.1-arm64-v8a-debug.apk}
AAPT=$(find /home/rickk -type f -name aapt -path '*build-tools*' 2>/dev/null | tail -1)
"$AAPT" dump badging "$APK" 2>/dev/null | grep -i 'uses-permission'
