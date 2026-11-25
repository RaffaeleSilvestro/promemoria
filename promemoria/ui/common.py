"""Elementi grafici condivisi: icona, colori, suono sveglia."""
from __future__ import annotations

import logging
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


ALARM_RINGS = 3
RING_INTERVAL_MS = 1_000


class AlarmSound(QObject):
    """Tre squilli in tre secondi, poi silenzio: si ferma da solo."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rings = 0
        self._timer = QTimer(self)
        self._timer.setInterval(RING_INTERVAL_MS)
        self._timer.timeout.connect(self._next)

    @staticmethod
    def _play(alias: str | None) -> None:
        if winsound is None:
            return
        flags = winsound.SND_ALIAS | winsound.SND_ASYNC if alias else winsound.SND_PURGE
        try:
            winsound.PlaySound(alias, flags)
        except RuntimeError as exc:
            logging.getLogger(__name__).warning("Suono non riprodotto: %s", exc)

    def _ring(self) -> None:
        self._rings += 1
        self._play("SystemExclamation")

    def _next(self) -> None:
        if self._rings >= ALARM_RINGS:
            self.stop()
        else:
            self._ring()

    def start(self) -> None:
        if self._timer.isActive():
            return  # sta già suonando: più promemoria insieme non allungano il suono
        self._rings = 0
        self._ring()
        self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._play(None)
