import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from promemoria.core.settings import Settings  # noqa: E402
from promemoria.ui.category_picker import CategoryPicker, merge_categories  # noqa: E402
from promemoria.ui.event_dialog import EventDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_merge_categories_dedupes_ignoring_case_and_sorts():
    merged = merge_categories(("Personale", "Lavoro", "Casa"), ["cretin", "lavoro", "", "  Amici "])
    # a parità, vince il nome già usato nei promemoria (coincide con la barra laterale)
    assert merged == ["Amici", "Casa", "cretin", "lavoro", "Personale"]


def test_dropdown_lists_existing_categories_and_selects():
    picker = CategoryPicker(["Lavoro", "Casa"], "")
    assert picker.names() == ["Casa", "Lavoro"]
    assert picker.isEditable() and picker.currentText() == ""
    picker.setCurrentIndex(1)  # scelta dall'elenco
    assert picker.currentText() == "Lavoro"


def test_typing_new_or_existing_category():
    picker = CategoryPicker(["Casa", "Lavoro"], "Casa")
    assert picker.currentText() == "Casa"
    picker.lineEdit().setText("  lavoro ")
    assert picker.currentText() == "Lavoro"  # usa il nome già esistente
    picker.lineEdit().setText("Palestra")
    assert picker.currentText() == "Palestra"
    picker.lineEdit().clear()
    assert picker.currentText() == ""


def test_click_on_field_only_edits_text(monkeypatch):
    picker = CategoryPicker(["Casa"], "")
    picker.show()
    opened = []
    monkeypatch.setattr(picker, "showPopup", lambda: opened.append(True))
    QTest.mouseClick(picker.lineEdit(), Qt.MouseButton.LeftButton)
    assert opened == []  # l'elenco si apre solo dalla freccia ▾
    assert picker.lineEdit().hasFocus() or not picker.isActiveWindow()


def test_event_dialog_offers_existing_categories():
    d = EventDialog(Settings(), default_start=datetime(2026, 12, 1, 9, 0), default_title="Prova",
                    categories=["cretin", "Lavoro"])
    assert {"cretin", "Lavoro"} <= set(d.category.names())
    d.category.setCurrentIndex(d.category.findText("cretin"))
    d._on_accept()
    assert d.result_reminder.category == "cretin"
    d2 = EventDialog(Settings(), default_start=datetime(2026, 12, 1, 9, 0), default_title="X",
                     categories=["Lavoro"])
    d2.category.lineEdit().setText("LAVORO")
    d2._on_accept()
    assert d2.result_reminder.category == "Lavoro"
