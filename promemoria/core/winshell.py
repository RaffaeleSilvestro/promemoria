"""Integrazione con Windows: identità dell'app sulla barra e collegamenti.

L'AppUserModelID fa sì che la finestra e il collegamento fissato sulla barra delle
applicazioni siano riconosciuti come la stessa app (stessa icona, nessun doppione).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

APP_ID = "Promemoria.Desktop.App"
APP_NAME = "Promemoria"
PROJECT_DIR = Path(__file__).resolve().parents[2]
MAIN_SCRIPT = PROJECT_DIR / "main.py"

log = logging.getLogger(__name__)


def set_process_app_id() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError) as exc:
        log.warning("Impossibile impostare l'AppUserModelID: %s", exc)


IS_FROZEN = bool(getattr(sys, "frozen", False))  # True se gira come Promemoria.exe


def pythonw_path() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def launch_target() -> tuple[str, str, str]:
    """(eseguibile, argomenti, cartella di lavoro) per avviare l'app."""
    if IS_FROZEN:
        exe = Path(sys.executable)
        return str(exe), "", str(exe.parent)
    return str(pythonw_path()), f'"{MAIN_SCRIPT}"', str(PROJECT_DIR)


def launch_command(background: bool = False) -> str:
    target, args, _ = launch_target()
    parts = [f'"{target}"', args, "--background" if background else ""]
    return " ".join(p for p in parts if p)


def shortcut_icon(default_icon: Path) -> str:
    # l'exe contiene già il logo; in sviluppo si usa il file .ico generato
    return str(sys.executable) if IS_FROZEN else str(default_icon)


def _special_folder(csidl_name: str) -> Path:
    from win32com.shell import shell, shellcon

    return Path(shell.SHGetFolderPath(0, getattr(shellcon, csidl_name), None, 0))


def start_menu_shortcut() -> Path:
    return _special_folder("CSIDL_PROGRAMS") / f"{APP_NAME}.lnk"


def desktop_shortcut() -> Path:
    return _special_folder("CSIDL_DESKTOPDIRECTORY") / f"{APP_NAME}.lnk"


def create_shortcut(lnk_path: Path, icon_path: Path) -> Path:
    """Crea un collegamento .lnk a main.py con icona e AppUserModelID."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    target, args, workdir = launch_target()
    link.SetPath(target)
    link.SetArguments(args)
    link.SetWorkingDirectory(workdir)
    link.SetIconLocation(shortcut_icon(icon_path), 0)
    link.SetDescription("Promemoria, calendario e sveglie")
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID,
                   propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(lnk_path), 0)
    return lnk_path


def ensure_start_menu_shortcut(icon_path: Path) -> Path | None:
    """Il collegamento nel menu Start serve a Windows per 'Aggiungi alla barra'."""
    if sys.platform != "win32":
        return None
    try:
        lnk = start_menu_shortcut()
        if not lnk.exists() or IS_FROZEN:
            # con l'exe lo ricreiamo sempre: se l'utente lo sposta, il collegamento segue
            create_shortcut(lnk, icon_path)
        return lnk
    except Exception as exc:  # noqa: BLE001 - non deve mai bloccare l'avvio
        log.warning("Collegamento nel menu Start non creato: %s", exc)
        return None
