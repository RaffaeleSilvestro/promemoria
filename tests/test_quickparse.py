from datetime import datetime

from promemoria.core.models import Recurrence
from promemoria.core.quickparse import parse

NOW = datetime(2026, 11, 13, 10, 0)  # venerdì


def test_tomorrow_with_time():
    p = parse("Dentista domani alle 15:30", NOW)
    assert p.title == "Dentista" and p.start == datetime(2026, 11, 14, 15, 30)


def test_relative_hours():
    p = parse("Chiama mamma tra 2 ore", NOW)
    assert p.title == "Chiama mamma" and p.start == datetime(2026, 11, 13, 12, 0)


def test_relative_minutes_and_days():
    assert parse("Tè tra 30 minuti", NOW).start == datetime(2026, 11, 13, 10, 30)
    assert parse("Revisione tra 3 giorni", NOW).start == datetime(2026, 11, 16, 9, 0)


def test_every_weekday_with_time():
    p = parse("Palestra ogni lunedì alle 18", NOW)
    assert p.recurrence == Recurrence("weekly", 1, (0,))
    assert p.start == datetime(2026, 11, 16, 18, 0) and p.title == "Palestra"


def test_day_month_name_defaults_to_nine():
    p = parse("Pagare affitto il 5 dicembre", NOW)
    assert p.start == datetime(2026, 12, 5, 9, 0) and p.title == "Pagare affitto"


def test_daily_time_already_passed_starts_tomorrow():
    p = parse("Pillola ogni giorno alle 8", NOW)
    assert p.recurrence.freq == "daily" and p.start == datetime(2026, 11, 14, 8, 0)


def test_no_date_returns_none():
    p = parse("Compra latte", NOW)
    assert p.start is None and p.title == "Compra latte" and not p.found_when


def test_numeric_date_with_dot_time():
    assert parse("Riunione 20/11 alle 9.30", NOW).start == datetime(2026, 11, 20, 9, 30)


def test_same_weekday_means_next_week():
    assert parse("Cena venerdì", NOW).start == datetime(2026, 11, 20, 9, 0)


def test_time_only_passed_goes_tomorrow():
    assert parse("Chiamare alle 9", NOW).start == datetime(2026, 11, 14, 9, 0)
    assert parse("Chiamare alle 18", NOW).start == datetime(2026, 11, 13, 18, 0)


def test_interval_recurrence():
    p = parse("Bucato ogni 2 settimane domani", NOW)
    assert p.recurrence == Recurrence("weekly", 2, (4,)) or p.recurrence.interval == 2


def test_day_part_words():
    assert parse("Palestra sabato mattina", NOW).start == datetime(2026, 11, 14, 9, 0)
    assert parse("Cena stasera", NOW).start == datetime(2026, 11, 13, 20, 0)


def test_past_numeric_date_rolls_to_next_year():
    assert parse("Compleanno 2/3", NOW).start == datetime(2027, 3, 2, 9, 0)
