"""Elementi grafici condivisi: icona, colori, suono sveglia."""
from __future__ import annotations

from colorsys import hsv_to_rgb
from zlib import crc32

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor, QIcon

try:
    import winsound
except ImportError:  # non Windows
    winsound = None

PRIORITY_COLORS = {0: "#8a8f98", 1: "#2d6cdf", 2: "#d93a3a"}


def category_color(category: str) -> QColor:
    if not category:
        return QColor("#8a8f98")
    hue = (crc32(category.lower().encode()) % 360) / 360
    r, g, b = hsv_to_rgb(hue, 0.55, 0.75)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


_ICON: QIcon | None = None


def app_icon() -> QIcon:
    """Logo stile Promemoria di iPhone (vedi logo.py), calcolato una sola volta."""
    global _ICON
    if _ICON is None:
        from .logo import logo_icon

        _ICON = logo_icon()
    return _ICON


class AlarmSound(QObject):
    """Suono ripetuto finché non viene fermato (sveglia)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(1400)
        self._timer.timeout.connect(self._beep)
        self._users = 0

    def _beep(self) -> None:
        if winsound is not None:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)

    def start(self) -> None:
        self._users += 1
        if self._users == 1:
            self._beep()
            self._timer.start()

    def stop(self) -> None:
        self._users = max(0, self._users - 1)
        if self._users == 0:
            self._timer.stop()
