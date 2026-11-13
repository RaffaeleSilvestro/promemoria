from datetime import date, datetime

from promemoria.core.formatting import (
    day_label,
    format_offset,
    format_recurrence,
    format_relative,
    format_short,
    format_when,
)
from promemoria.core.models import Recurrence


def test_format_when_and_short():
    dt = datetime(2026, 11, 13, 15, 30)
    assert format_when(dt) == "venerdì 13 novembre 2026 alle 15:30"
    assert format_short(dt) == "Ven 13/11/2026 15:30"


def test_format_offset_units():
    assert format_offset(0) == "All'ora dell'evento"
    assert format_offset(1) == "1 minuto prima"
    assert format_offset(10) == "10 minuti prima"
    assert format_offset(60) == "1 ora prima"
    assert format_offset(180) == "3 ore prima"
    assert format_offset(1440) == "1 giorno prima"
    assert format_offset(10080) == "1 settimana prima"
    assert format_offset(90) == "90 minuti prima"


def test_format_recurrence():
    assert format_recurrence(Recurrence()) == ""
    assert format_recurrence(Recurrence("daily")) == "Ogni giorno"
    assert format_recurrence(Recurrence("monthly", 3)) == "Ogni 3 mesi"
    weekly = Recurrence("weekly", 2, (4, 0), until=datetime(2027, 1, 31))
    assert format_recurrence(weekly) == "Ogni 2 settimane (Lun, Ven) fino al 31/01/2027"


def test_day_label_relative_and_other_year():
    today = date(2026, 11, 13)
    assert day_label(today, today) == "Oggi · venerdì 13 novembre"
    assert day_label(date(2026, 11, 14), today).startswith("Domani")
    assert day_label(date(2026, 11, 12), today).startswith("Ieri")
    assert day_label(date(2026, 11, 20), today) == "Venerdì 20 novembre"
    assert day_label(date(2027, 1, 5), today) == "Martedì 5 gennaio 2027"


def test_format_relative():
    now = datetime(2026, 11, 13, 10, 0)
    assert format_relative(datetime(2026, 11, 13, 18, 0), now) == "oggi alle 18:00"
    assert format_relative(datetime(2026, 11, 14, 9, 5), now) == "domani alle 09:05"
    assert format_relative(datetime(2026, 11, 20, 9, 0), now) == "venerdì 20 novembre alle 09:00"
