"""Modelli di dominio immutabili."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

FREQS = ("none", "daily", "weekly", "monthly", "yearly")
PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH = 0, 1, 2


@dataclass(frozen=True)
class Recurrence:
    freq: str = "none"
    interval: int = 1
    weekdays: tuple[int, ...] = ()  # 0 = lunedì ... 6 = domenica (solo weekly)
    until: datetime | None = None

    def __post_init__(self) -> None:
        if self.freq not in FREQS:
            raise ValueError(f"Frequenza non valida: {self.freq}")
        if self.interval < 1:
            raise ValueError("L'intervallo deve essere almeno 1")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Giorno della settimana non valido")


@dataclass(frozen=True)
class Channels:
    popup: bool = True
    sound: bool = False
    email: bool = False
    telegram: bool = False


@dataclass(frozen=True)
class Reminder:
    title: str
    start: datetime
    id: int | None = None
    notes: str = ""
    priority: int = PRIORITY_NORMAL
    category: str = ""
    recurrence: Recurrence = Recurrence()
    alerts: tuple[int, ...] = (0,)  # minuti di preavviso (0 = all'ora esatta)
    channels: Channels = Channels()
    completed: bool = False
    armed_from: datetime | None = None  # nessun avviso prima di questo istante

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Il titolo non può essere vuoto")
        if not self.alerts:
            raise ValueError("Serve almeno un avviso")
        if any(a < 0 for a in self.alerts):
            raise ValueError("Il preavviso non può essere negativo")
        if self.priority not in (PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH):
            raise ValueError("Priorità non valida")

    @property
    def is_recurring(self) -> bool:
        return self.recurrence.freq != "none"


@dataclass(frozen=True)
class Due:
    """Un avviso che deve essere mostrato/inviato adesso."""

    reminder: Reminder
    occurrence: datetime
    offset_min: int
    missed: bool = False  # scattato mentre l'app era chiusa
    snoozed: bool = False


@dataclass(frozen=True)
class AgendaItem:
    reminder: Reminder
    occurrence: datetime
    done: bool
