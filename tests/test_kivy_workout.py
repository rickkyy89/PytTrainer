"""Workout session controller (ticket 09); no Kivy, no real clock."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.workout import (
    WorkoutError,
    WorkoutSessionController,
    parse_recupero_secondi,
)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, delta):
        self.t += delta


def make_session(orari=None, **kw):
    esercizi = orari or [
        {"nome": "Squat", "ripetizioni": "3x12", "recupero": "90 SEC", "note": "Ginocchia."},
        {"nome": "Plank", "ripetizioni": "1x60s", "recupero": "1:30", "note": ""},
        {"nome": "Cosa", "ripetizioni": "", "recupero": "bizzarro", "note": ""},
    ]
    clock = FakeClock()
    kw.setdefault("monotonic", clock)
    return WorkoutSessionController(esercizi, **kw), clock


# ---------------------------------------------------------------- parsing

@pytest.mark.parametrize("testo, atteso", [
    ("90 SEC", 90),
    ("120 sec", 120),
    ("90s", 90),
    ("90", 90),
    ("1:30", 90),
    ("0:45", 45),
    ("2 min", 120),
    ("1 min 30 sec", 90),
    ("2m", 120),
    ("", None),
    (None, None),
    ("bizzarro", None),
    ("3x12", None),
])
def test_parse_recupero_secondi_formatti(testo, atteso):
    assert parse_recupero_secondi(testo) == atteso


# ------------------------------------------------------------ checkboxes

def test_spunte_segnano_stato_di_sessione_azzera_riporta_pulito():
    sessione, _ = make_session()

    assert sessione.toggle_completato(0) is True
    assert sessione.completato(0) is True
    assert sessione.conteggio_completati() == 1
    assert sessione.toggle_completato(0) is False
    assert sessione.conteggio_completati() == 0

    sessione.toggle_completato(1)
    sessione.azzera_sessione()
    assert sessione.conteggio_completati() == 0
    with pytest.raises(WorkoutError):
        sessione.toggle_completato(99)


# ---------------------------------------------------------------- timer

def test_timer_legge_durata_dal_campo_recupero_e_scende_col_tempo():
    sessione, clock = make_session()

    assert sessione.avvia_recupero(0) == 90
    assert sessione.recupero_rimasto() == 90
    clock.advance(30)
    assert sessione.recupero_rimasto() == 60
    assert sessione.recupero_finito() is False
    clock.advance(60)
    assert sessione.recupero_rimasto() == 0
    assert sessione.recupero_finito() is True
    assert sessione.esercizio_in_timer == 0


def test_timer_parse_m_s_e_default_su_valore_impossibile():
    sessione, clock = make_session()

    assert sessione.avvia_recupero(1) == 90          # "1:30"
    assert sessione.avvia_recupero(2) == 60          # "bizzarro" -> default 60
    assert sessione.avvia_recupero(2, secondi=15) == 15
    clock.advance(15)
    assert sessione.recupero_finito() is True


def test_timer_riavviabile_e_annullabile():
    sessione, clock = make_session()
    sessione.avvia_recupero(0)
    clock.advance(5)

    sessione.avvia_recupero(1)
    assert sessione.recupero_rimasto() == 90

    sessione.annulla_recupero()
    assert sessione.recupero_attivo() is False
    assert sessione.recupero_rimasto() == 0
    assert sessione.esercizio_in_timer is None
