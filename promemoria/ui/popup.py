"""Popup in primo piano mostrato quando scatta un promemoria."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ..core.formatting import format_offset, format_recurrence, format_when
from ..core.models import Due
from . import theme
from .common import category_color

SNOOZE_LABELS = {5: "+5 min", 10: "+10 min", 15: "+15 min", 30: "+30 min",
                 60: "+1 ora", 180: "+3 ore", 1440: "Domani"}


def snooze_choices(default: int) -> list[int]:
    choices = [default, 60, 1440] if default not in (60, 1440) else [10, 60, 1440]
    return list(dict.fromkeys(choices))


class ReminderPopup(QDialog):
    done = Signal(object)  # Due
    snoozed = Signal(object, int)  # Due, minuti
    closed = Signal(object)  # Due

    def __init__(self, due: Due, default_snooze: int, sound_on: bool) -> None:
        super().__init__(None)
        self.due = due
        self.sound_on = sound_on
        r = due.reminder
        p = theme.current()
        color = theme.priority_color(r.priority)
        self.setWindowTitle(f"⏰ {r.title}")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        # visibile e cliccabile, ma non ruba mai il primo piano ad altre app
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFixedWidth(420)

        accent = QFrame()
        accent.setFixedHeight(6)
        accent.setStyleSheet(f"background: {color}; border: none;")

        icon = QLabel("🔔" if sound_on else "⏰")
        icon.setStyleSheet(f"font-size: 30px; background: {p.primary_soft};"
                           " border-radius: 26px; padding: 6px;")
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(r.title)
        title.setObjectName("PopupTitle")
        title.setWordWrap(True)
        when = QLabel(format_when(due.occurrence))
        when.setObjectName("PopupWhen")
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(title)
        head_text.addWidget(when)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(head_text, 1)

        body = QVBoxLayout()
        body.setContentsMargins(22, 18, 22, 18)
        body.setSpacing(10)
        body.addLayout(head)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        texts = []
        if due.snoozed:
            texts.append(("💤 Posticipato", ""))
        elif due.offset_min:
            texts.append((f"⏳ {format_offset(due.offset_min)}", ""))
        if r.priority == 2:
            texts.append(("❗ Priorità alta", "late"))
        if r.is_recurring:
            texts.append(("↻ " + format_recurrence(r.recurrence), ""))
        for text, kind in texts:
            b = QLabel(text)
            b.setObjectName("Badge")
            if kind:
                b.setProperty("kind", kind)
            badges.addWidget(b)
        if r.category:
            cat = QLabel(f"● {r.category}")
            cat.setObjectName("Badge")
            cat.setStyleSheet(f"color: {category_color(r.category).name()};")
            badges.addWidget(cat)
        badges.addStretch()
        if texts or r.category:
            body.addLayout(badges)
        if due.missed:
            warn = QLabel("⚠️  Scattato mentre l'app era chiusa o il PC spento")
            warn.setObjectName("PopupWarning")
            body.addWidget(warn)
        if r.notes.strip():
            notes = QLabel(r.notes.strip())
            notes.setObjectName("PopupNotes")
            notes.setWordWrap(True)
            notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.addWidget(notes)

        snooze_row = QHBoxLayout()
        snooze_row.setSpacing(6)
        label = QLabel("Posticipa:")
        label.setObjectName("Muted")
        snooze_row.addWidget(label)
        for minutes in snooze_choices(default_snooze):
            chip = QPushButton(SNOOZE_LABELS.get(minutes, f"+{minutes} min"))
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, m=minutes: self._on_snooze(m))
            snooze_row.addWidget(chip)
        snooze_row.addStretch()
        body.addSpacing(4)
        body.addLayout(snooze_row)

        btn_close = QPushButton("Chiudi")
        btn_close.setObjectName("Ghost")
        btn_close.clicked.connect(self.close)
        btn_done = QPushButton("✓  Fatto")
        btn_done.setObjectName("Primary")
        btn_done.setDefault(True)
        btn_done.setMinimumHeight(38)
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.clicked.connect(self._on_done)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(btn_close)
        actions.addWidget(btn_done)
        body.addLayout(actions)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(accent)
        layout.addLayout(body)

    def place(self, index: int) -> None:
        """Posiziona il popup in basso a destra, impilando i successivi verso l'alto."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.adjustSize()
        frame_extra = 40
        y = area.bottom() - self.height() - frame_extra - 16 - index * 36
        x = area.right() - self.width() - 24 - index * 16
        self.move(max(area.left(), x), max(area.top(), y))

    def _on_done(self) -> None:
        self.done.emit(self.due)
        self.close()

    def _on_snooze(self, minutes: int) -> None:
        self.snoozed.emit(self.due, minutes)
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.closed.emit(self.due)
        super().closeEvent(event)
