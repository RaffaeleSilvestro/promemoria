"""Generazione delle occorrenze di un promemoria ricorrente."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, time, timedelta
from typing import Iterator

from .models import Recurrence


def add_months(dt: datetime, months: int) -> datetime:
    """Somma mesi limitando il giorno all'ultimo del mese (31 gen + 1 -> 28/29 feb)."""
    total = dt.year * 12 + (dt.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def occurrences(
    start: datetime, rec: Recurrence, frm: datetime, to: datetime
) -> Iterator[datetime]:
    """Occorrenze con frm <= occ <= to, in ordine crescente."""
    if to < frm:
        return
    limit = to
    if rec.until is not None:
        limit = min(to, datetime.combine(rec.until.date(), time.max))

    if rec.freq == "none":
        if frm <= start <= limit:
            yield start
        return
    if rec.freq == "daily":
        yield from _daily(start, rec.interval, frm, limit)
    elif rec.freq == "weekly":
        yield from _weekly(start, rec, frm, limit)
    elif rec.freq == "monthly":
        yield from _monthly(start, rec.interval, frm, limit)
    elif rec.freq == "yearly":
        yield from _monthly(start, rec.interval * 12, frm, limit)


def _daily(start: datetime, interval: int, frm: datetime, limit: datetime):
    step = timedelta(days=interval)
    k = max(0, (frm - start) // step)
    cur = start + k * step
    while cur <= limit:
        if cur >= frm:
            yield cur
        cur += step


def _weekly(start: datetime, rec: Recurrence, frm: datetime, limit: datetime):
    weekdays = sorted(set(rec.weekdays)) or [start.weekday()]
    week0 = (start - timedelta(days=start.weekday())).replace(
        hour=start.hour, minute=start.minute, second=0, microsecond=0
    )
    weeks_elapsed = max(0, (frm - week0).days // 7)
    w = (weeks_elapsed // rec.interval) * rec.interval
    while True:
        monday = week0 + timedelta(weeks=w)
        if monday > limit:
            return
        for wd in weekdays:
            cur = monday + timedelta(days=wd)
            if cur < start or cur < frm:
                continue
            if cur > limit:
                return
            yield cur
        w += rec.interval


def _monthly(start: datetime, months_step: int, frm: datetime, limit: datetime):
    elapsed = (frm.year - start.year) * 12 + (frm.month - start.month)
    k = max(0, elapsed // months_step - 1)
    while True:
        cur = add_months(start, k * months_step)
        if cur > limit:
            return
        if cur >= frm:
            yield cur
        k += 1


def next_occurrence(start: datetime, rec: Recurrence, after: datetime) -> datetime | None:
    """Prima occorrenza >= after (cerca fino a 50 anni avanti)."""
    horizon = after + timedelta(days=365 * 50)
    return next(occurrences(start, rec, after, horizon), None)
