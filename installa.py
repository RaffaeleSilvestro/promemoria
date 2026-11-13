"""Crea il logo e i collegamenti (Desktop + menu Start) di Promemoria.

Uso:  python installa.py
Poi: apri Promemoria, tasto destro sulla sua icona nella barra delle applicazioni
     -> "Aggiungi alla barra delle applicazioni".
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from promemoria.core import winshell  # noqa: E402
from promemoria.ui.logo import write_ico  # noqa: E402


def main() -> int:
    if sys.platform != "win32":
        print("Questo installer serve solo su Windows.")
        return 1
    app = QGuiApplication([])  # noqa: F841 - necessaria per disegnare il logo
    icon = write_ico()
    created = []
    for lnk in (winshell.start_menu_shortcut(), winshell.desktop_shortcut()):
        if lnk.exists():
            lnk.unlink()  # ricrea sempre: aggiorna percorso e icona
        created.append(winshell.create_shortcut(lnk, icon))
    for lnk in created:
        print(f"Creato: {lnk}")
    print('\nOra apri Promemoria e fai tasto destro sulla sua icona nella barra delle '
          'applicazioni -> "Aggiungi alla barra delle applicazioni".')
    return 0


if __name__ == "__main__":
    sys.exit(main())
