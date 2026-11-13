"""Logica di scheduling: cosa deve scattare adesso e cosa c'è in agenda."""
from __future__ import annotations

from datetime import datetime, timedelta

from .db import Repository, key
from .models import AgendaItem, Due
from .recurrence import occurrences

MISSED_AFTER = timedelta(minutes=2)


def due_notifications(
    repo: Repository, now: datetime, lookback: timedelta = timedelta(hours=24)
) -> list[Due]:
    """Avvisi scaduti non ancora inviati. Li registra come inviati."""
    window_start = now - lookback
    done = repo.done_set()
    result: list[Due] = []
    by_id = {}

    for r in repo.list():
        by_id[r.id] = r
        if r.completed:
            continue
        earliest = max(window_start, r.armed_from or window_start)
        horizon = now + timedelta(minutes=max(r.alerts))
        for occ in occurrences(r.start, r.recurrence, window_start, horizon):
            if (r.id, key(occ)) in done:
                continue
            for offset in sorted(r.alerts, reverse=True):
                trigger = occ - timedelta(minutes=offset)
                if trigger > now or trigger < earliest:
                    continue
                if repo.mark_fired(r.id, occ, offset):
                    result.append(
                        Due(r, occ, offset, missed=now - trigger > MISSED_AFTER)
                    )

    for reminder_id, occ in repo.pop_due_snoozes(now):
        r = by_id.get(reminder_id)
        if r is None or r.completed or (r.id, key(occ)) in done:
            continue
        result.append(Due(r, occ, 0, snoozed=True))

    return sorted(result, key=lambda d: d.occurrence)


def agenda(repo: Repository, frm: datetime, to: datetime) -> list[AgendaItem]:
    """Tutte le occorrenze nell'intervallo, ordinate per data."""
    done = repo.done_set()
    items: list[AgendaItem] = []
    for r in repo.list():
        for occ in occurrences(r.start, r.recurrence, frm, to):
            is_done = (r.completed and not r.is_recurring) or (r.id, key(occ)) in done
            items.append(AgendaItem(r, occ, is_done))
    return sorted(items, key=lambda i: (i.occurrence, -i.reminder.priority))


def overdue(repo: Repository, now: datetime) -> list[AgendaItem]:
    """Promemoria singoli non completati e già passati."""
    return [
        AgendaItem(r, r.start, False)
        for r in repo.list()
        if not r.is_recurring and not r.completed and r.start < now
    ]


def mark_done(repo: Repository, item: AgendaItem, done: bool = True) -> None:
    r = item.reminder
    if r.is_recurring:
        repo.set_done(r.id, item.occurrence, done)
    else:
        repo.set_completed(r.id, done)


def snooze(repo: Repository, due: Due, minutes: int, now: datetime) -> None:
    repo.add_snooze(due.reminder.id, due.occurrence, now + timedelta(minutes=minutes))
