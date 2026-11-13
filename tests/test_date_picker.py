import os
from datetime import date, datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QDateTime, QTime  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from promemoria.core.settings import Settings  # noqa: E402
from promemoria.ui.date_picker import DatePicker, DateTimePicker  # noqa: E402
from promemoria.ui.event_dialog import EventDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_click_opens_calendar_and_pick_updates_date():
    picker = DatePicker(QDate(2026, 11, 13))
    assert "venerdì 13 novembre 2026" in picker.text()
    picker.click()
    popup = picker._popup
    assert popup is not None and popup.isVisible()
    assert popup.calendar.selectedDate() == QDate(2026, 11, 13)
    changes = []
    picker.dateChanged.connect(changes.append)
    popup.calendar.clicked.emit(QDate(2026, 11, 25))
    assert picker.date() == QDate(2026, 11, 25) and changes == [QDate(2026, 11, 25)]
    assert not popup.isVisible()
    assert "mercoledì 25 novembre 2026" in picker.text()


def test_short_format_and_today_button():
    picker = DatePicker(QDate(2027, 1, 5), short=True)
    assert "05/01/2027" in picker.text()
    picker.open_calendar()
    picker._popup._pick(QDate.currentDate())
    assert picker.date() == QDate.currentDate()


def test_datetime_picker_roundtrip():
    dt = DateTimePicker(QDateTime(QDate(2026, 12, 1), QTime(18, 45)))
    assert dt.dateTime().toPython() == datetime(2026, 12, 1, 18, 45)
    dt.setDateTime(QDateTime(QDate(2027, 2, 3), QTime(7, 5, 59)))
    assert dt.dateTime().toPython() == datetime(2027, 2, 3, 7, 5)


def test_event_dialog_uses_pickers_and_chips():
    d = EventDialog(Settings(), default_start=datetime(2026, 11, 13, 17, 0), default_title="Prova")
    d._shift_day(1)
    d._set_hour(9)
    expected = datetime.combine(date.today() + timedelta(days=1), datetime.min.time()).replace(hour=9)
    assert d.when.dateTime().toPython() == expected
    d.when.date_field.setDate(QDate(2026, 12, 24))
    d._on_accept()
    assert d.result_reminder.start == datetime(2026, 12, 24, 9, 0)
