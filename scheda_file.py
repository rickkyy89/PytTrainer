"""Compatibility re-export for :mod:`core.scheda_file`."""

import sys

from core import scheda_file as _core_module

sys.modules[__name__] = _core_module
