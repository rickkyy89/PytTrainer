"""Session-only workout mode for one opened scheda (ticket 09).

``WorkoutSessionController`` tracks which exercises are checked off during the
session (never persisted into the bundle) and the recovery countdown whose
duration is parsed from the free-text ``Recupero`` field ("90 SEC", "1:30",
"2 min", ...).  All time reads go through an injected monotonic clock so the
countdown logic is fully testable.  The UI layer owns ticking, sounds and
vibration; this module only computes.
"""

from __future__ import annotations

import math
import re
import time


DEFAULT_RECUPERO_SECONDI = 60

_COLON = re.compile(r"^(\d+):([0-5]?\d)$")
_MIN_SEC = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:min(?:ut[oi])?|m)\s*(\d+)\s*(?:sec(?:ondi)?|s)?$",
                      re.IGNORECASE)
_MIN_ONLY = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:min(?:ut[oi])?|m)$", re.IGNORECASE)
_SEC_ONLY = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:sec(?:ondi)?|s)?$", re.IGNORECASE)


def parse_recupero_secondi(testo: str | None) -> int | None:
    """Return whole seconds from the free-text Recupero field, or None.

    Supported (anchored, full-string) shapes: "90", "90 SEC", "90s", "1:30"
    (m:ss), "1m30", "2 min", "1 min 30 sec". Anything else returns None so the
    caller can fall back to a default or disable the timer.
    """
    if testo is None:
        return None
    testo = str(testo).strip().replace(",", ".")
    if not testo:
        return None

    m = _COLON.match(testo)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    m = _MIN_SEC.match(testo)
    if m:
        return round(float(m.group(1)) * 60 + float(m.group(2)))

    m = _MIN_ONLY.match(testo)
    if m:
        return round(float(m.group(1)) * 60)

    m = _SEC_ONLY.match(testo)
    if m:
        return round(float(m.group(1)))

    return None


class WorkoutError(Exception):
    """A user-facing failure in workout mode."""


class WorkoutSessionController:
    """Checkboxes + recovery countdown for one training session."""

    def __init__(self, esercizi, *, monotonic=time.monotonic,
                 default_secondi=DEFAULT_RECUPERO_SECONDI):
        self._esercizi = esercizi
        self._mono = monotonic
        self._default = default_secondi
        self._completati: set[int] = set()
        self._scadenza: float | None = None
        self._durata: float | None = None
        self._esercizio_timer: int | None = None

    # ---------------------------------------------------------- esercizi

    @property
    def esercizi(self):
        return self._esercizi

    def toggle_completato(self, indice: int) -> bool:
        self._esame(indice)
        if indice in self._completati:
            self._completati.discard(indice)
            return False
        self._completati.add(indice)
        return True

    def completato(self, indice: int) -> bool:
        return indice in self._completati

    def conteggio_completati(self) -> int:
        return len(self._completati)

    def azzera_sessione(self) -> None:
        self._completati.clear()
        self._scadenza = None
        self._durata = None
        self._esercizio_timer = None

    # ----------------------------------------------------------- timer

    def secondi_recupero(self, indice: int) -> int | None:
        """Parsed recovery duration for one exercise (None = not parseable)."""
        return parse_recupero_secondi(self._esame(indice).get("recupero"))

    def avvia_recupero(self, indice: int, *, secondi: int | None = None) -> int:
        """Start the countdown; returns the chosen duration in seconds.

        Falls back to the exercise's Recupero field, then to the default.
        """
        self._esame(indice)
        durata = secondi
        if durata is None:
            durata = self.secondi_recupero(indice)
        if durata is None or durata <= 0:
            durata = self._default
        self._durata = float(durata)
        self._scadenza = self._mono() + self._durata
        self._esercizio_timer = indice
        return int(durata)

    def recupero_attivo(self) -> bool:
        return self._scadenza is not None

    def recupero_rimasto(self, *, now: float | None = None) -> int:
        """Whole seconds left (ceil); 0 once finished. Keeps the value after
        expiry so the UI can show the finished state until a new start."""
        if self._scadenza is None:
            return 0
        now = self._mono() if now is None else now
        return max(0, math.ceil(self._scadenza - now))

    def recupero_finito(self, *, now: float | None = None) -> bool:
        return self._scadenza is not None and self.recupero_rimasto(now=now) == 0

    def annulla_recupero(self) -> None:
        self._scadenza = None
        self._durata = None
        self._esercizio_timer = None

    @property
    def esercizio_in_timer(self) -> int | None:
        return self._esercizio_timer

    def _esame(self, indice: int):
        try:
            return self._esercizi[indice]
        except IndexError as exc:
            raise WorkoutError(f"Indice esercizio non valido: {indice + 1}.") from exc
