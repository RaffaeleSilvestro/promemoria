"""Card dei promemoria e lista scorrevole raggruppata."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout,
    QWidget,
)

from ..core.formatting import format_recurrence
from ..core.models import AgendaItem
from . import theme
from .common import category_color


@dataclass(frozen=True)
class Group:
    title: str
    items: tuple[AgendaItem, ...]
    alert: bool = False
    show_date: bool = False


@dataclass(frozen=True)
class EmptyState:
    icon: str
    title: str
    hint: str


def _badge(text: str, kind: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Badge")
    if kind:
        label.setProperty("kind", kind)
    return label


class ItemCard(QFrame):
    toggled = Signal(object)
    edit = Signal(object)
    delete = Signal(object)

    def __init__(self, item: AgendaItem, show_date: bool, now: datetime) -> None:
        super().__init__()
        self.item = item
        r = item.reminder
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Doppio clic per modificare")

        check = QToolButton()
        check.setCheckable(True)
        check.setChecked(item.done)
        check.setText("✓" if item.done else "")
        check.setFixedSize(24, 24)
        check.setCursor(Qt.CursorShape.PointingHandCursor)
        check.setToolTip("Segna come fatto" if not item.done else "Riapri")
        color = theme.priority_color(r.priority)
        fill = color if item.done else "transparent"
        check.setStyleSheet(
            f"QToolButton {{ border: 2px solid {color}; border-radius: 12px; background: {fill};"
            f" color: white; font-weight: 700; }}"
            f"QToolButton:hover {{ background: {color}; color: white; }}")
        check.clicked.connect(lambda: self.toggled.emit(self.item))

        title = QLabel(r.title)
        title.setObjectName("CardTitle")
        title.setProperty("done", "true" if item.done else "false")
        title.setWordWrap(True)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        when = item.occurrence.strftime("%d/%m · %H:%M" if show_date else "%H:%M")
        late = not item.done and item.occurrence < now
        meta.addWidget(_badge(("⏱ " if late else "🕑 ") + when, "late" if late else "time"))
        if r.priority == 2:
            meta.addWidget(_badge("❗ Alta", "late"))
        if r.category:
            cat = _badge(f"● {r.category}")
            cat.setStyleSheet(f"color: {category_color(r.category).name()};")
            meta.addWidget(cat)
        if r.is_recurring:
            meta.addWidget(_badge("↻ " + format_recurrence(r.recurrence)))
        icons = "".join(icon for on, icon in ((r.channels.sound, "🔔"), (r.channels.email, "✉️"),
                                               (r.channels.telegram, "✈️")) if on)
        if icons:
            ch = QLabel(icons)
            ch.setObjectName("Muted")
            ch.setToolTip("Sveglia / Email / Telegram")
            meta.addWidget(ch)
        meta.addStretch()

        text = QVBoxLayout()
        text.setSpacing(5)
        text.addWidget(title)
        text.addLayout(meta)
        if r.notes.strip():
            first_line = r.notes.strip().splitlines()[0]
            notes = QLabel(first_line[:120] + ("…" if len(first_line) > 120 else ""))
            notes.setObjectName("CardNotes")
            text.addWidget(notes)

        self._actions = []
        for symbol, tip, name, signal in (("✎", "Modifica", "CardAction", self.edit),
                                          ("🗑", "Elimina", "CardDelete", self.delete)):
            btn = QToolButton()
            btn.setObjectName(name)
            btn.setText(symbol)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, s=signal: s.emit(self.item))
            policy = btn.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            btn.setSizePolicy(policy)
            btn.hide()
            self._actions.append(btn)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 10, 12)
        row.setSpacing(12)
        row.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, 1)
        for btn in self._actions:
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt)
        for btn in self._actions:
            btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        for btn in self._actions:
            btn.hide()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.edit.emit(self.item)


class CardList(QScrollArea):
    toggled = Signal(object)
    edit = Signal(object)
    delete = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 6, 12)
        self._layout.setSpacing(8)
        self.setWidget(self._body)

    def _clear(self) -> None:
        while self._layout.count():
            child = self._layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def set_content(self, groups: list[Group], empty: EmptyState) -> None:
        scroll = self.verticalScrollBar().value()
        self._clear()
        now = datetime.now()
        groups = [g for g in groups if g.items]
        if not groups:
            self._layout.addStretch(1)
            for text, name in ((empty.icon, "EmptyIcon"), (empty.title, "EmptyTitle"),
                               (empty.hint, "Hint")):
                label = QLabel(text)
                label.setObjectName(name)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setWordWrap(True)
                self._layout.addWidget(label)
            self._layout.addStretch(2)
            return
        for group in groups:
            if group.title:
                header = QLabel(group.title.upper())
                header.setObjectName("GroupHeader")
                header.setProperty("alert", "true" if group.alert else "false")
                self._layout.addWidget(header)
            for item in group.items:
                card = ItemCard(item, group.show_date, now)
                card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
                card.toggled.connect(self.toggled)
                card.edit.connect(self.edit)
                card.delete.connect(self.delete)
                self._layout.addWidget(card)
        self._layout.addStretch(1)
        self.verticalScrollBar().setValue(scroll)
