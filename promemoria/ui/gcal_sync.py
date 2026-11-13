"""Sincronizzazione automatica con Google Calendar (debounce + periodica)."""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from ..core import gauth, gcal
from ..core.db import Repository
from ..core.settings import Settings
from .google_tab import system_timezone
from .worker import run_in_thread

DEBOUNCE_MS = 3_000
PERIOD_MS = 15 * 60 * 1000
ERROR_NOTICE_EVERY = timedelta(hours=1)
log = logging.getLogger(__name__)


class GCalSync(QObject):
    def __init__(self, repo: Repository, get_settings: Callable[[], Settings],
                 save_settings: Callable[[Settings], None],
                 notify_error: Callable[[str], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._get_settings = get_settings
        self._save_settings = save_settings
        self._notify_error = notify_error
        self._running = False
        self._pending = False
        self._last_notice: datetime | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.sync_now)
        self._periodic = QTimer(self)
        self._periodic.timeout.connect(self.sync_now)
        self._periodic.start(PERIOD_MS)

    def schedule(self, delay_ms: int = DEBOUNCE_MS) -> None:
        if self._get_settings().gcal_ready:
            self._debounce.start(delay_ms)

    def sync_now(self) -> None:
        s = self._get_settings()
        if not s.gcal_ready:
            return
        if self._running:
            self._pending = True
            return
        tz = system_timezone()
        plan = gcal.plan_sync(self._repo.list(), self._repo.gcal_map(), datetime.now(),
                              tz, s.gcal_email)
        credentials, calendar_id = s.gcal_credentials, s.gcal_calendar_id

        def work():
            session = gauth.session(credentials)
            current = gcal.ensure_calendar(session, calendar_id, tz)
            if current != calendar_id:
                return current, None  # calendario ricreato: va rifatto tutto
            result = gcal.apply_plan(session, current, plan) if not plan.is_empty else gcal.SyncResult()
            return current, result

        self._running = True
        run_in_thread(work, self._done)

    def _done(self, outcome, error: str) -> None:
        self._running = False
        if error:
            self._report(error)
        else:
            calendar_id, result = outcome
            if result is None:
                log.info("Calendario Google ricreato, risincronizzo tutto")
                self._repo.clear_gcal()
                self._save_settings(replace(self._get_settings(), gcal_calendar_id=calendar_id))
                self._pending = True
            else:
                for rid, event_id, h in result.saved:
                    self._repo.set_gcal(rid, event_id, h)
                for rid in result.removed:
                    self._repo.delete_gcal(rid)
                if result.saved or result.removed:
                    log.info("Google Calendar: %d aggiornati, %d eliminati",
                             len(result.saved), len(result.removed))
                if result.errors:
                    self._report(result.errors[0])
                else:
                    self._last_notice = None
        if self._pending:
            self._pending = False
            self.schedule(500)

    def _report(self, message: str) -> None:
        log.warning(message)
        now = datetime.now()
        if self._last_notice is None or now - self._last_notice > ERROR_NOTICE_EVERY:
            self._last_notice = now
            self._notify_error(message)
