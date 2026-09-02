#!/usr/bin/env bash
# wrapper per lanciare buildozer con l'ambiente pyenv corretto
set -e
source /mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/wsl_env.sh
pyenv shell 3.11.9
. /home/rickk/spike-builder/venv/bin/activate
cd /home/rickk/spike-builder/app
exec buildozer "$@"
