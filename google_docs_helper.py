"""Compatibility re-export for :mod:`core.docs_helper`."""

import sys

from core import docs_helper as _core_module

sys.modules[__name__] = _core_module
