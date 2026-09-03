"""End-of-recovery notification (ticket 09), platform-guarded and silent on failure."""

from __future__ import annotations

import sys


def notifica_fine_recupero(testo: str = "Recupero finito") -> bool:
    """Signal the end of a countdown via the best platform mechanism.

    Never raises: a missing sound/vibration backend must not break the UI
    loop. Returns True when at least one channel was triggered.
    """
    ok = False
    if sys.platform == "win32":
        try:
            import winsound

            for _ in range(3):
                winsound.MessageBeep(winsound.MB_OK)
            ok = True
        except Exception:
            pass
    else:
        try:
            from plyer import vibration

            vibration.vibrate(1.0)
            ok = True
        except Exception:
            pass
    if not ok:
        try:
            from plyer import notification

            notification.notify(title="pyTrainer", message=testo, timeout=5)
            ok = True
        except Exception:
            pass
    return ok
