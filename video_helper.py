"""Compatibility re-export for :mod:`core.video_helper`."""

import sys

from core import video_helper as _core_module

sys.modules[__name__] = _core_module
