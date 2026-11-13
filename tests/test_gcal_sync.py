import os
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from promemoria.core import gcal  # noqa: E402
from promemoria.core.db import Repository  # noqa: E402
from promemoria.core.models import Reminder  # noqa: E402
from promemoria.core.settings import Settings  # noqa: E402
from promemoria.ui import gcal_sync  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGoogle:
    def __init__(self, calendar_id: str = "cal") -> None:
        self.calendar_id = calendar_id
        self.events: dict[str, dict] = {}
        self.fail_with: str = ""
        self._n = 0

    def ensure(self, session, calendar_id, tz):
        return self.calendar_id

    def apply(self, session, calendar_id, plan):
        result = gcal.SyncResult()
        if self.fail_with:
            result.errors.append(self.fail_with)
            return result
        for up in plan.upserts:
            event_id = up.event_id
            if event_id is None:
                self._n += 1
                event_id = f"ev{self._n}"
            self.events[event_id] = up.event
            result.saved.append((up.reminder_id, event_id, up.hash))
        for rid, event_id in plan.deletes:
            self.events.pop(event_id, None)
            result.removed.append(rid)
        return result


@pytest.fixture()
def env(monkeypatch):
    google = FakeGoogle()
    monkeypatch.setattr(gcal_sync, "run_in_thread", lambda fn, done: done(fn(), ""))
    monkeypatch.setattr(gcal_sync.gauth, "session", lambda creds: object())
    monkeypatch.setattr(gcal_sync.gcal, "ensure_calendar", google.ensure)
    monkeypatch.setattr(gcal_sync.gcal, "apply_plan", google.apply)
    repo = Repository()
    state = {"settings": Settings(gcal_enabled=True, gcal_credentials="{}", gcal_calendar_id="cal")}
    errors: list[str] = []

    def save(s):
        state["settings"] = s

    sync = gcal_sync.GCalSync(repo, lambda: state["settings"], save, errors.append)
    yield google, repo, sync, state, errors
    repo.close()


def future(hours: int = 2) -> datetime:
    return (datetime.now() + timedelta(hours=hours)).replace(second=0, microsecond=0)


def test_create_update_delete_cycle(env):
    google, repo, sync, _, _ = env
    r = repo.add(Reminder("Dentista", future()))
    sync.sync_now()
    assert [e["summary"] for e in google.events.values()] == ["Dentista"]
    repo.update(replace(r, title="Dentista (spostato)"))
    sync.sync_now()
    assert [e["summary"] for e in google.events.values()] == ["Dentista (spostato)"]
    repo.delete(r.id)
    sync.sync_now()
    assert google.events == {} and repo.gcal_map() == {}


def test_disabled_does_nothing(env):
    google, repo, sync, state, _ = env
    state["settings"] = replace(state["settings"], gcal_enabled=False)
    repo.add(Reminder("X", future()))
    sync.sync_now()
    assert google.events == {}


def test_recreated_calendar_resets_mapping_and_saves_id(env):
    google, repo, sync, state, _ = env
    repo.add(Reminder("X", future()))
    sync.sync_now()
    google.calendar_id = "cal-nuovo"
    google.events.clear()
    sync.sync_now()  # rileva il nuovo calendario
    assert state["settings"].gcal_calendar_id == "cal-nuovo" and repo.gcal_map() == {}
    sync.sync_now()
    assert len(google.events) == 1


def test_errors_are_rate_limited(env):
    google, repo, sync, _, errors = env
    google.fail_with = "Google Calendar non raggiungibile (rete?)"
    repo.add(Reminder("X", future()))
    sync.sync_now()
    sync.sync_now()
    assert errors == ["Google Calendar non raggiungibile (rete?)"]
    assert repo.gcal_map() == {}  # riproverà al prossimo giro
    google.fail_with = ""
    sync.sync_now()
    assert len(repo.gcal_map()) == 1
