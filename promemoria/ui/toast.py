"""Messaggio temporaneo in basso con azione facoltativa (es. Annulla)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QWidget


class Toast(QFrame):
    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("Toast")
        self._host = host
        self._callback: Callable[[], None] | None = None
        self._label = QLabel()
        self._button = QPushButton()
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_action)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(self._label)
        layout.addWidget(self._button)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        host.installEventFilter(self)
        self.hide()

    def show_message(self, text: str, action: str = "",
                     callback: Callable[[], None] | None = None, ms: int = 4500) -> None:
        self._label.setText(text)
        self._callback = callback
        self._button.setVisible(bool(action))
        self._button.setText(action)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _on_action(self) -> None:
        callback, self._callback = self._callback, None
        self.hide()
        if callback:
            callback()

    def _place(self) -> None:
        x = (self._host.width() - self.width()) // 2
        self.move(max(8, x), self._host.height() - self.height() - 24)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt)
        if obj is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return False
