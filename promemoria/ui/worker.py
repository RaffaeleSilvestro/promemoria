"""Esecuzione di operazioni lente (rete, login) fuori dal thread dell'interfaccia."""
from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.gauth import GAuthError
from ..core.gcal import GCalError
from ..core.notify import NotifyError

USER_ERRORS = (NotifyError, GAuthError, GCalError)
log = logging.getLogger(__name__)
_alive: set[_Task] = set()  # tiene vivi i task finché non hanno risposto


class _Signals(QObject):
    done = Signal(object, str)  # (risultato, messaggio d'errore)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self._fn(), "")
        except USER_ERRORS as exc:
            self.signals.done.emit(None, str(exc))
        except Exception as exc:  # noqa: BLE001 - mai far cadere l'app per un errore qui
            log.exception("Errore in un'operazione in background")
            self.signals.done.emit(None, f"Errore imprevisto: {type(exc).__name__}")


def run_in_thread(fn: Callable[[], Any], on_done: Callable[[Any, str], None]) -> None:
    """Esegue fn in background; on_done(risultato, errore) viene chiamata nel thread UI."""
    task = _Task(fn)

    def finished(result: Any, error: str) -> None:
        _alive.discard(task)
        on_done(result, error)

    task.signals.done.connect(finished)
    _alive.add(task)
    QThreadPool.globalInstance().start(task)
