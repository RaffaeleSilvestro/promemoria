"""Riconosce giochi, video e presentazioni a schermo intero (Windows)."""
from __future__ import annotations

import logging
import sys

# Valori di QUERY_USER_NOTIFICATION_STATE in cui non si deve disturbare
BUSY, D3D_FULL_SCREEN, PRESENTATION = 2, 3, 4
log = logging.getLogger(__name__)


def _notification_state() -> int | None:
    if sys.platform != "win32":
        return None
    import ctypes

    state = ctypes.c_int()
    try:
        result = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
    except (AttributeError, OSError) as exc:
        log.warning("Stato schermo intero non disponibile: %s", exc)
        return None
    return state.value if result == 0 else None


def is_fullscreen_app_active() -> bool:
    return _notification_state() in (BUSY, D3D_FULL_SCREEN, PRESENTATION)
