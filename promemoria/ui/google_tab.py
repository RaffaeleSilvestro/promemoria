"""Scheda Impostazioni → Google Calendar: credenziali, collegamento account, opzioni."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimeZone, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from ..core import gauth, gcal
from ..core.settings import Settings, default_data_dir
from .worker import run_in_thread

GUIDE = (
    "<b>Avvisi sul telefono anche a PC spento.</b> Ogni promemoria diventa un evento nel "
    "calendario «Promemoria» del tuo Google Calendar.<br><br>"
    "<b>Configurazione (una volta sola, ~10 minuti):</b><br>"
    "1. Apri <a href='https://console.cloud.google.com/projectcreate'>Google Cloud</a> e crea un "
    "progetto (es. «Promemoria»).<br>"
    "2. <a href='https://console.cloud.google.com/apis/library/calendar-json.googleapis.com'>"
    "Abilita Google Calendar API</a>.<br>"
    "3. <a href='https://console.cloud.google.com/auth/overview'>Google Auth Platform</a>: "
    "configura con tipo <b>Esterno</b>, poi in <i>Pubblico</i> premi <b>Pubblica app</b> "
    "(altrimenti l'accesso scade ogni 7 giorni).<br>"
    "4. <a href='https://console.cloud.google.com/auth/clients'>Client</a> → Crea client → "
    "tipo <b>App desktop</b> → scarica il file JSON.<br>"
    "5. Qui sotto: <b>Scegli file credenziali</b>, poi <b>Collega account Google</b>.<br>"
    "<span style='color:gray'>Al collegamento Google può mostrare «app non verificata»: è la tua "
    "app, scegli Avanzate → Vai a Promemoria. L'app vede solo il calendario che crea lei.</span>"
)


def system_timezone() -> str:
    return bytes(QTimeZone.systemTimeZoneId()).decode() or "UTC"


class GoogleTab(QWidget):
    status = Signal(str)  # messaggi per la barra di stato del dialog

    def __init__(self, settings: Settings, data_dir: Path | None = None) -> None:
        super().__init__()
        self._data_dir = data_dir or default_data_dir()
        self._credentials = settings.gcal_credentials
        self._calendar_id = settings.gcal_calendar_id
        self._busy = False

        guide = QLabel(GUIDE)
        guide.setWordWrap(True)
        guide.setOpenExternalLinks(True)
        self.client_label = QLabel()
        self.account_label = QLabel()
        self.account_label.setWordWrap(True)
        choose = QPushButton("Scegli file credenziali…")
        choose.clicked.connect(self._choose_client_file)
        self.connect_btn = QPushButton("Collega account Google")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn = QPushButton("Scollega")
        self.disconnect_btn.setObjectName("Ghost")
        self.disconnect_btn.clicked.connect(self._disconnect)
        buttons = QHBoxLayout()
        for b in (choose, self.connect_btn, self.disconnect_btn):
            buttons.addWidget(b)
        buttons.addStretch()

        self.enabled = QCheckBox("Sincronizza i promemoria con Google Calendar")
        self.enabled.setChecked(settings.gcal_enabled)
        self.email = QCheckBox("Per i promemoria con ✉️ Email, fai inviare l'email anche da Google")
        self.email.setChecked(settings.gcal_email)

        form = QFormLayout(self)
        form.addRow(guide)
        form.addRow("File credenziali", self.client_label)
        form.addRow("Account", self.account_label)
        form.addRow(buttons)
        form.addRow(self.enabled)
        form.addRow(self.email)
        self._refresh()

    # ---- stato ---------------------------------------------------------------
    def _client_path(self) -> Path:
        return gauth.client_file(self._data_dir)

    def _refresh(self) -> None:
        has_client = self._client_path().exists()
        connected = bool(self._credentials and self._calendar_id)
        self.client_label.setText("✅ caricato" if has_client else "— non ancora caricato")
        self.account_label.setText(
            "✅ collegato · calendario «Promemoria» pronto" if connected else "— non collegato")
        self.connect_btn.setEnabled(has_client and not self._busy)
        self.connect_btn.setText("Ricollega account Google" if connected else "Collega account Google")
        self.disconnect_btn.setVisible(connected)
        self.enabled.setEnabled(connected)
        self.email.setEnabled(connected)

    def apply(self, settings: Settings) -> Settings:
        connected = bool(self._credentials and self._calendar_id)
        return replace(settings, gcal_credentials=self._credentials,
                       gcal_calendar_id=self._calendar_id,
                       gcal_enabled=self.enabled.isChecked() and connected,
                       gcal_email=self.email.isChecked())

    # ---- azioni --------------------------------------------------------------
    def _choose_client_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "File credenziali Google (JSON)", str(Path.home() / "Downloads"), "JSON (*.json)")
        if not path:
            return
        try:
            gauth.import_client_file(Path(path), self._data_dir)
        except (gauth.GAuthError, OSError) as exc:
            self.status.emit(f"❌ {exc}")
            return
        self.status.emit("✅ File credenziali caricato: ora premi «Collega account Google»")
        self._refresh()

    def _connect(self) -> None:
        client, tz, previous_calendar = self._client_path(), system_timezone(), self._calendar_id

        def work() -> tuple[str, str]:
            credentials = gauth.login(client)
            calendar_id = gcal.ensure_calendar(gauth.session(credentials), previous_calendar, tz)
            return credentials, calendar_id

        self._busy = True
        self._refresh()
        self.status.emit("Si è aperto il browser: accedi con Google e consenti l'accesso…")
        run_in_thread(work, self._on_connected)

    def _on_connected(self, result, error: str) -> None:
        self._busy = False
        if error:
            self.status.emit(f"❌ {error}")
        else:
            self._credentials, self._calendar_id = result
            self.enabled.setChecked(True)
            self.status.emit("✅ Collegato! Premi Salva: i promemoria verranno copiati su Google Calendar")
        self._refresh()

    def _disconnect(self) -> None:
        self._credentials = ""
        self._calendar_id = ""
        self.enabled.setChecked(False)
        self.status.emit("Account scollegato (il calendario su Google resta: puoi eliminarlo da lì)")
        self._refresh()
