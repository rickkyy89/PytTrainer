#!/usr/bin/env bash
# Esegue un comando dentro l'ambiente pyenv+venv dello spike.
# Usage: wslcmd.sh <comando...>
source /mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/wsl_env.sh
pyenv shell 3.11.9
. /home/rickk/spike-builder/venv/bin/activate
exec "$@"
