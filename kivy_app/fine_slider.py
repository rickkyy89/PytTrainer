"""Scrub slider with linear tap-jump and fine drag sensitivity.

The stock Kivy ``Slider`` maps the whole widget width onto the full ``[min,
max]`` range, so on long videos a few millimetres of finger travel translate
into many seconds.  This widget splits the two gestures:

* a **tap** (press and release without dragging) jumps linearly to the touched
  position, so a distant point is reached in one step;
* a **drag** (press then move) is scaled by :attr:`FINE_FACTOR`, so small
  movements produce small timestamp deltas — useful for picking the exact
  frame on a long video.

The commit handler already bound to ``on_touch_up`` keeps working: the value
set by these gestures is what the caller observes on release.
"""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.slider import Slider


class FineSlider(Slider):
    """Slider whose drag moves ``FINE_FACTOR`` of the range per full width."""

    FINE_FACTOR = 0.10
    DRAG_THRESHOLD_DP = 8

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_touch = None
        self._press_x = 0.0
        self._press_value = 0.0
        self._dragging = False

    def _span(self):
        return self.max - self.min

    def _frac_at(self, position):
        """Normalised [0, 1] position inside the widget for a given x."""
        width = max(self.width, 1)
        return min(max((position - self.x) / width, 0.0), 1.0)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self._active_touch = touch
        self._press_x = touch.x
        # Tap/jump: move linearly to the touched position straight away.
        self.value = self.min + self._frac_at(touch.x) * self._span()
        self._press_value = self.value
        self._dragging = False
        return True

    def on_touch_move(self, touch):
        if touch is not self._active_touch:
            return super().on_touch_move(touch)
        if abs(touch.x - self._press_x) > dp(self.DRAG_THRESHOLD_DP):
            self._dragging = True
        if self._dragging:
            # Reduced sensitivity: the whole width covers FINE_FACTOR of range,
            # so small finger movements give small value deltas.
            delta = (touch.x - self._press_x) / max(self.width, 1) * self._span() * self.FINE_FACTOR
            self.value = min(max(self._press_value + delta, self.min), self.max)
        return True

    def on_touch_up(self, touch):
        if touch is not self._active_touch:
            return super().on_touch_up(touch)
        self._active_touch = None
        self._dragging = False
        return True
