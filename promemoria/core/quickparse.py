"""Inserimento rapido in italiano: "Dentista domani alle 15:30" -> titolo + data."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import Recurrence
from .recurrence import add_months

DEFAULT_TIME = time(9, 0)
_WD_FORMS = {
    0: ("lunedì", "lunedi"), 1: ("martedì", "martedi"), 2: ("mercoledì", "mercoledi"),
    3: ("giovedì", "giovedi"), 4: ("venerdì", "venerdi"), 5: ("sabato",), 6: ("domenica",),
}
WEEKDAYS = {form: wd for wd, forms in _WD_FORMS.items() for form in forms}
WD_RE = "(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + ")"
MONTHS = {m: i + 1 for i, m in enumerate((
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre"))}
MONTH_RE = "(" + "|".join(MONTHS) + ")"
FREQ_BY_UNIT = {"giorn": "daily", "settiman": "weekly", "mes": "monthly", "ann": "yearly"}
DAY_PARTS = {"mattina": 9, "stamattina": 9, "mezzogiorno": 12, "pomeriggio": 15,
             "sera": 20, "stasera": 20}
_EDGE_WORDS = {"il", "lo", "la", "di", "alle", "a", "e", "per", "da", "entro", "-", ",", ":"}


@dataclass(frozen=True)
class QuickParse:
    title: str
    start: datetime | None
    recurrence: Recurrence = Recurrence()

    @property
    def found_when(self) -> bool:
        return self.start is not None


class _Text:
    """Testo da cui vengono 'consumate' le parti riconosciute."""

    def __init__(self, text: str) -> None:
        self.value = f" {text} "

    def take(self, pattern: str) -> re.Match | None:
        m = re.search(pattern, self.value, re.IGNORECASE)
        if m:
            self.value = self.value[: m.start()] + " " + self.value[m.end():]
        return m


def _freq(unit: str) -> str:
    return next(f for prefix, f in FREQ_BY_UNIT.items() if unit.lower().startswith(prefix))


def _next_weekday(today: date, wd: int, allow_today: bool) -> date:
    ahead = (wd - today.weekday()) % 7
    if ahead == 0 and not allow_today:
        ahead = 7
    return today + timedelta(days=ahead)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _future_date(today: date, day: int, month: int, year: int | None) -> date | None:
    if year is not None:
        return _safe_date(year if year > 99 else 2000 + year, month, day)
    found = _safe_date(today.year, month, day)
    if found and found < today:
        found = _safe_date(today.year + 1, month, day)
    return found


def _parse_recurrence(t: _Text, today: date) -> tuple[Recurrence, date | None, bool]:
    m = t.take(r"\bogni\s+(\d+)\s+(giorni|settimane|mesi|anni)\b")
    if m:
        return Recurrence(_freq(m.group(2)), max(1, int(m.group(1)))), None, False
    m = t.take(r"\b(?:ogni|tutti\s+i|tutte\s+le)\s+(giorno|giorni|settimana|settimane|mese|mesi|anno|anni)\b")
    if m:
        return Recurrence(_freq(m.group(1))), None, False
    m = t.take(rf"\bogni\s+{WD_RE}\b")
    if m:
        wd = WEEKDAYS[m.group(1).lower()]
        return Recurrence("weekly", 1, (wd,)), _next_weekday(today, wd, True), True
    return Recurrence(), None, False


def _parse_relative(t: _Text, now: datetime) -> tuple[datetime | None, date | None]:
    if t.take(r"\btra\s+mezz'?\s?ora\b"):
        return (now + timedelta(minutes=30)).replace(second=0, microsecond=0), None
    m = t.take(r"\b(?:tra|fra)\s+(\d+|un|una|un')\s*(minut[oi]|or[ae]|giorn[oi]|settiman[ae]|mes[ei])\b")
    if not m:
        return None, None
    n = 1 if not m.group(1).isdigit() else int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("minut"):
        return (now + timedelta(minutes=n)).replace(second=0, microsecond=0), None
    if unit.startswith("or"):
        return (now + timedelta(hours=n)).replace(second=0, microsecond=0), None
    if unit.startswith("giorn"):
        return None, now.date() + timedelta(days=n)
    if unit.startswith("settiman"):
        return None, now.date() + timedelta(weeks=n)
    return None, add_months(now, n).date()


def _parse_date(t: _Text, today: date) -> date | None:
    for word, delta in (("dopodomani", 2), ("domani", 1), ("oggi", 0)):
        if t.take(rf"\b{word}\b"):
            return today + timedelta(days=delta)
    m = t.take(rf"\b(?:il\s+|l')?(\d{{1,2}})\s+{MONTH_RE}(?:\s+(\d{{4}}))?\b")
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return _future_date(today, int(m.group(1)), MONTHS[m.group(2).lower()], year)
    m = t.take(r"\b(?:il\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return _future_date(today, int(m.group(1)), int(m.group(2)), year)
    m = t.take(rf"\b(?:(?:il|la)\s+)?(?:prossim[oa]\s+)?{WD_RE}(?:\s+prossim[oa])?\b")
    if m:
        return _next_weekday(today, WEEKDAYS[m.group(1).lower()], False)
    m = t.take(r"\bil\s+(\d{1,2})\b")
    if m:
        day = int(m.group(1))
        found = _safe_date(today.year, today.month, day)
        if found is None or found < today:
            nxt = add_months(datetime.combine(today.replace(day=1), time()), 1)
            found = _safe_date(nxt.year, nxt.month, day)
        return found
    return None


def _parse_time(t: _Text) -> tuple[time | None, bool]:
    """Ritorna (orario, implica_oggi)."""
    m = t.take(r"(?:\balle|\ball'|\bore|\bh)\s*([01]?\d|2[0-3])(?:[:.]([0-5]\d))?\b")
    if not m:
        m = t.take(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
    if m:
        return time(int(m.group(1)), int(m.group(2) or 0)), False
    m = t.take(r"\b(?:di\s+|in\s+)?(stamattina|stasera|mattina|pomeriggio|sera|mezzogiorno)\b")
    if m:
        word = m.group(1).lower()
        return time(DAY_PARTS[word], 0), word.startswith("sta")
    return None, False


def _clean_title(raw: str) -> str:
    words = raw.split()
    while words and words[0].lower() in _EDGE_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _EDGE_WORDS:
        words.pop()
    title = " ".join(words).strip(" ,;-")
    return (title[:1].upper() + title[1:]) if title else "Promemoria"


def parse(text: str, now: datetime | None = None) -> QuickParse:
    now = now or datetime.now()
    today = now.date()
    t = _Text(text)

    recurrence, rec_day, rec_day_flexible = _parse_recurrence(t, today)
    exact, rel_day = _parse_relative(t, now)
    day = _parse_date(t, today) or rel_day
    tm, implies_today = _parse_time(t)
    title = _clean_title(t.value)

    if exact is not None:
        return QuickParse(title, exact, recurrence)
    if day is None and implies_today:
        day = today
    explicit_day = day is not None
    day = day or rec_day
    if day is None and tm is None and recurrence.freq == "none":
        return QuickParse(title, None, recurrence)

    start = datetime.combine(day or today, tm or DEFAULT_TIME)
    if start <= now and not explicit_day:
        start += timedelta(days=7 if rec_day_flexible else 1)
    return QuickParse(title, start, recurrence)
