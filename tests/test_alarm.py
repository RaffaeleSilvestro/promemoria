import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from promemoria.core import engine, fullscreen  # noqa: E402
from promemoria.core.db import Repository  # noqa: E402
from promemoria.core.models import Channels, Due, Reminder  # noqa: E402
from promemoria.core.settings import Settings  # noqa: E402
from promemoria.ui import alerts, common  # noqa: E402
from promemoria.ui.popup import ReminderPopup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def rings(monkeypatch):
    calls = []

    class FakeWinsound:
        SND_ALIAS = SND_ASYNC = SND_PURGE = 0

        @staticmethod
        def PlaySound(name, flags):  # noqa: N802
            calls.append(name)

    monkeypatch.setattr(common, "winsound", FakeWinsound)
    return calls


def test_alarm_rings_three_times_then_stops_by_itself(rings):
    alarm = common.AlarmSound()
    alarm.start()
    alarm.start()  # due promemoria insieme: nessuno squillo in più
    QTest.qWait(4600)
    assert [r for r in rings if r] == ["SystemExclamation"] * 3
    assert rings[-1] is None  # a 3 secondi il suono viene comunque interrotto


def test_alarm_can_be_stopped_early_and_restarted(rings):
    alarm = common.AlarmSound()
    alarm.start()
    alarm.stop()
    QTest.qWait(1300)
    assert [r for r in rings if r] == ["SystemExclamation"]
    alarm.start()
    assert len([r for r in rings if r]) == 2
    alarm.stop()


def make(repo):
    r = repo.add(Reminder("Pillola", datetime(2026, 11, 24, 23, 40), alerts=(10,),
                          channels=Channels(True, True)))
    return Due(r, r.start, 10)


def test_popup_never_takes_focus():
    repo = Repository()
    popup = ReminderPopup(make(repo), 10, True)
    assert popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert popup.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    popup.close()
    repo.close()


@pytest.fixture()
def env(rings):
    repo = Repository()
    state = {"full": False}
    a = alerts.AlertPresenter(repo, Settings, common.AlarmSound(), lambda: state["full"])
    yield a, repo, state, rings
    a.shutdown()
    for p in list(a.popups):
        p.close()
    repo.close()


def test_normal_desktop_shows_popup_at_once(env):
    a, repo, _, rings = env
    a.present(make(repo), sound=True)
    assert len(a.popups) == 1 and len(rings) == 1


def test_fullscreen_rings_but_waits_to_show_popup(env):
    a, repo, state, rings = env
    state["full"] = True
    a.present(make(repo), sound=True)
    a.flush()
    assert a.popups == [] and len(a.waiting) == 1 and len(rings) == 1
    state["full"] = False
    a.flush()
    assert len(a.popups) == 1 and a.waiting == [] and len(rings) == 1  # non risuona


def test_waiting_popup_dropped_if_done_or_deleted(env):
    a, repo, state, _ = env
    state["full"] = True
    d1, d2 = make(repo), make(repo)
    a.present(d1, sound=False)
    a.present(d2, sound=False)
    repo.set_completed(d1.reminder.id, True)
    repo.delete(d2.reminder.id)
    state["full"] = False
    a.flush()
    assert a.popups == [] and a.waiting == []


def test_waiting_popup_survives_quit(env):
    a, repo, state, _ = env
    state["full"] = True
    a.present(make(repo), sound=False)
    a.shutdown()
    again = engine.due_notifications(repo, datetime.now() + timedelta(minutes=1))
    assert [d.reminder.title for d in again if d.snoozed] == ["Pillola"]


@pytest.mark.parametrize("state, expected", [
    (None, False), (1, False), (2, True), (3, True), (4, True), (5, False), (6, False)])
def test_fullscreen_states(monkeypatch, state, expected):
    monkeypatch.setattr(fullscreen, "_notification_state", lambda: state)
    assert fullscreen.is_fullscreen_app_active() is expected
