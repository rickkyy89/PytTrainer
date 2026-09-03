#!/usr/bin/env bash
# Stato della build di produzione in WSL: processi reali + ultima riga di log.
LOG=${1:-/mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/prod_build4.log}
ps -eo pid,etime,cmd | grep -E 'buildozer|pythonforandroid|python3?.*apk|gradle' | grep -v grep | head -5
echo "--- log: $LOG"
if [ -f "$LOG" ]; then
  sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$LOG" | grep -v '^\[DEBUG\]' | tail -n 4
else
  echo "LOG ASSENTE"
fi
