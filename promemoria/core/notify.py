"""Invio di notifiche via email (SMTP) e Telegram."""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage

import requests

from .formatting import PRIORITIES, format_offset, format_when
from .models import Due
from .settings import Settings

TG_API = "https://api.telegram.org"


class NotifyError(Exception):
    """Errore di invio con messaggio leggibile (mai con credenziali)."""


def build_message(due: Due) -> tuple[str, str]:
    r = due.reminder
    subject = f"⏰ {r.title} — {format_when(due.occurrence)}"
    lines = [f"⏰ {r.title}", f"Quando: {format_when(due.occurrence)}"]
    if due.offset_min and not due.snoozed:
        lines.append(f"Preavviso: {format_offset(due.offset_min)}")
    if due.snoozed:
        lines.append("(promemoria posticipato)")
    if r.priority == 2:
        lines.append(f"Priorità: {PRIORITIES[r.priority]} ❗")
    if r.category:
        lines.append(f"Categoria: {r.category}")
    if r.notes.strip():
        lines.append("")
        lines.append(r.notes.strip())
    if due.missed:
        lines.append("")
        lines.append("⚠️ Avviso scattato mentre il PC era spento o l'app chiusa.")
    return subject, "\n".join(lines)


def send_email(settings: Settings, subject: str, body: str) -> None:
    if not settings.email_ready:
        raise NotifyError("Email non configurata nelle Impostazioni")
    msg = EmailMessage()
    msg["From"] = settings.smtp_user
    msg["To"] = settings.email_to
    msg["Subject"] = subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                      timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with server:
            if settings.smtp_port != 465:
                server.starttls(context=ctx)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise NotifyError("Email: credenziali rifiutate (usa una password per le app)") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"Email: invio fallito ({type(exc).__name__})") from exc


def _tg_call(token: str, method: str, payload: dict) -> dict:
    try:
        resp = requests.post(f"{TG_API}/bot{token}/{method}", json=payload, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError):
        # Non propaghiamo l'eccezione originale: contiene l'URL col token.
        raise NotifyError("Telegram: impossibile contattare il server (rete?)") from None
    if not data.get("ok"):
        raise NotifyError(f"Telegram: {data.get('description', 'errore sconosciuto')}")
    return data


def send_telegram(settings: Settings, text: str) -> None:
    if not settings.telegram_ready:
        raise NotifyError("Telegram non configurato nelle Impostazioni")
    _tg_call(settings.tg_token, "sendMessage",
             {"chat_id": settings.tg_chat_id, "text": text})


def detect_telegram_chat_id(token: str) -> str:
    """Restituisce l'ID della chat dell'ultimo messaggio ricevuto dal bot."""
    data = _tg_call(token, "getUpdates", {"timeout": 0})
    for update in reversed(data.get("result", [])):
        message = update.get("message") or update.get("edited_message")
        if message:
            return str(message["chat"]["id"])
    raise NotifyError("Nessun messaggio trovato: scrivi /start al tuo bot e riprova")


def deliver(settings: Settings, due: Due, retries: tuple[int, ...] = (5, 30)) -> list[str]:
    """Invia sui canali richiesti dal promemoria. Ritorna gli errori finali.

    Da eseguire in un thread di lavoro: può bloccarsi per i tentativi di retry.
    """
    subject, body = build_message(due)
    channels = due.reminder.channels
    senders = []
    if channels.email:
        senders.append(("Email", lambda: send_email(settings, subject, body)))
    if channels.telegram:
        senders.append(("Telegram", lambda: send_telegram(settings, body)))

    errors: list[str] = []
    for _name, send in senders:
        error = None
        for delay in (0, *retries):
            if delay:
                time.sleep(delay)
            try:
                send()
                error = None
                break
            except NotifyError as exc:
                error = str(exc)
                if "non configurat" in error or "credenziali" in error:
                    break  # inutile riprovare
        if error:
            errors.append(f"{error} — «{due.reminder.title}»")
    return errors
