#!/usr/bin/env bash
# Mostra le righe di errore di un log buildozer.
LOG=${1:-/mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/prod_build4.log}
sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$LOG" | grep -nE 'Error|error:|ERROR|failed|Failed|FAILURE|No matching|could not|Could not' | tail -n 20
echo '=== contesto attorno a "Command failed" ==='
sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$LOG" | grep -n 'Command failed' | tail -n 1
