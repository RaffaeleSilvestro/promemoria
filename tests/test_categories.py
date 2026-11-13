import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from promemoria.app import rename_category_list  # noqa: E402
from promemoria.core.db import Repository  # noqa: E402
from promemoria.core.models import Reminder  # noqa: E402
from promemoria.core.settings import Settings  # noqa: E402
from promemoria.ui import main_window  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win():
    repo = Repository()
    start = datetime.now() + timedelta(days=1)
    repo.add(Reminder("ale è cretina", start, category="cretin"))
    repo.add(Reminder("Altro", start, category="cretin"))
    repo.add(Reminder("Lavoro", start, category="Lavoro"))
    w = main_window.MainWindow(repo, lambda: Settings())
    events: list[tuple[str, str]] = []
    w.categories_renamed.connect(lambda old, new: events.append((old, new)))
    yield w, repo, events
    w.quitting = True
    w.close()
    repo.close()


def cats(repo):
    return {r.title: r.category for r in repo.list()}


def sidebar_categories(w):
    return sorted(k[4:] for k in w.sidebar._buttons if k.startswith("cat:"))


def test_delete_category_keeps_reminders_and_undo(win):
    w, repo, events = win
    w.set_view("cat:cretin")
    w.delete_category("cretin")
    assert cats(repo) == {"ale è cretina": "", "Altro": "", "Lavoro": "Lavoro"}
    assert sidebar_categories(w) == ["Lavoro"]
    assert w.view == "today" and events == [("cretin", "")]
    w.toast._on_action()  # «Annulla»
    assert cats(repo)["ale è cretina"] == "cretin"
    assert sidebar_categories(w) == ["Lavoro", "cretin"]
    assert events[-1] == ("", "cretin")


def test_rename_category_follows_view_and_undo(win, monkeypatch):
    w, repo, events = win
    monkeypatch.setattr(main_window.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Amici", True)))
    w.set_view("cat:cretin")
    w.rename_category("cretin")
    assert cats(repo)["Altro"] == "Amici" and w.view == "cat:Amici"
    assert sidebar_categories(w) == ["Amici", "Lavoro"]
    assert events == [("cretin", "Amici")]
    w.toast._on_action()
    assert cats(repo)["Altro"] == "cretin" and w.view == "cat:cretin"


def test_rename_cancelled_or_same_name_does_nothing(win, monkeypatch):
    w, repo, events = win
    for answer in (("", True), ("cretin", True), ("Nuovo", False)):
        monkeypatch.setattr(main_window.QInputDialog, "getText",
                            staticmethod(lambda *a, ans=answer, **k: ans))
        w.rename_category("cretin")
    assert cats(repo)["Altro"] == "cretin" and events == []


def test_sidebar_menu_offers_rename_and_delete(win):
    w, _, _ = win
    labels = [label for label, _ in w.sidebar.category_menu_actions("cretin")]
    assert any("Rinomina" in label for label in labels)
    assert any("Elimina" in label for label in labels)


@pytest.mark.parametrize("start, old, new, expected", [
    (("Casa", "Lavoro"), "Casa", "Famiglia", ("Famiglia", "Lavoro")),
    (("Casa", "Lavoro"), "Casa", "Lavoro", ("Lavoro",)),       # unisce con una esistente
    (("Casa", "Lavoro"), "Casa", "", ("Lavoro",)),             # eliminata
    (("Casa",), "cretin", "", ("Casa",)),                      # non era suggerita
    (("Casa",), "", "cretin", ("Casa",)),                      # annulla di una mai suggerita
])
def test_rename_category_list(start, old, new, expected):
    assert rename_category_list(start, old, new, set()) == expected


def test_rename_category_list_undo_restores_removed():
    removed: set[str] = set()
    after_delete = rename_category_list(("Casa", "Lavoro"), "Casa", "", removed)
    assert after_delete == ("Lavoro",) and removed == {"Casa"}
    assert rename_category_list(after_delete, "", "Casa", removed) == ("Lavoro", "Casa")
    assert removed == set()
