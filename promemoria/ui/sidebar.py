"""Barra laterale di navigazione."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from .common import app_icon, category_color

VIEWS = (
    ("today", "☀️", "Oggi", "Ctrl+1"),
    ("upcoming", "🗓️", "Prossimi giorni", "Ctrl+2"),
    ("calendar", "📅", "Calendario", "Ctrl+3"),
    ("overdue", "⏰", "In ritardo", "Ctrl+4"),
    ("done", "✅", "Completati", "Ctrl+5"),
)


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class NavButton(QPushButton):
    def __init__(self, key: str, icon: str, text: str, icon_color: str = "") -> None:
        super().__init__()
        self.key = key
        self.setObjectName("Nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        icon_label = QLabel(icon)
        icon_label.setFixedWidth(22)
        if icon_color:
            icon_label.setStyleSheet(f"color: {icon_color}; font-size: 14px;")
        self._text = QLabel(text)
        self._text.setObjectName("NavText")
        self._count = QLabel()
        self._count.setObjectName("NavCount")
        self._count.setFixedHeight(18)
        self._count.setMinimumWidth(18)
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        for widget in (icon_label, self._text, self._count):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)
        layout.addWidget(self._text, 1)
        layout.addWidget(self._count)
        self.setMinimumHeight(38)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._text.setProperty("active", "true" if checked else "false")
        _repolish(self._text)

    def set_count(self, count: int, alert: bool = False) -> None:
        self._count.setVisible(count > 0)
        self._count.setText(str(count))
        self._count.setProperty("alert", "true" if alert else "false")
        _repolish(self._count)


class Sidebar(QFrame):
    selected = Signal(str)
    new_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    category_rename_requested = Signal(str)
    category_delete_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(240)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, NavButton] = {}

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(30, 30))
        name = QLabel("Promemoria")
        name.setObjectName("AppName")
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch()

        new_btn = QPushButton("＋  Nuovo promemoria")
        new_btn.setObjectName("Primary")
        new_btn.setMinimumHeight(40)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setToolTip("Ctrl+N")
        new_btn.clicked.connect(self.new_requested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)
        layout.addLayout(brand)
        layout.addSpacing(14)
        layout.addWidget(new_btn)
        layout.addSpacing(10)
        for key, icon, text, shortcut in VIEWS:
            btn = self._add_button(key, icon, text)
            btn.setToolTip(shortcut)
            layout.addWidget(btn)

        section = QLabel("CATEGORIE")
        section.setObjectName("SectionLabel")
        layout.addWidget(section)
        self._cat_box = QVBoxLayout()
        self._cat_box.setSpacing(2)
        cat_widget = QWidget()
        cat_widget.setLayout(self._cat_box)
        self._cat_box.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidget(cat_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        status = QLabel("●  In ascolto: gli avvisi sono attivi")
        status.setObjectName("Hint")
        status.setStyleSheet("color: #2fa36b;")
        settings_btn = QPushButton("⚙  Impostazioni")
        settings_btn.setObjectName("Ghost")
        settings_btn.setStyleSheet("text-align: left; padding: 8px 10px;")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setToolTip("Ctrl+,")
        settings_btn.clicked.connect(self.settings_requested.emit)
        quit_btn = QPushButton("⏻  Esci")
        quit_btn.setObjectName("Ghost")
        quit_btn.setStyleSheet("padding: 8px 10px;")
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setToolTip("Chiude del tutto l'app (gli avvisi si fermano)")
        quit_btn.clicked.connect(self.quit_requested.emit)
        bottom = QHBoxLayout()
        bottom.addWidget(settings_btn, 1)
        bottom.addWidget(quit_btn)
        layout.addLayout(bottom)
        layout.addWidget(status)
        self._group.buttonClicked.connect(lambda b: self.selected.emit(b.key))

    def _add_button(self, key: str, icon: str, text: str, color: str = "") -> NavButton:
        btn = NavButton(key, icon, text, color)
        self._group.addButton(btn)
        self._buttons[key] = btn
        return btn

    def category_menu_actions(self, name: str) -> list[tuple[str, Signal]]:
        return [("✎  Rinomina categoria…", self.category_rename_requested),
                ("🗑  Elimina categoria", self.category_delete_requested)]

    def _category_menu(self, button: QPushButton, name: str, pos) -> None:
        menu = QMenu(self)
        for label, signal in self.category_menu_actions(name):
            menu.addAction(label).triggered.connect(lambda _=False, s=signal: s.emit(name))
        menu.exec(button.mapToGlobal(pos))

    def select(self, key: str) -> None:
        btn = self._buttons.get(key) or self._buttons["today"]
        btn.setChecked(True)

    def set_counts(self, counts: dict[str, tuple[int, bool]]) -> None:
        for key, (count, alert) in counts.items():
            if key in self._buttons:
                self._buttons[key].set_count(count, alert)

    def set_categories(self, categories: list[str], counts: dict[str, int]) -> None:
        current = self._group.checkedButton()
        current_key = current.key if current else "today"
        for key in [k for k in self._buttons if k.startswith("cat:")]:
            btn = self._buttons.pop(key)
            self._group.removeButton(btn)
            btn.deleteLater()
        while self._cat_box.count():
            self._cat_box.takeAt(0)
        for cat in categories:
            btn = self._add_button(f"cat:{cat}", "●", cat, category_color(cat).name())
            btn.set_count(counts.get(cat, 0))
            btn.setToolTip("Tasto destro per rinominare o eliminare")
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, name=cat: self._category_menu(b, name, pos))
            self._cat_box.addWidget(btn)
        if not categories:
            hint = QLabel("Le categorie che usi\ncompariranno qui")
            hint.setObjectName("Hint")
            hint.setContentsMargins(10, 4, 0, 0)
            self._cat_box.addWidget(hint)
        self._cat_box.addStretch()
        self.select(current_key if current_key in self._buttons else "today")
