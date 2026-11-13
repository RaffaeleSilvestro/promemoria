"""Formattazione in italiano di date, ricorrenze e preavvisi."""
from __future__ import annotations

from datetime import date, datetime

from .models import Recurrence

DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
DAYS_SHORT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
MONTHS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
PRIORITIES = {0: "Bassa", 1: "Normale", 2: "Alta"}
FREQ_LABELS = {
    "none": "Mai", "daily": "Ogni giorno", "weekly": "Ogni settimana",
    "monthly": "Ogni mese", "yearly": "Ogni anno",
}
_UNITS = {"daily": ("giorno", "giorni"), "weekly": ("settimana", "settimane"),
          "monthly": ("mese", "mesi"), "yearly": ("anno", "anni")}


def format_when(dt: datetime) -> str:
    return f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month - 1]} {dt.year} alle {dt:%H:%M}"


def format_short(dt: datetime) -> str:
    return f"{DAYS_SHORT[dt.weekday()]} {dt:%d/%m/%Y %H:%M}"


def format_day(d: date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def day_label(d: date, today: date) -> str:
    """'Oggi', 'Domani', 'Ieri' oppure 'sabato 14 novembre'."""
    names = {0: "Oggi", 1: "Domani", -1: "Ieri"}
    delta = (d - today).days
    if delta in names:
        return f"{names[delta]} · {format_day(d)}"
    text = format_day(d)
    if d.year != today.year:
        text += f" {d.year}"
    return text[:1].upper() + text[1:]


def format_relative(dt: datetime, now: datetime) -> str:
    """Descrizione breve per l'anteprima: 'domani alle 15:30'."""
    delta = (dt.date() - now.date()).days
    day = {0: "oggi", 1: "domani", 2: "dopodomani"}.get(delta, format_day(dt.date()))
    return f"{day} alle {dt:%H:%M}"


def format_offset(minutes: int) -> str:
    if minutes == 0:
        return "All'ora dell'evento"
    for size, one, many in ((10080, "settimana", "settimane"), (1440, "giorno", "giorni"),
                            (60, "ora", "ore"), (1, "minuto", "minuti")):
        if minutes % size == 0:
            n = minutes // size
            return f"{n} {one if n == 1 else many} prima"
    return f"{minutes} minuti prima"


def format_recurrence(rec: Recurrence) -> str:
    if rec.freq == "none":
        return ""
    one, many = _UNITS[rec.freq]
    text = f"Ogni {one}" if rec.interval == 1 else f"Ogni {rec.interval} {many}"
    if rec.freq == "weekly" and rec.weekdays:
        text += " (" + ", ".join(DAYS_SHORT[d] for d in sorted(rec.weekdays)) + ")"
    if rec.until:
        text += f" fino al {rec.until:%d/%m/%Y}"
    return text
