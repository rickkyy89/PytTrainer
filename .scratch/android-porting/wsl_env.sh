#!/usr/bin/env bash
# Carica pyenv e prepone il suo binario al PATH.
export PYENV_ROOT="/home/rickk/.pyenv"
# Source pyenv senza rileggere tutto .bashrc (che potrebbe rompersi)
if [ -f "$PYENV_ROOT/bin/pyenv" ]; then
  export PATH="$PYENV_ROOT/bin:$PATH"
  eval "$(pyenv init -)"
fi
