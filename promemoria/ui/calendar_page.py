"""Vista calendario: mese con pallini e lista del giorno selezionato."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QLocale, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from . import theme
from .cards import CardList


class DotCalendar(QCalendarWidget):
    """Calendario che disegna un pallino sui giorni con promemoria e un anello su oggi."""

    def __init__(self) -> None:
        super().__init__()
        self._marks: dict[date, str] = {}
        self.setLocale(QLocale(QLocale.Language.Italian))
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setMinimumSize(360, 360)

    def apply_palette(self) -> None:
        p = theme.current()
        header = QTextCharFormat()
        header.setForeground(QColor(p.muted))
        header.setFontWeight(QFont.Weight.DemiBold)
        header.setBackground(QColor(p.surface))
        self.setHeaderTextFormat(header)
        weekend = QTextCharFormat()
        weekend.setForeground(QColor(p.muted))
        for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
            self.setWeekdayTextFormat(day, weekend)
        normal = QTextCharFormat()
        normal.setForeground(QColor(p.text))
        for day in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                    Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday):
            self.setWeekdayTextFormat(day, normal)

    def set_marks(self, marks: dict[date, str]) -> None:
        self._marks = marks
        self.updateCells()

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate) -> None:  # noqa: N802
        d = qdate.toPython()
        p = theme.current()
        selected = qdate == self.selectedDate()
        in_month = qdate.month() == self.monthShown()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor(p.surface))
        side = min(rect.width(), rect.height()) - 10
        box = QRect(rect.center().x() - side // 2, rect.center().y() - side // 2, side, side)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.primary))
            painter.drawRoundedRect(box, 10, 10)
        elif d == date.today():
            painter.setPen(QPen(QColor(p.primary), 1.8))
            painter.setBrush(QColor(p.primary_soft))
            painter.drawRoundedRect(box, 10, 10)

        if selected:
            text_color = QColor(p.on_primary)
        elif not in_month:
            text_color = QColor(p.muted)
            text_color.setAlpha(110)
        elif d.weekday() >= 5:
            text_color = QColor(p.muted)
        else:
            text_color = QColor(p.text)
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.Bold if selected or d == date.today() else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect.adjusted(0, 0, 0, -6), Qt.AlignmentFlag.AlignCenter, str(qdate.day()))

        color = self._marks.get(d)
        if color:
            dot = QColor(p.on_primary) if selected else QColor(color)
            if not in_month and not selected:
                dot.setAlpha(110)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(rect.center().x() + 0.5, rect.center().y() + 11), 2.8, 2.8)
        painter.restore()


class CalendarPage(QWidget):
    add_requested = Signal(object)  # date

    def __init__(self) -> None:
        super().__init__()
        self.calendar = DotCalendar()
        self.calendar.activated.connect(lambda d: self.add_requested.emit(d.toPython()))
        cal_card = QFrame()
        cal_card.setObjectName("CalendarCard")
        cl = QVBoxLayout(cal_card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.addWidget(self.calendar)
        today_btn = QPushButton("Vai a oggi")
        today_btn.setObjectName("Chip")
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.clicked.connect(self.go_today)
        hint = QLabel("Doppio clic su un giorno per aggiungere")
        hint.setObjectName("Hint")
        foot = QHBoxLayout()
        foot.addWidget(today_btn)
        foot.addStretch()
        foot.addWidget(hint)
        cl.addLayout(foot)

        self.day_title = QLabel()
        self.day_title.setObjectName("EmptyTitle")
        add = QPushButton("＋ Aggiungi")
        add.setObjectName("Chip")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(lambda: self.add_requested.emit(self.calendar.selectedDate().toPython()))
        head = QHBoxLayout()
        head.addWidget(self.day_title)
        head.addStretch()
        head.addWidget(add)
        self.cards = CardList()
        right = QVBoxLayout()
        right.addLayout(head)
        right.addWidget(self.cards, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(cal_card, 1)
        layout.addLayout(right, 1)

    def go_today(self) -> None:
        today = QDate.currentDate()
        self.calendar.setSelectedDate(today)
        self.calendar.setCurrentPage(today.year(), today.month())

    def selected_date(self) -> date:
        return self.calendar.selectedDate().toPython()
