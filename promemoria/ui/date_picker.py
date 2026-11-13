"""Selettori di data/ora: un clic sul campo apre un calendario a tendina."""
from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, QPoint, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QPushButton, QTimeEdit, QVBoxLayout, QWidget,
)

from ..core.formatting import DAYS, MONTHS
from .calendar_page import DotCalendar


def _long_label(d: QDate) -> str:
    py = d.toPython()
    return f"{DAYS[py.weekday()]} {py.day} {MONTHS[py.month - 1]} {py.year}"


class _CalendarPopup(QFrame):
    picked = Signal(QDate)

    def __init__(self, parent: QWidget, selected: QDate) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("CalendarCard")
        self.calendar = DotCalendar()
        self.calendar.setMinimumSize(320, 290)
        self.calendar.apply_palette()
        self.calendar.setSelectedDate(selected)
        self.calendar.setCurrentPage(selected.year(), selected.month())
        self.calendar.clicked.connect(self._pick)
        self.calendar.activated.connect(self._pick)  # Invio da tastiera
        today = QPushButton("Oggi")
        today.setObjectName("Chip")
        today.setCursor(Qt.CursorShape.PointingHandCursor)
        today.clicked.connect(lambda: self._pick(QDate.currentDate()))
        foot = QHBoxLayout()
        foot.addWidget(today)
        foot.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.calendar)
        layout.addLayout(foot)

    def _pick(self, d: QDate) -> None:
        self.picked.emit(d)
        self.close()


class DatePicker(QPushButton):
    """Campo data cliccabile: mostra la data in italiano e apre il calendario."""

    dateChanged = Signal(QDate)

    def __init__(self, d: QDate, short: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DateField")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clicca per scegliere il giorno dal calendario")
        self._short = short
        self._date = d
        self._popup: _CalendarPopup | None = None
        self.clicked.connect(self.open_calendar)
        self._update_text()

    def date(self) -> QDate:
        return self._date

    def setDate(self, d: QDate) -> None:  # noqa: N802 (stile Qt)
        if d.isValid() and d != self._date:
            self._date = d
            self._update_text()
            self.dateChanged.emit(d)

    def _update_text(self) -> None:
        text = self._date.toString("dd/MM/yyyy") if self._short else _long_label(self._date)
        self.setText(f"📅  {text}   ▾")

    def open_calendar(self) -> None:
        self._popup = _CalendarPopup(self, self._date)
        self._popup.picked.connect(self.setDate)
        self._popup.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = self.screen().availableGeometry()
        x = min(pos.x(), screen.right() - self._popup.width())
        y = pos.y() if pos.y() + self._popup.height() <= screen.bottom() else \
            self.mapToGlobal(QPoint(0, 0)).y() - self._popup.height() - 4
        self._popup.move(max(screen.left(), x), max(screen.top(), y))
        self._popup.show()
        self._popup.calendar.setFocus()


class DateTimePicker(QWidget):
    """Data (con calendario a tendina) + ora. Stessa interfaccia di QDateTimeEdit."""

    def __init__(self, value: QDateTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.date_field = DatePicker(value.date())
        self.time_field = QTimeEdit(value.time())
        self.time_field.setDisplayFormat("HH:mm")
        self.time_field.setFixedWidth(84)
        self.time_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_field.setToolTip("Scrivi l'ora o usa la rotellina del mouse")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.date_field, 1)
        layout.addWidget(self.time_field)

    def dateTime(self) -> QDateTime:  # noqa: N802 (stile Qt)
        return QDateTime(self.date_field.date(), self.time_field.time())

    def setDateTime(self, value: QDateTime) -> None:  # noqa: N802 (stile Qt)
        self.date_field.setDate(value.date())
        self.time_field.setTime(QTime(value.time().hour(), value.time().minute()))
