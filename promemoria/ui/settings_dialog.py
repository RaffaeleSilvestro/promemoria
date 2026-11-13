"""Impostazioni: email, Telegram, avvio automatico."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..core import notify
from ..core.settings import Settings
from .google_tab import GoogleTab


class _Result(QObject):
    finished = Signal(str, str)  # (messaggio, errore)


class _Job(QRunnable):
    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn
        self.result = _Result()

    def run(self) -> None:
        try:
            self.result.finished.emit(self._fn(), "")
        except notify.NotifyError as exc:
            self.result.finished.emit("", str(exc))
        except Exception as exc:  # noqa: BLE001 - mostriamo qualunque errore all'utente
            self.result.finished.emit("", f"Errore imprevisto: {type(exc).__name__}")


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impostazioni")
        self.setMinimumWidth(520)
        self._settings = settings
        self._jobs: list[_Job] = []
        self.result_settings: Settings | None = None

        tabs = QTabWidget()
        tabs.addTab(self._email_tab(settings), "Email")
        tabs.addTab(self._telegram_tab(settings), "Telegram")
        tabs.addTab(self._general_tab(settings), "Generali")
        self.google_tab = GoogleTab(settings)
        tabs.addTab(self.google_tab, "Google Calendar")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salva")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.status = QLabel("")
        self.google_tab.status.connect(self.status.setText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

    # ---- schede --------------------------------------------------------
    def _email_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.smtp_host = QLineEdit(s.smtp_host)
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(s.smtp_port)
        self.smtp_user = QLineEdit(s.smtp_user)
        self.smtp_password = QLineEdit(s.smtp_password)
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.email_to = QLineEdit(s.email_to)
        hint = QLabel(
            "Per Gmail serve una <b>password per le app</b> (non la password normale): "
            "Account Google → Sicurezza → Verifica in due passaggi → Password per le app."
        )
        hint.setWordWrap(True)
        test = QPushButton("Invia email di prova")
        test.clicked.connect(self._test_email)
        form.addRow(hint)
        form.addRow("Server SMTP", self.smtp_host)
        form.addRow("Porta", self.smtp_port)
        form.addRow("Utente (mittente)", self.smtp_user)
        form.addRow("Password per le app", self.smtp_password)
        form.addRow("Invia a", self.email_to)
        form.addRow(test)
        return w

    def _telegram_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        guide = QLabel(
            "<b>Come creare il bot (2 minuti):</b><br>"
            "1. Su Telegram cerca <b>@BotFather</b> e scrivi <code>/newbot</code>.<br>"
            "2. Scegli nome e username; BotFather ti dà il <b>token</b>: incollalo qui sotto.<br>"
            "3. Apri il tuo nuovo bot e premi <b>Avvia</b> / scrivi <code>/start</code>.<br>"
            "4. Torna qui e premi <b>Rileva chat ID</b>."
        )
        guide.setWordWrap(True)
        self.tg_token = QLineEdit(s.tg_token)
        self.tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.tg_chat = QLineEdit(s.tg_chat_id)
        detect = QPushButton("Rileva chat ID")
        detect.clicked.connect(self._detect_chat)
        test = QPushButton("Invia messaggio di prova")
        test.clicked.connect(self._test_telegram)
        form.addRow(guide)
        form.addRow("Token del bot", self.tg_token)
        form.addRow("Chat ID", self.tg_chat)
        form.addRow(detect)
        form.addRow(test)
        return w

    def _general_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.autostart = QCheckBox("Avvia Promemoria all'accesso a Windows (in background)")
        self.autostart.setChecked(s.autostart)
        self.snooze = QComboBox()
        for minutes in (5, 10, 15, 30, 60):
            self.snooze.addItem(f"{minutes} minuti", minutes)
        idx = self.snooze.findData(s.snooze_default)
        self.snooze.setCurrentIndex(idx if idx >= 0 else 1)
        self.lookback = QSpinBox()
        self.lookback.setRange(1, 168)
        self.lookback.setValue(s.lookback_hours)
        self.lookback.setSuffix(" ore")
        self.categories = QLineEdit(", ".join(s.categories))
        self.theme = QComboBox()
        for value, label in (("auto", "Automatico (come Windows)"), ("light", "Chiaro"),
                             ("dark", "Scuro")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        self.def_sound = QCheckBox("🔔 Sveglia sonora")
        self.def_sound.setChecked(s.default_sound)
        self.def_email = QCheckBox("✉️ Email")
        self.def_email.setChecked(s.default_email)
        self.def_tg = QCheckBox("✈️ Telegram")
        self.def_tg.setChecked(s.default_telegram)
        channels = QHBoxLayout()
        for cb in (self.def_sound, self.def_email, self.def_tg):
            channels.addWidget(cb)
        channels.addStretch()
        form.addRow("Tema", self.theme)
        form.addRow(self.autostart)
        form.addRow("Posticipo predefinito", self.snooze)
        form.addRow("Recupera avvisi persi fino a", self.lookback)
        form.addRow("Categorie (separate da virgola)", self.categories)
        form.addRow("Nuovi promemoria avvisano anche con", channels)
        return w

    # ---- azioni -----------------------------------------------------------
    def _current(self) -> Settings:
        cats = tuple(c.strip() for c in self.categories.text().split(",") if c.strip())
        updated = replace(
            self._settings,
            smtp_host=self.smtp_host.text().strip(), smtp_port=self.smtp_port.value(),
            smtp_user=self.smtp_user.text().strip(),
            smtp_password=self.smtp_password.text().strip().replace(" ", ""),
            email_to=self.email_to.text().strip(),
            tg_token=self.tg_token.text().strip(), tg_chat_id=self.tg_chat.text().strip(),
            autostart=self.autostart.isChecked(),
            snooze_default=int(self.snooze.currentData()),
            lookback_hours=self.lookback.value(), categories=cats,
            theme=str(self.theme.currentData()),
            default_sound=self.def_sound.isChecked(),
            default_email=self.def_email.isChecked(),
            default_telegram=self.def_tg.isChecked(),
        )
        return self.google_tab.apply(updated)

    def _run(self, fn, on_ok=None) -> None:
        self.status.setText("Operazione in corso…")
        job = _Job(fn)
        self._jobs.append(job)

        def finished(message: str, error: str) -> None:
            self.status.setText(f"❌ {error}" if error else f"✅ {message}")
            if not error and on_ok:
                on_ok(message)

        job.result.finished.connect(finished)
        QThreadPool.globalInstance().start(job)

    def _test_email(self) -> None:
        s = self._current()

        def work() -> str:
            notify.send_email(s, "Promemoria: email di prova", "Se leggi questo, le email funzionano.")
            return f"Email inviata a {s.email_to}"

        self._run(work)

    def _test_telegram(self) -> None:
        s = self._current()

        def work() -> str:
            notify.send_telegram(s, "✅ Promemoria: messaggio di prova")
            return "Messaggio Telegram inviato"

        self._run(work)

    def _detect_chat(self) -> None:
        token = self.tg_token.text().strip()
        if not token:
            self.status.setText("❌ Inserisci prima il token del bot")
            return
        self._run(lambda: notify.detect_telegram_chat_id(token),
                  on_ok=lambda chat_id: self.tg_chat.setText(chat_id))

    def _on_accept(self) -> None:
        s = self._current()
        if s.smtp_user and s.email_to and "@" not in s.email_to:
            QMessageBox.warning(self, "Email non valida", "Controlla l'indirizzo di destinazione.")
            return
        self.result_settings = s
        self.accept()
