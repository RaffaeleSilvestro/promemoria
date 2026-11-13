"""Finestra di creazione/modifica di un promemoria."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QLocale, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.formatting import DAYS_SHORT, FREQ_LABELS, PRIORITIES, format_offset
from ..core.models import Channels, Recurrence, Reminder
from ..core.settings import Settings

ALERT_PRESETS = (0, 5, 10, 30, 60, 180, 1440, 2880, 10080)
FREQ_ORDER = ("none", "daily", "weekly", "monthly", "yearly")
FREQ_UNITS = {"daily": "giorni", "weekly": "settimane", "monthly": "mesi", "yearly": "anni"}


def _to_qdt(dt: datetime) -> QDateTime:
    return QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)


def _chip(text: str, checkable: bool = False) -> QPushButton:
    chip = QPushButton(text)
    chip.setObjectName("Chip")
    chip.setCheckable(checkable)
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    return chip


class EventDialog(QDialog):
    def __init__(self, settings: Settings, reminder: Reminder | None = None,
                 default_start: datetime | None = None, default_title: str = "",
                 default_category: str = "", default_channels: Channels | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._existing = reminder
        self._settings = settings
        self.setWindowTitle("Modifica promemoria" if reminder else "Nuovo promemoria")
        self.setMinimumWidth(560)
        base = reminder or Reminder(
            title="x",
            start=default_start or (datetime.now() + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0),
            alerts=(0, 10), category=default_category,
            channels=default_channels or Channels(),
        )

        heading = QLabel(self.windowTitle())
        heading.setObjectName("PageTitle")
        heading.setStyleSheet("font-size: 20px;")
        self.title = QLineEdit(base.title if reminder else default_title)
        self.title.setObjectName("QuickAdd")
        self.title.setPlaceholderText("Cosa devi ricordare?")
        self.when = QDateTimeEdit(_to_qdt(base.start))
        self.when.setLocale(QLocale(QLocale.Language.Italian))
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dddd d MMMM yyyy   HH:mm")
        self.when.setMinimumWidth(280)
        self.notes = QPlainTextEdit(base.notes)
        self.notes.setPlaceholderText("Dettagli, indirizzo, link… (facoltativo)")
        self.notes.setFixedHeight(64)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(["", *settings.categories])
        self.category.setCurrentText(base.category)
        self.category.lineEdit().setPlaceholderText("Nessuna")

        self._priority = base.priority
        self._priority_chips: dict[int, QPushButton] = {}
        prio_row = QHBoxLayout()
        prio_row.setSpacing(6)
        for value, label in PRIORITIES.items():
            chip = _chip({0: "▽ ", 1: "◇ ", 2: "❗ "}[value] + label, checkable=True)
            chip.setChecked(value == base.priority)
            chip.clicked.connect(lambda _=False, v=value: self._set_priority(v))
            self._priority_chips[value] = chip
            prio_row.addWidget(chip)
        prio_row.addStretch()

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Quando", self.when)
        form.addRow("", self._quick_when_row())
        form.addRow("Categoria", self.category)
        form.addRow("Priorità", prio_row)
        form.addRow("Note", self.notes)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)
        root.addWidget(heading)
        root.addWidget(self.title)
        root.addLayout(form)
        root.addWidget(self._build_recurrence(base.recurrence))
        root.addWidget(self._build_alerts(base.alerts))
        root.addWidget(self._build_channels(base.channels))

        cancel = QPushButton("Annulla")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salva  (Ctrl+Invio)")
        save.setObjectName("Primary")
        save.setMinimumHeight(38)
        save.setDefault(True)
        save.clicked.connect(self._on_accept)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        self.result_reminder: Reminder | None = None
        self.title.setFocus()

    def _quick_when_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label, days in (("Oggi", 0), ("Domani", 1), ("+1 settimana", 7)):
            chip = _chip(label)
            chip.clicked.connect(lambda _=False, d=days: self._shift_day(d))
            layout.addWidget(chip)
        layout.addSpacing(10)
        for hh in (9, 13, 18, 21):
            chip = _chip(f"{hh}:00")
            chip.clicked.connect(lambda _=False, h=hh: self._set_hour(h))
            layout.addWidget(chip)
        layout.addStretch()
        return row

    def _shift_day(self, days: int) -> None:
        current = self.when.dateTime().toPython()
        target = datetime.now().date() + timedelta(days=days)
        self.when.setDateTime(_to_qdt(datetime.combine(target, current.time())))

    def _set_hour(self, hour: int) -> None:
        current = self.when.dateTime().toPython()
        self.when.setDateTime(_to_qdt(current.replace(hour=hour, minute=0)))

    def _set_priority(self, value: int) -> None:
        self._priority = value
        for v, chip in self._priority_chips.items():
            chip.setChecked(v == value)

    # ---- sezioni -----------------------------------------------------
    def _build_recurrence(self, rec: Recurrence) -> QGroupBox:
        box = QGroupBox("Ripetizione")
        self.freq = QComboBox()
        for f in FREQ_ORDER:
            self.freq.addItem(FREQ_LABELS[f], f)
        self.freq.setCurrentIndex(FREQ_ORDER.index(rec.freq))
        self.interval = QSpinBox()
        self.interval.setRange(1, 365)
        self.interval.setValue(rec.interval)
        self.interval_label = QLabel()
        self.weekday_boxes = [QCheckBox(name) for name in DAYS_SHORT]
        for i, cb in enumerate(self.weekday_boxes):
            cb.setChecked(i in rec.weekdays)
        self.until_check = QCheckBox("Fino al")
        self.until_check.setChecked(rec.until is not None)
        default_until = (rec.until or self.when.dateTime().toPython() + timedelta(days=365)).date()
        self.until = QDateEdit(QDate(default_until.year, default_until.month, default_until.day))
        self.until.setCalendarPopup(True)
        self.until.setDisplayFormat("dd/MM/yyyy")

        top = QHBoxLayout()
        top.addWidget(self.freq)
        top.addWidget(QLabel("ogni"))
        top.addWidget(self.interval)
        top.addWidget(self.interval_label)
        top.addStretch()
        self.weekday_row = QWidget()
        wl = QHBoxLayout(self.weekday_row)
        wl.setContentsMargins(0, 0, 0, 0)
        for cb in self.weekday_boxes:
            wl.addWidget(cb)
        until_row = QHBoxLayout()
        until_row.addWidget(self.until_check)
        until_row.addWidget(self.until)
        until_row.addStretch()
        self.rec_details = QWidget()
        dl = QVBoxLayout(self.rec_details)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.weekday_row)
        dl.addLayout(until_row)

        layout = QVBoxLayout(box)
        layout.addLayout(top)
        layout.addWidget(self.rec_details)
        self.freq.currentIndexChanged.connect(self._refresh_recurrence)
        self.until_check.toggled.connect(self.until.setEnabled)
        self.until.setEnabled(rec.until is not None)
        self._refresh_recurrence()
        return box

    def _refresh_recurrence(self) -> None:
        freq = self.freq.currentData()
        self.interval.setVisible(freq != "none")
        self.interval_label.setVisible(freq != "none")
        self.interval_label.setText(FREQ_UNITS.get(freq, ""))
        self.rec_details.setVisible(freq != "none")
        self.weekday_row.setVisible(freq == "weekly")
        self.adjustSize()

    def _build_alerts(self, alerts: tuple[int, ...]) -> QGroupBox:
        box = QGroupBox("Avvisi")
        grid = QGridLayout(box)
        offsets = sorted(set(ALERT_PRESETS) | set(alerts))
        self.alert_boxes: dict[int, QCheckBox] = {}
        for i, minutes in enumerate(offsets):
            cb = QCheckBox(format_offset(minutes))
            cb.setChecked(minutes in alerts)
            self.alert_boxes[minutes] = cb
            grid.addWidget(cb, i // 3, i % 3)
        return box

    def _build_channels(self, ch: Channels) -> QGroupBox:
        box = QGroupBox("Come avvisarmi")
        s = self._settings
        self.ch_popup = QCheckBox("Popup")
        self.ch_popup.setChecked(ch.popup)
        self.ch_sound = QCheckBox("Sveglia sonora")
        self.ch_sound.setChecked(ch.sound)
        self.ch_email = QCheckBox("Email" + ("" if s.email_ready else " ⚠"))
        self.ch_email.setChecked(ch.email)
        if not s.email_ready:
            self.ch_email.setToolTip("Email non ancora configurata: vai in Impostazioni")
        self.ch_tg = QCheckBox("Telegram" + ("" if s.telegram_ready else " ⚠"))
        if not s.telegram_ready:
            self.ch_tg.setToolTip("Telegram non ancora configurato: vai in Impostazioni")
        self.ch_tg.setChecked(ch.telegram)
        layout = QHBoxLayout(box)
        for cb in (self.ch_popup, self.ch_sound, self.ch_email, self.ch_tg):
            layout.addWidget(cb)
        return box

    # ---- risultato ---------------------------------------------------
    def _on_accept(self) -> None:
        title = self.title.text().strip()
        if not title:
            QMessageBox.warning(self, "Titolo mancante", "Scrivi un titolo per il promemoria.")
            return
        alerts = tuple(m for m, cb in self.alert_boxes.items() if cb.isChecked())
        if not alerts:
            QMessageBox.warning(self, "Avviso mancante", "Seleziona almeno un avviso.")
            return
        channels = Channels(self.ch_popup.isChecked(), self.ch_sound.isChecked(),
                            self.ch_email.isChecked(), self.ch_tg.isChecked())
        if not any((channels.popup, channels.sound, channels.email, channels.telegram)):
            QMessageBox.warning(self, "Canale mancante", "Scegli almeno un modo per essere avvisato.")
            return
        start = self.when.dateTime().toPython().replace(second=0, microsecond=0)
        freq = self.freq.currentData()
        weekdays = tuple(i for i, cb in enumerate(self.weekday_boxes) if cb.isChecked())
        until = None
        if freq != "none" and self.until_check.isChecked():
            until = datetime.combine(self.until.date().toPython(), datetime.min.time())
            if until.date() < start.date():
                QMessageBox.warning(self, "Data non valida", "La data finale è precedente all'inizio.")
                return
        recurrence = Recurrence(freq, self.interval.value(),
                                weekdays if freq == "weekly" else (), until)
        previous = self._existing
        self.result_reminder = Reminder(
            title=title, start=start, id=previous.id if previous else None,
            notes=self.notes.toPlainText().strip(),
            priority=self._priority,
            category=self.category.currentText().strip(),
            recurrence=recurrence, alerts=alerts, channels=channels,
            completed=previous.completed if previous else False,
        )
        self.accept()
