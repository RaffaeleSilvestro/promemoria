"""Campo categoria: scrivi una nuova categoria o clicca una di quelle esistenti."""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .common import category_color
from .flow_layout import FlowLayout

NONE_LABEL = "Nessuna"


def merge_categories(suggested: Iterable[str], used: Iterable[str]) -> list[str]:
    """Unisce categorie suggerite e usate, senza doppioni (maiuscole ignorate), in ordine alfabetico."""
    by_key: dict[str, str] = {}
    for name in (*used, *suggested):  # a parità, vince il nome già usato nei promemoria
        clean = name.strip()
        if clean and clean.lower() not in by_key:
            by_key[clean.lower()] = clean
    return sorted(by_key.values(), key=str.lower)


class CategoryPicker(QWidget):
    def __init__(self, categories: list[str], current: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._names = merge_categories(categories, [])
        self._canonical = {n.lower(): n for n in self._names}

        self.edit = QLineEdit(current)
        self.edit.setPlaceholderText("Scrivi una nuova categoria o clicca una di quelle qui sotto")
        self.edit.setClearButtonEnabled(True)
        completer = QCompleter(self._names, self.edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.edit.setCompleter(completer)
        self.edit.textChanged.connect(self._sync)

        self._chips: dict[str, QPushButton] = {}
        chips_box = QWidget()
        flow = FlowLayout(chips_box)
        for name in (NONE_LABEL, *self._names):
            chip = QPushButton(name if name == NONE_LABEL else f"● {name}")
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            if name != NONE_LABEL:
                chip.setStyleSheet(f"QPushButton {{ color: {category_color(name).name()}; }}")
                chip.setToolTip(f"Usa la categoria «{name}»")
            chip.clicked.connect(lambda _=False, n=name: self._choose(n))
            self._chips[name] = chip
            flow.addWidget(chip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.edit)
        layout.addWidget(chips_box)
        self._sync()

    # ---- API usata dal modulo ------------------------------------------------
    def currentText(self) -> str:  # noqa: N802 (stile Qt)
        """La categoria scelta; se esiste già (anche con maiuscole diverse) usa quel nome."""
        typed = self.edit.text().strip()
        return self._canonical.get(typed.lower(), typed)

    def setCurrentText(self, text: str) -> None:  # noqa: N802 (stile Qt)
        self.edit.setText(text)

    def chip(self, name: str) -> QPushButton:
        return self._chips[name]

    def chip_names(self) -> list[str]:
        return list(self._chips)

    # ---- interni ---------------------------------------------------------------
    def _choose(self, name: str) -> None:
        self.edit.setText("" if name == NONE_LABEL else name)
        self._sync()  # anche se il testo non cambia, ripristina l'evidenziazione

    def _sync(self) -> None:
        typed = self.edit.text().strip()
        match = NONE_LABEL if not typed else self._canonical.get(typed.lower())
        for name, chip in self._chips.items():
            chip.setChecked(name == match)
