"""Sincronizzazione dei promemoria verso Google Calendar (API REST v3).

Scelte:
- un calendario dedicato «Promemoria» (scope calendar.app.created: l'app vede solo
  il calendario che ha creato, mai gli altri calendari dell'utente);
- ogni promemoria = un evento con gli stessi preavvisi come notifiche Google, così
  il telefono avvisa anche a PC spento;
- la pianificazione (cosa creare/aggiornare/eliminare) è pura e testabile; la parte
  di rete gira in un thread di lavoro e non tocca il database.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

from .formatting import PRIORITIES
from .gauth import GAuthError
from .models import Recurrence, Reminder

API = "https://www.googleapis.com/calendar/v3"
CALENDAR_NAME = "Promemoria"
EVENT_MINUTES = 15
MAX_OVERRIDES = 5  # limite di Google per evento
MAX_MINUTES = 40320  # preavviso massimo accettato da Google (4 settimane)
SKIP_PAST_UNSYNCED = timedelta(days=1)
_BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

log = logging.getLogger(__name__)


OFFLINE_MESSAGE = "Google Calendar non raggiungibile (rete?): riprovo più tardi"


class GCalError(Exception):
    """Errore leggibile dall'utente."""


class Session(Protocol):
    def request(self, method: str, url: str, json: Any = None, timeout: float | None = None) -> Any: ...


# ---- conversione promemoria -> evento --------------------------------------------
def rrule(rec: Recurrence, start: datetime) -> str | None:
    if rec.freq == "none":
        return None
    parts = [f"FREQ={rec.freq.upper()}"]
    if rec.interval > 1:
        parts.append(f"INTERVAL={rec.interval}")
    if rec.freq == "weekly":
        days = sorted(set(rec.weekdays) or {start.weekday()})
        parts.append("BYDAY=" + ",".join(_BYDAY[d] for d in days))
    elif rec.freq == "monthly" and start.day > 28:
        # come l'app: il 31 diventa l'ultimo giorno dei mesi più corti
        parts.append("BYMONTHDAY=" + ",".join(str(d) for d in range(28, start.day + 1)))
        parts.append("BYSETPOS=-1")
    elif rec.freq == "yearly" and start.month == 2 and start.day == 29:
        parts += ["BYMONTH=2", "BYMONTHDAY=28,29", "BYSETPOS=-1"]
    if rec.until is not None:
        parts.append(f"UNTIL={rec.until:%Y%m%d}T235959Z")
    return ";".join(parts)


def _overrides(r: Reminder, email_reminders: bool) -> list[dict]:
    minutes = sorted({min(a, MAX_MINUTES) for a in r.alerts})
    overrides = [{"method": "popup", "minutes": m} for m in minutes][:MAX_OVERRIDES]
    if email_reminders and r.channels.email:
        if len(overrides) >= MAX_OVERRIDES:
            overrides.pop()
        overrides.append({"method": "email", "minutes": minutes[0]})
    return overrides


def _description(r: Reminder) -> str:
    lines = [r.notes.strip()] if r.notes.strip() else []
    if r.category:
        lines.append(f"Categoria: {r.category}")
    if r.priority != 1:
        lines.append(f"Priorità: {PRIORITIES[r.priority]}")
    lines.append("— creato dall'app Promemoria")
    return "\n".join(lines)


def build_event(r: Reminder, tz: str, email_reminders: bool) -> dict:
    end = r.start + timedelta(minutes=EVENT_MINUTES)
    event: dict[str, Any] = {
        "summary": r.title,
        "description": _description(r),
        "start": {"dateTime": r.start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
        "reminders": {"useDefault": False, "overrides": _overrides(r, email_reminders)},
        "transparency": "transparent",  # non segna "occupato" nel calendario
        "extendedProperties": {"private": {"promemoriaId": str(r.id)}},
    }
    if r.priority == 2:
        event["colorId"] = "11"  # rosso
    rule = rrule(r.recurrence, r.start)
    if rule:
        event["recurrence"] = [f"RRULE:{rule}"]
    return event


def event_hash(event: dict) -> str:
    return hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()


# ---- pianificazione -------------------------------------------------------------
@dataclass(frozen=True)
class Upsert:
    reminder_id: int
    event_id: str | None  # None = da creare
    event: dict
    hash: str


@dataclass(frozen=True)
class SyncPlan:
    upserts: tuple[Upsert, ...] = ()
    deletes: tuple[tuple[int, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.upserts and not self.deletes


def plan_sync(reminders: list[Reminder], mapping: dict[int, tuple[str, str]],
              now: datetime, tz: str, email_reminders: bool) -> SyncPlan:
    """Confronta promemoria locali ed eventi già creati (mapping id -> (evento, hash))."""
    upserts: list[Upsert] = []
    deletes: list[tuple[int, str]] = []
    seen: set[int] = set()
    for r in reminders:
        seen.add(r.id)
        mapped = mapping.get(r.id)
        if not r.is_recurring and r.completed:
            if mapped:
                deletes.append((r.id, mapped[0]))
            continue
        if not r.is_recurring and r.start < now - SKIP_PAST_UNSYNCED and not mapped:
            continue  # vecchio e mai sincronizzato: inutile crearlo ora
        event = build_event(r, tz, email_reminders)
        h = event_hash(event)
        if mapped and mapped[1] == h:
            continue
        upserts.append(Upsert(r.id, mapped[0] if mapped else None, event, h))
    for rid, (event_id, _h) in mapping.items():
        if rid not in seen:
            deletes.append((rid, event_id))
    return SyncPlan(tuple(upserts), tuple(deletes))


# ---- esecuzione (thread di lavoro) ------------------------------------------------
@dataclass
class SyncResult:
    saved: list[tuple[int, str, str]] = field(default_factory=list)  # (id, evento, hash)
    removed: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _AuthError(Exception):
    pass


def _check(resp: Any, ok: tuple[int, ...] = (200, 201, 204)) -> Any:
    if resp.status_code in (401, 403):
        raise _AuthError()
    return resp


def _events_url(calendar_id: str, event_id: str = "") -> str:
    url = f"{API}/calendars/{quote(calendar_id, safe='')}/events"
    return f"{url}/{quote(event_id, safe='')}" if event_id else url


def _create(session: Session, calendar_id: str, event: dict) -> str | None:
    resp = _check(session.request("POST", _events_url(calendar_id), json=event, timeout=20))
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    log.warning("Creazione evento fallita: HTTP %s", resp.status_code)
    return None


def apply_plan(session: Session, calendar_id: str, plan: SyncPlan) -> SyncResult:
    result = SyncResult()
    try:
        for up in plan.upserts:
            event_id = None
            if up.event_id:
                resp = _check(session.request("PUT", _events_url(calendar_id, up.event_id),
                                              json=up.event, timeout=20))
                if resp.status_code in (200, 201):
                    event_id = up.event_id
                elif resp.status_code not in (404, 410):
                    log.warning("Aggiornamento evento fallito: HTTP %s", resp.status_code)
                    result.errors.append(f"Google Calendar: errore {resp.status_code} su «{up.event['summary']}»")
                    continue
            if event_id is None:  # nuovo, oppure cancellato da Google: lo ricreiamo
                event_id = _create(session, calendar_id, up.event)
            if event_id:
                result.saved.append((up.reminder_id, event_id, up.hash))
            else:
                result.errors.append(f"Google Calendar: impossibile creare «{up.event['summary']}»")
        for rid, event_id in plan.deletes:
            resp = _check(session.request("DELETE", _events_url(calendar_id, event_id), timeout=20))
            if resp.status_code in (200, 204, 404, 410):
                result.removed.append(rid)
            else:
                result.errors.append(f"Google Calendar: eliminazione non riuscita ({resp.status_code})")
    except _AuthError:
        result.errors.append("Google Calendar: accesso scaduto o revocato, ricollega l'account nelle Impostazioni")
    except GAuthError as exc:  # scaduto a metà: gli eventi già salvati restano registrati
        result.errors.append(str(exc))
    except OSError:  # include gli errori di rete di requests
        result.errors.append(OFFLINE_MESSAGE)
    return result


def ensure_calendar(session: Session, calendar_id: str, tz: str) -> str:
    """Restituisce l'id del calendario «Promemoria», creandolo se manca."""
    try:
        return _ensure_calendar(session, calendar_id, tz)
    except _AuthError:
        raise GCalError("Google ha rifiutato l'accesso: ricollega l'account") from None
    except OSError as exc:
        raise GCalError(OFFLINE_MESSAGE) from exc


def _ensure_calendar(session: Session, calendar_id: str, tz: str) -> str:
    if calendar_id:
        resp = _check(session.request("GET", f"{API}/calendars/{quote(calendar_id, safe='')}",
                                      timeout=20))
        if resp.status_code == 200:
            return calendar_id
        if resp.status_code not in (404, 410):
            raise GCalError(f"Google Calendar: errore {resp.status_code}")
    body = {"summary": CALENDAR_NAME, "timeZone": tz,
            "description": "Promemoria sincronizzati dall'app Promemoria per Windows"}
    resp = _check(session.request("POST", f"{API}/calendars", json=body, timeout=20))
    if resp.status_code not in (200, 201):
        raise GCalError(f"Impossibile creare il calendario (errore {resp.status_code})")
    return resp.json()["id"]
