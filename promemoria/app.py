"""Avvio dell'applicazione: collega scheduler, notifiche, tray e finestre."""
from __future__ import annotations

import getpass
import logging
import sys
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta

from PySide6.QtCore import QLockFile, QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .core import autostart, engine, notify
from .core.winshell import ensure_start_menu_shortcut, set_process_app_id
from .core.db import Repository
from .core.models import Due
from .core.settings import Settings, SettingsStore, default_data_dir
from .ui import theme
from .ui.common import AlarmSound, app_icon
from .ui.gcal_sync import GCalSync
from .ui.main_window import MainWindow
from .ui.popup import ReminderPopup
from .ui.settings_dialog import SettingsDialog

TICK_MS = 10_000


class _DeliveryResult(QObject):
    errors = Signal(list)


class _DeliveryJob(QRunnable):
    def __init__(self, settings: Settings, due: Due) -> None:
        super().__init__()
        self._settings, self._due = settings, due
        self.result = _DeliveryResult()

    def run(self) -> None:
        try:
            errors = notify.deliver(self._settings, self._due)
        except Exception as exc:  # noqa: BLE001 - non perdere mai l'errore
            errors = [f"Errore imprevisto nell'invio: {type(exc).__name__}"]
        if errors:
            self.result.errors.emit(errors)


class Controller(QObject):
    def __init__(self, app: QApplication, background: bool) -> None:
        super().__init__()
        self.app = app
        data_dir = default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.repo = Repository(data_dir / "promemoria.db")
        self.store = SettingsStore(data_dir)
        self.settings = self.store.load()
        if self.settings.autostart:
            # ripristina la voce di avvio (es. se la cartella è stata spostata)
            try:
                autostart.set_autostart(True)
            except OSError as exc:
                logging.warning("Avvio automatico non impostato: %s", exc)
        theme.apply(app, self.settings.theme)
        try:
            app.styleHints().colorSchemeChanged.connect(lambda *_: self._apply_theme())
        except AttributeError:  # Qt < 6.5
            pass
        self._last_minute = None
        self.alarm = AlarmSound(self)
        self._popups: list[ReminderPopup] = []
        self._jobs: list[_DeliveryJob] = []

        self.window = MainWindow(self.repo, lambda: self.settings)
        self.window.settings_requested.connect(self.open_settings)
        self.window.quit_requested.connect(self.confirm_quit)
        self.window.data_changed.connect(self.tick)
        self._build_tray()
        self.gsync = GCalSync(self.repo, lambda: self.settings, self._save_settings,
                              self._gcal_error, self)
        self.window.data_changed.connect(self.gsync.schedule)
        self.gsync.schedule(5_000)  # prima sincronizzazione poco dopo l'avvio

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        self.tick()
        if not background:
            # con --background (avvio con Windows) resta nascosta: si apre dall'icona
            self.show_window()

    # ---- tray ---------------------------------------------------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Promemoria")
        menu = QMenu()
        for label, slot in (("Apri Promemoria", self.show_window),
                            ("Nuovo promemoria…", self.quick_add),
                            ("Impostazioni…", self.open_settings)):
            action = QAction(label, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("Esci (i promemoria non scatteranno)", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _on_tray(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self) -> None:
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def confirm_quit(self) -> None:
        answer = QMessageBox.question(
            self.window, "Uscire da Promemoria?",
            "Se esci, i promemoria non scatteranno finché non riapri l'app.\n\n"
            "Per tenerla attiva basta chiudere la finestra con la X:\n"
            "l'app resta in background e la riapri dall'icona sulla barra.")
        if answer == QMessageBox.StandardButton.Yes:
            self.quit()

    def quick_add(self) -> None:
        self.show_window()
        self.window.create()

    def _apply_theme(self) -> None:
        theme.apply(self.app, self.settings.theme)
        self.window.refresh()

    def quit(self) -> None:
        self.window.quitting = True
        self.tray.hide()
        self.app.quit()

    # ---- impostazioni ---------------------------------------------------
    def _save_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.store.save(settings)

    def _google_connected(self, credentials: str, calendar_id: str) -> None:
        """Salvato subito: vale anche se la finestra Impostazioni è già stata chiusa."""
        previous = self.settings.gcal_calendar_id
        self._save_settings(replace(self.settings, gcal_credentials=credentials,
                                    gcal_calendar_id=calendar_id, gcal_enabled=True))
        if previous != calendar_id:
            self.repo.clear_gcal()
        logging.info("Account Google collegato")
        self.tray.showMessage("Google Calendar", "Collegato: copio i promemoria nel calendario «Promemoria»…",
                              QSystemTrayIcon.MessageIcon.Information, 6000)
        self.gsync.schedule(500)

    def _gcal_error(self, message: str) -> None:
        self.tray.showMessage("Google Calendar", message,
                              QSystemTrayIcon.MessageIcon.Warning, 10000)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.window if self.window.isVisible() else None,
                                on_google_connected=self._google_connected)
        if dialog.exec() and dialog.result_settings:
            previous = self.settings
            self.settings = dialog.result_settings
            self.store.save(self.settings)
            if previous.gcal_calendar_id != self.settings.gcal_calendar_id:
                self.repo.clear_gcal()  # nuovo account/calendario: ricrea tutti gli eventi
            self.gsync.schedule(500)
            self._apply_theme()
            try:
                autostart.set_autostart(self.settings.autostart)
            except OSError as exc:
                QMessageBox.warning(None, "Avvio automatico", f"Impossibile aggiornare l'avvio automatico: {exc}")

    # ---- scheduler ---------------------------------------------------------
    def tick(self) -> None:
        now = datetime.now()
        lookback = timedelta(hours=self.settings.lookback_hours)
        fired = engine.due_notifications(self.repo, now, lookback)
        for due in fired:
            self._show(due)
        minute = now.replace(second=0, microsecond=0)
        if fired or minute != self._last_minute:
            # aggiorna badge "in ritardo" e contatori una volta al minuto
            self._last_minute = minute
            if self.window.isVisible():
                self.window.refresh()

    def _show(self, due: Due) -> None:
        ch = due.reminder.channels
        if ch.email or ch.telegram:
            if not due.snoozed:
                self._dispatch(due)
        if ch.popup or ch.sound or due.snoozed:
            self._popup(due, sound=ch.sound)
        else:
            self.tray.showMessage(due.reminder.title, due.occurrence.strftime("%d/%m %H:%M"),
                                  QSystemTrayIcon.MessageIcon.Information, 8000)

    def _dispatch(self, due: Due) -> None:
        job = _DeliveryJob(self.settings, due)
        job.result.errors.connect(self._on_delivery_errors)
        self._jobs.append(job)  # tiene vivo l'oggetto segnale finché il thread lavora
        QThreadPool.globalInstance().start(job)

    def _on_delivery_errors(self, errors: list) -> None:
        self.tray.showMessage("Invio notifica fallito", "\n".join(errors),
                              QSystemTrayIcon.MessageIcon.Warning, 15000)

    def _popup(self, due: Due, sound: bool) -> None:
        popup = ReminderPopup(due, self.settings.snooze_default, sound)
        popup.done.connect(self._on_done)
        popup.snoozed.connect(self._on_snooze)
        popup.closed.connect(lambda _d, p=popup: self._on_popup_closed(p))
        self._popups.append(popup)
        if sound:
            self.alarm.start()
        popup.show()
        popup.place(len(self._popups) - 1)
        popup.raise_()
        popup.activateWindow()

    def _on_popup_closed(self, popup: ReminderPopup) -> None:
        if popup.sound_on:
            self.alarm.stop()
        if popup in self._popups:
            self._popups.remove(popup)

    def _on_done(self, due: Due) -> None:
        item = next(
            (i for i in engine.agenda(self.repo, due.occurrence, due.occurrence)
             if i.reminder.id == due.reminder.id), None)
        if item is not None:
            engine.mark_done(self.repo, item)
            self.window.refresh()

    def _on_snooze(self, due: Due, minutes: int) -> None:
        engine.snooze(self.repo, due, minutes, datetime.now())


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    background = "--background" in argv
    _setup_logging()
    set_process_app_id()  # prima di creare finestre: icona corretta sulla barra
    app = QApplication([a for a in argv if a != "--background"])
    app.setApplicationName("Promemoria")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    app.setWindowIcon(app_icon())

    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir / "promemoria.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        # Già in esecuzione: chiediamo all'altra istanza di mostrare la finestra.
        if not _ask_running_instance_to_show():
            QMessageBox.information(None, "Promemoria", "Promemoria è già in esecuzione.")
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(_SERVER_NAME)
    server.listen(_SERVER_NAME)

    ensure_start_menu_shortcut(_ensure_ico())
    controller = Controller(app, background)
    server.newConnection.connect(lambda: _on_show_request(server, controller))
    code = app.exec()
    lock.unlock()
    return code


_SERVER_NAME = f"promemoria-{getpass.getuser()}"


def _setup_logging() -> None:
    """Log su file: con pythonw non c'è console, così gli errori non si perdono."""
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / "promemoria.log", maxBytes=512_000,
                                  backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    def log_unhandled(exc_type, exc, tb) -> None:
        # Un errore in un'azione non deve chiudere l'app: lo registriamo e basta.
        logging.error("Errore non gestito", exc_info=(exc_type, exc, tb))

    sys.excepthook = log_unhandled
    logging.info("Promemoria avviato")


def _ask_running_instance_to_show() -> bool:
    if sys.platform == "win32":
        import ctypes

        # Questo processo è stato avviato dal clic dell'utente, quindi può cedere
        # il primo piano all'istanza già aperta (altrimenti Windows lo blocca).
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    socket = QLocalSocket()
    socket.connectToServer(_SERVER_NAME)
    if not socket.waitForConnected(1500):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def _on_show_request(server: QLocalServer, controller: Controller) -> None:
    conn = server.nextPendingConnection()
    if conn is not None:
        conn.disconnected.connect(conn.deleteLater)
    controller.show_window()


def _ensure_ico():
    from .ui.logo import ICO_PATH, write_ico

    try:
        return ICO_PATH if ICO_PATH.exists() else write_ico()
    except OSError:
        return ICO_PATH
