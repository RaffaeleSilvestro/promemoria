import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


def test_chip_click_selects_category():
    picker = CategoryPicker(["Casa", "Lavoro"], "")
    assert picker.chip_names() == ["Nessuna", "Casa", "Lavoro"]
    picker.chip("Lavoro").click()
    assert picker.currentText() == "Lavoro"
    assert picker.chip("Lavoro").isChecked() and not picker.chip("Casa").isChecked()
    picker.chip("Nessuna").click()
    assert picker.currentText() == "" and picker.chip("Nessuna").isChecked()


def test_typing_new_or_existing_category():
    picker = CategoryPicker(["Casa", "Lavoro"], "Casa")
    assert picker.chip("Casa").isChecked()
    picker.edit.setText("  lavoro ")
    assert picker.chip("Lavoro").isChecked()          # riconosciuta anche in minuscolo
    assert picker.currentText() == "Lavoro"            # usa il nome già esistente
    picker.edit.setText("Palestra")
    assert picker.currentText() == "Palestra"
    assert not any(picker.chip(n).isChecked() for n in picker.chip_names())


def test_event_dialog_offers_existing_categories():
    d = EventDialog(Settings(), default_start=datetime(2026, 12, 1, 9, 0), default_title="Prova",
                    categories=["cretin", "Lavoro"])
    assert {"cretin", "Lavoro"} <= set(d.category.chip_names())
    d.category.chip("cretin").click()
    d._on_accept()
    assert d.result_reminder.category == "cretin"
    d2 = EventDialog(Settings(), default_start=datetime(2026, 12, 1, 9, 0), default_title="X",
                     categories=["Lavoro"])
    d2.category.edit.setText("LAVORO")
    d2._on_accept()
    assert d2.result_reminder.category == "Lavoro"
