from datetime import datetime

import pytest

from promemoria.core import engine, secrets
from promemoria.core.db import Repository
from promemoria.core.models import Channels, Recurrence, Reminder
from promemoria.core.recurrence import add_months, occurrences
from promemoria.core.settings import Settings, SettingsStore

D = datetime


def occ(start, rec, frm, to):
    return list(occurrences(start, rec, frm, to))


def test_single_occurrence():
    s = D(2026, 11, 20, 9, 0)
    assert occ(s, Recurrence(), D(2026, 11, 1), D(2026, 12, 1)) == [s]
    assert occ(s, Recurrence(), D(2026, 11, 21), D(2026, 12, 1)) == []


def test_daily_interval_and_until():
    s = D(2026, 11, 1, 8, 0)
    rec = Recurrence("daily", 2, until=D(2026, 11, 9))
    got = occ(s, rec, D(2026, 11, 4), D(2026, 12, 31))
    assert got == [D(2026, 11, 5, 8), D(2026, 11, 7, 8), D(2026, 11, 9, 8)]


def test_weekly_multiple_weekdays():
    s = D(2026, 11, 2, 18, 30)  # lunedì
    rec = Recurrence("weekly", 1, weekdays=(0, 2))
    got = occ(s, rec, D(2026, 11, 9), D(2026, 11, 15, 23, 59))
    assert got == [D(2026, 11, 9, 18, 30), D(2026, 11, 11, 18, 30)]


def test_weekly_biweekly_skips_odd_weeks():
    s = D(2026, 11, 2, 7, 0)
    rec = Recurrence("weekly", 2, weekdays=(0,))
    got = occ(s, rec, D(2026, 11, 1), D(2026, 12, 1))
    assert got == [D(2026, 11, 2, 7), D(2026, 11, 16, 7), D(2026, 11, 30, 7)]


def test_weekly_never_before_start():
    s = D(2026, 11, 4, 9, 0)  # mercoledì
    rec = Recurrence("weekly", 1, weekdays=(0, 2))
    assert occ(s, rec, D(2026, 11, 1), D(2026, 11, 8))[0] == s


def test_monthly_clamps_end_of_month():
    s = D(2026, 1, 31, 10, 0)
    got = occ(s, Recurrence("monthly"), D(2026, 1, 1), D(2026, 4, 30, 23, 59))
    assert [g.date().isoformat() for g in got] == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_yearly_leap_day():
    s = D(2024, 2, 29, 12, 0)
    got = occ(s, Recurrence("yearly"), D(2025, 1, 1), D(2028, 12, 31))
    assert [g.date().isoformat() for g in got] == ["2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]


def test_add_months_year_rollover():
    assert add_months(D(2026, 11, 15), 3) == D(2027, 2, 15)


def test_invalid_reminder_rejected():
    with pytest.raises(ValueError):
        Reminder(title="  ", start=D(2026, 1, 1))
    with pytest.raises(ValueError):
        Recurrence("daily", 0)


@pytest.fixture()
def repo():
    r = Repository()
    yield r
    r.close()


def test_crud_roundtrip(repo):
    r = Reminder("Dentista", D(2026, 11, 20, 15, 0), notes="porta tessera", priority=2,
                 category="Salute", recurrence=Recurrence("weekly", 2, (1, 3), D(2027, 1, 1)),
                 alerts=(0, 60, 1440), channels=Channels(True, True, True, False))
    saved = repo.add(r)
    loaded = repo.get(saved.id)
    assert loaded.recurrence == r.recurrence and loaded.alerts == (0, 60, 1440)
    assert loaded.channels == r.channels and loaded.title == "Dentista"
    repo.update(Reminder("Dentista 2", r.start, id=saved.id))
    assert repo.get(saved.id).title == "Dentista 2"
    repo.delete(saved.id)
    assert repo.list() == []


def test_fires_once_with_preavviso(repo):
    created = D(2026, 11, 13, 8, 0)
    repo.add(Reminder("Riunione", D(2026, 11, 13, 10, 0), alerts=(0, 30)), now=created)
    assert engine.due_notifications(repo, D(2026, 11, 13, 9, 0)) == []
    d1 = engine.due_notifications(repo, D(2026, 11, 13, 9, 30))
    assert [d.offset_min for d in d1] == [30] and not d1[0].missed
    assert engine.due_notifications(repo, D(2026, 11, 13, 9, 31)) == []
    d2 = engine.due_notifications(repo, D(2026, 11, 13, 10, 0))
    assert [d.offset_min for d in d2] == [0]
    assert engine.due_notifications(repo, D(2026, 11, 13, 10, 1)) == []


def test_missed_while_off_is_flagged(repo):
    repo.add(Reminder("Pillola", D(2026, 11, 13, 7, 0)), now=D(2026, 11, 12, 20, 0))
    due = engine.due_notifications(repo, D(2026, 11, 13, 9, 0))
    assert len(due) == 1 and due[0].missed


def test_no_retroactive_fire_for_new_reminder(repo):
    repo.add(Reminder("Passato", D(2026, 11, 13, 7, 0)), now=D(2026, 11, 13, 9, 0))
    assert engine.due_notifications(repo, D(2026, 11, 13, 9, 1)) == []


def test_recurring_done_skips_only_that_occurrence(repo):
    repo.add(Reminder("Vitamine", D(2026, 11, 10, 8, 0), recurrence=Recurrence("daily")),
                 now=D(2026, 11, 10, 23, 0))
    items = engine.agenda(repo, D(2026, 11, 11), D(2026, 11, 12, 23, 59))
    engine.mark_done(repo, items[0])
    assert engine.due_notifications(repo, D(2026, 11, 11, 8, 0)) == []
    assert len(engine.due_notifications(repo, D(2026, 11, 12, 8, 0))) == 1


def test_snooze_refires(repo):
    repo.add(Reminder("Chiama", D(2026, 11, 13, 10, 0)), now=D(2026, 11, 13, 9, 0))
    due = engine.due_notifications(repo, D(2026, 11, 13, 10, 0))[0]
    engine.snooze(repo, due, 10, D(2026, 11, 13, 10, 0))
    assert engine.due_notifications(repo, D(2026, 11, 13, 10, 5)) == []
    again = engine.due_notifications(repo, D(2026, 11, 13, 10, 10))
    assert len(again) == 1 and again[0].snoozed


def test_completed_single_does_not_fire_and_overdue(repo):
    r = repo.add(Reminder("X", D(2026, 11, 13, 10, 0)), now=D(2026, 11, 13, 9, 0))
    assert len(engine.overdue(repo, D(2026, 11, 14))) == 1
    repo.set_completed(r.id, True)
    assert engine.overdue(repo, D(2026, 11, 14)) == []
    assert engine.due_notifications(repo, D(2026, 11, 13, 10, 0)) == []


def test_edit_start_rearms(repo):
    r = repo.add(Reminder("Y", D(2026, 11, 13, 10, 0)), now=D(2026, 11, 13, 9, 0))
    engine.due_notifications(repo, D(2026, 11, 13, 10, 0))
    repo.update(Reminder("Y", D(2026, 11, 13, 12, 0), id=r.id), now=D(2026, 11, 13, 10, 5))
    assert len(engine.due_notifications(repo, D(2026, 11, 13, 12, 0))) == 1


def test_secret_roundtrip():
    token = secrets.protect("p@ss wörd")
    assert "p@ss" not in token and secrets.unprotect(token) == "p@ss wörd"
    assert secrets.protect("") == "" and secrets.unprotect("") == ""


def test_settings_store_encrypts(tmp_path):
    store = SettingsStore(tmp_path)
    store.save(Settings(smtp_user="a@b.it", smtp_password="segreto", tg_token="123:ABC"))
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "segreto" not in raw and "123:ABC" not in raw
    loaded = store.load()
    assert loaded.smtp_password == "segreto" and loaded.tg_token == "123:ABC"
    assert SettingsStore(tmp_path / "nuova").load() == Settings()


def test_gcal_map_survives_reminder_delete(repo):
    r = repo.add(Reminder("Z", D(2026, 11, 20, 9, 0)))
    repo.set_gcal(r.id, "ev1", "h1")
    repo.set_gcal(r.id, "ev1", "h2")
    assert repo.gcal_map() == {r.id: ("ev1", "h2")}
    repo.delete(r.id)
    assert repo.gcal_map() == {r.id: ("ev1", "h2")}  # serve per cancellare l'evento
    repo.delete_gcal(r.id)
    assert repo.gcal_map() == {}
    repo.set_gcal(5, "e", "h")
    repo.clear_gcal()
    assert repo.gcal_map() == {}


def test_gcal_credentials_encrypted(tmp_path):
    store = SettingsStore(tmp_path)
    store.save(Settings(gcal_credentials='{"refresh_token": "RT-SEGRETO"}', gcal_enabled=True,
                        gcal_calendar_id="cal"))
    assert "RT-SEGRETO" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    loaded = store.load()
    assert loaded.gcal_ready and "RT-SEGRETO" in loaded.gcal_credentials


def test_category_ids_and_set_category(repo):
    a = repo.add(Reminder("A", D(2026, 11, 20, 9, 0), category="cretin"))
    b = repo.add(Reminder("B", D(2026, 11, 21, 9, 0), category="cretin"))
    c = repo.add(Reminder("C", D(2026, 11, 22, 9, 0), category="Lavoro"))
    armed_before = repo.get(a.id).armed_from
    ids = repo.ids_in_category("cretin")
    assert sorted(ids) == sorted([a.id, b.id])
    assert repo.set_category(ids, "") == 2
    assert {r.title: r.category for r in repo.list()} == {"A": "", "B": "", "C": "Lavoro"}
    # cambiare categoria non deve far riscattare gli avvisi
    assert repo.get(a.id).armed_from == armed_before
    assert repo.set_category([a.id], "  Amici ") == 1
    assert repo.get(a.id).category == "Amici"
    assert repo.set_category([], "X") == 0
    assert repo.ids_in_category("non esiste") == []
    assert c.id not in repo.ids_in_category("cretin")
