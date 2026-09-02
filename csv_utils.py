"""Compatibility re-export for :mod:`core.csv_utils`."""

import sys

from core import csv_utils as _core_module

sys.modules[__name__] = _core_module
