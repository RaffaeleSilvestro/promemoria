"""Mostra i popup senza disturbare: con un'app a schermo intero aspettano."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.db import Repository, key
from ..core.fullscreen import is_fullscreen_app_active
from ..core.models import Due
from ..core.settings import Settings
from .common import AlarmSound
from .popup import ReminderPopup

POLL_MS = 3_000
log = logging.getLogger(__name__)


class AlertPresenter(QObject):
    done = Signal(object)  # Due
    snoozed = Signal(object, int)  # Due, minuti

    def __init__(self, repo: Repository, get_settings: Callable[[], Settings], alarm: AlarmSound,
                 is_fullscreen: Callable[[], bool] = is_fullscreen_app_active,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._get_settings = get_settings
        self._alarm = alarm
        self._is_fullscreen = is_fullscreen
        self.popups: list[ReminderPopup] = []
        self.waiting: list[Due] = []
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.flush)

    def present(self, due: Due, sound: bool) -> None:
        if sound:
            self._alarm.start()
        if self._is_fullscreen():
            log.info("App a schermo intero: popup rimandato")
            self.waiting.append(due)
            self._timer.start()
        else:
            self._show(due)

    def flush(self) -> None:
        """Mostra i popup in attesa appena lo schermo intero finisce."""
        if not self.waiting or self._is_fullscreen():
            return
        for due in self._take_needed():
            self._show(due)

    def shutdown(self) -> None:
        """Alla chiusura, i popup non ancora visti ricompaiono al prossimo avvio."""
        for due in self._take_needed():
            self._repo.add_snooze(due.reminder.id, due.occurrence, datetime.now())

    def _take_needed(self) -> list[Due]:
        pending, self.waiting = self.waiting, []
        self._timer.stop()
        return [due for due in pending if self._still_needed(due)]

    def _still_needed(self, due: Due) -> bool:
        current = self._repo.get(due.reminder.id)
        return (current is not None and not current.completed
                and (due.reminder.id, key(due.occurrence)) not in self._repo.done_set())

    def _show(self, due: Due) -> None:
        popup = ReminderPopup(due, self._get_settings().snooze_default,
                              due.reminder.channels.sound)
        popup.done.connect(self.done)
        popup.snoozed.connect(self.snoozed)
        popup.closed.connect(lambda _d, p=popup: self._on_closed(p))
        self.popups.append(popup)
        popup.place(len(self.popups) - 1)
        popup.show()  # senza attivarlo: il primo piano resta all'app in uso

    def _on_closed(self, popup: ReminderPopup) -> None:
        self._alarm.stop()
        if popup in self.popups:
            self.popups.remove(popup)
