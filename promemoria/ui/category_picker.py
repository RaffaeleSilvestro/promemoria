"""Campo categoria compatto: freccia ▾ per scegliere tra le esistenti, o scrivine una nuova."""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QCompleter, QWidget

from .common import category_color


def merge_categories(suggested: Iterable[str], used: Iterable[str]) -> list[str]:
    """Unisce categorie suggerite e usate, senza doppioni (maiuscole ignorate), in ordine alfabetico."""
    by_key: dict[str, str] = {}
    for name in (*used, *suggested):  # a parità, vince il nome già usato nei promemoria
        clean = name.strip()
        if clean and clean.lower() not in by_key:
            by_key[clean.lower()] = clean
    return sorted(by_key.values(), key=str.lower)


def _dot_icon(color: QColor) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(2, 2, 8, 8)
    p.end()
    return QIcon(pix)


class CategoryPicker(QComboBox):
    def __init__(self, categories: list[str], current: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # le nuove si salvano col promemoria
        self.setMaxVisibleItems(12)
        self._names = merge_categories(categories, [])
        self._canonical = {n.lower(): n for n in self._names}
        for name in self._names:
            self.addItem(_dot_icon(category_color(name)), name)

        edit = self.lineEdit()
        edit.setPlaceholderText("Nessuna · clicca ▾ per scegliere o scrivine una nuova")
        edit.setClearButtonEnabled(True)
        completer = QCompleter(self._names, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(completer)
        self.setCurrentIndex(-1)
        edit.setText(current)
        self.setToolTip("Scegli una categoria dall'elenco oppure scrivine una nuova")

    def names(self) -> list[str]:
        return list(self._names)

    def currentText(self) -> str:  # noqa: N802 (stile Qt)
        """La categoria scelta; se esiste già (anche con maiuscole diverse) usa quel nome."""
        typed = self.lineEdit().text().strip()
        return self._canonical.get(typed.lower(), typed)

    def setCurrentText(self, text: str) -> None:  # noqa: N802 (stile Qt)
        self.lineEdit().setText(text)
