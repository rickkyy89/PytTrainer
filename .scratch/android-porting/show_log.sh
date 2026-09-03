#!/usr/bin/env bash
# Mostra un range di righe di un log buildozer senza codici colore.
# Uso: show_log.sh <log> <da> <a>
sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$1" | sed -n "${2},${3}p"
