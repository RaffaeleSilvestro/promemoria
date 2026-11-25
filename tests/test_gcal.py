from datetime import datetime

import pytest

from promemoria.core import gcal
from promemoria.core.gauth import GAuthError
from promemoria.core.models import Channels, Recurrence, Reminder

TZ = "Europe/Rome"
NOW = datetime(2026, 11, 13, 10, 0)


def rem(rid: int = 1, **kw) -> Reminder:
    base = dict(title="Dentista", start=datetime(2026, 11, 20, 15, 30), id=rid)
    base.update(kw)
    return Reminder(**base)


# ---- RRULE -------------------------------------------------------------------
@pytest.mark.parametrize("rec, start, expected", [
    (Recurrence(), datetime(2026, 11, 20, 9), None),
    (Recurrence("daily"), datetime(2026, 11, 20, 9), "FREQ=DAILY"),
    (Recurrence("daily", 3), datetime(2026, 11, 20, 9), "FREQ=DAILY;INTERVAL=3"),
    (Recurrence("weekly", 1, (2, 0)), datetime(2026, 11, 16, 9), "FREQ=WEEKLY;BYDAY=MO,WE"),
    (Recurrence("weekly"), datetime(2026, 11, 20, 9), "FREQ=WEEKLY;BYDAY=FR"),
    (Recurrence("monthly"), datetime(2026, 11, 15, 9), "FREQ=MONTHLY"),
    (Recurrence("monthly"), datetime(2026, 1, 31, 9),
     "FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1"),
    (Recurrence("yearly"), datetime(2024, 2, 29, 9),
     "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1"),
    (Recurrence("daily", until=datetime(2026, 12, 31)), datetime(2026, 11, 20, 9),
     "FREQ=DAILY;UNTIL=20261231T235959Z"),
])
def test_rrule(rec, start, expected):
    assert gcal.rrule(rec, start) == expected


# ---- evento ------------------------------------------------------------------
def test_build_event_basic_fields():
    r = rem(notes="Portare tessera", category="Salute", priority=2, alerts=(1440, 0, 30))
    ev = gcal.build_event(r, TZ, email_reminders=False)
    assert ev["summary"] == "Dentista"
    assert ev["start"] == {"dateTime": "2026-11-20T15:30:00", "timeZone": TZ}
    assert ev["end"] == {"dateTime": "2026-11-20T15:45:00", "timeZone": TZ}
    assert ev["reminders"] == {"useDefault": False, "overrides": [
        {"method": "popup", "minutes": 0}, {"method": "popup", "minutes": 30},
        {"method": "popup", "minutes": 1440}]}
    assert "Portare tessera" in ev["description"] and "Salute" in ev["description"]
    assert ev["transparency"] == "transparent" and ev["colorId"] == "11"
    assert ev["extendedProperties"]["private"]["promemoriaId"] == "1"
    assert "recurrence" not in ev


def test_build_event_recurring_and_email():
    r = rem(recurrence=Recurrence("weekly", 1, (4,)), alerts=(10,),
            channels=Channels(popup=True, email=True))
    ev = gcal.build_event(r, TZ, email_reminders=True)
    assert ev["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=FR"]
    assert {"method": "email", "minutes": 10} in ev["reminders"]["overrides"]
    no_email = gcal.build_event(r, TZ, email_reminders=False)
    assert all(o["method"] == "popup" for o in no_email["reminders"]["overrides"])


def test_build_event_respects_google_limits():
    r = rem(alerts=(0, 5, 10, 30, 60, 180, 1440, 99999))
    overrides = gcal.build_event(r, TZ, False)["reminders"]["overrides"]
    assert len(overrides) == 5
    assert max(o["minutes"] for o in overrides) <= gcal.MAX_MINUTES


# ---- pianificazione ------------------------------------------------------------
def test_plan_creates_updates_and_deletes():
    new = rem(1)
    unchanged = rem(2, title="Palestra")
    changed = rem(3, title="Chiamare")
    done_single = rem(4, completed=True)
    old_unsynced = rem(5, start=datetime(2026, 10, 1, 9))
    mapping = {
        2: ("ev2", gcal.event_hash(gcal.build_event(unchanged, TZ, False))),
        3: ("ev3", "vecchio-hash"),
        4: ("ev4", "h"),
        99: ("ev99", "h"),  # promemoria eliminato in locale
    }
    plan = gcal.plan_sync([new, unchanged, changed, done_single, old_unsynced],
                          mapping, NOW, TZ, False)
    assert [(u.reminder_id, u.event_id) for u in plan.upserts] == [(1, None), (3, "ev3")]
    assert sorted(plan.deletes) == [(4, "ev4"), (99, "ev99")]
    assert not plan.is_empty


def test_plan_empty_when_in_sync():
    r = rem(1)
    mapping = {1: ("ev1", gcal.event_hash(gcal.build_event(r, TZ, False)))}
    assert gcal.plan_sync([r], mapping, NOW, TZ, False).is_empty


# ---- esecuzione con sessione finta ---------------------------------------------
class FakeResp:
    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: dict | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.responses = responses or {}
        self.counter = 0

    def request(self, method, url, json=None, timeout=None):
        self.calls.append((method, url))
        for (m, fragment), resp in self.responses.items():
            if m == method and fragment in url:
                return resp
        if method == "POST":
            self.counter += 1
            return FakeResp(200, {"id": f"new{self.counter}"})
        if method == "DELETE":
            return FakeResp(204)
        return FakeResp(200, {"id": url.rsplit("/", 1)[-1]})


def test_apply_plan_create_update_delete():
    plan = gcal.plan_sync([rem(1), rem(3, title="X")],
                          {3: ("ev3", "old"), 9: ("ev9", "h")}, NOW, TZ, False)
    session = FakeSession()
    result = gcal.apply_plan(session, "cal@group", plan)
    assert [(s[0], s[1]) for s in result.saved] == [(1, "new1"), (3, "ev3")]
    assert result.removed == [9] and result.errors == []
    assert ("DELETE", f"{gcal.API}/calendars/cal%40group/events/ev9") in session.calls


def test_apply_plan_recreates_missing_event_and_tolerates_gone_delete():
    plan = gcal.plan_sync([rem(3, title="X")], {3: ("ev3", "old"), 9: ("ev9", "h")},
                          NOW, TZ, False)
    session = FakeSession({("PUT", "/events/ev3"): FakeResp(404),
                           ("DELETE", "/events/ev9"): FakeResp(410)})
    result = gcal.apply_plan(session, "cal", plan)
    assert result.saved[0][1] == "new1" and result.removed == [9] and not result.errors


def test_apply_plan_reports_auth_error_without_crashing():
    plan = gcal.plan_sync([rem(1)], {}, NOW, TZ, False)
    session = FakeSession({("POST", "/events"): FakeResp(401)})
    result = gcal.apply_plan(session, "cal", plan)
    assert result.saved == [] and "ricollega" in result.errors[0].lower()


def test_apply_plan_network_error(monkeypatch):
    class Broken(FakeSession):
        def request(self, *a, **k):
            raise OSError("rete giù")

    result = gcal.apply_plan(Broken(), "cal", gcal.plan_sync([rem(1)], {}, NOW, TZ, False))
    assert result.saved == [] and "rete" in result.errors[0].lower()


def test_ensure_calendar_reuses_or_creates():
    ok = FakeSession({("GET", "/calendars/cal1"): FakeResp(200, {"id": "cal1"})})
    assert gcal.ensure_calendar(ok, "cal1", TZ) == "cal1"
    missing = FakeSession({("GET", "/calendars/old"): FakeResp(404),
                           ("POST", "/calendars"): FakeResp(200, {"id": "nuovo"})})
    assert gcal.ensure_calendar(missing, "old", TZ) == "nuovo"
    assert gcal.ensure_calendar(missing, "", TZ) == "nuovo"


def test_expired_access_midway_keeps_saved_events():
    class ExpiresAfterFirst(FakeSession):
        def request(self, *args, **kwargs):
            if self.calls:
                raise GAuthError("Accesso a Google scaduto")
            return super().request(*args, **kwargs)

    plan = gcal.plan_sync([rem(1), rem(2)], {}, NOW, TZ, False)
    result = gcal.apply_plan(ExpiresAfterFirst(), "cal", plan)
    assert [s[0] for s in result.saved] == [1]  # non verra' creato due volte
    assert result.errors == ["Accesso a Google scaduto"]


def test_ensure_calendar_network_error_is_readable():
    class Offline(FakeSession):
        def request(self, *args, **kwargs):
            raise ConnectionError("giu")

    with pytest.raises(gcal.GCalError, match="non raggiungibile"):
        gcal.ensure_calendar(Offline(), "cal", TZ)
