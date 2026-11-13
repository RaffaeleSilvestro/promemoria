import smtplib
from dataclasses import replace
from datetime import datetime

import pytest
import requests

from promemoria.core import notify
from promemoria.core.models import Channels, Due, Reminder
from promemoria.core.settings import Settings

TOKEN = "123456:SEGRETO"
READY = Settings(smtp_user="me@example.com", smtp_password="pw", email_to="me@example.com",
                 tg_token=TOKEN, tg_chat_id="42")


def make_due(offset: int = 10, missed: bool = False, snoozed: bool = False) -> Due:
    r = Reminder("Dentista", datetime(2026, 11, 14, 15, 30), id=1, notes="Portare tessera",
                 priority=2, category="Salute", channels=Channels(True, False, True, True))
    return Due(r, r.start, offset, missed=missed, snoozed=snoozed)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_build_message_contains_details():
    subject, body = notify.build_message(make_due(missed=True))
    assert "Dentista" in subject and "sabato 14 novembre 2026 alle 15:30" in subject
    for part in ("10 minuti prima", "Priorità: Alta", "Categoria: Salute", "Portare tessera",
                 "PC era spento"):
        assert part in body


def test_build_message_snoozed():
    _, body = notify.build_message(make_due(snoozed=True))
    assert "posticipato" in body and "Preavviso" not in body


def test_send_telegram_ok(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return FakeResponse({"ok": True})

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send_telegram(READY, "ciao")
    assert calls[0][0].endswith("/sendMessage")
    assert calls[0][1] == {"chat_id": "42", "text": "ciao"}


def test_telegram_network_error_does_not_leak_token(monkeypatch):
    def boom(url, json, timeout):
        raise requests.ConnectionError(f"failed {url}")

    monkeypatch.setattr(notify.requests, "post", boom)
    with pytest.raises(notify.NotifyError) as err:
        notify.send_telegram(READY, "x")
    assert TOKEN not in str(err.value)
    assert err.value.__cause__ is None


def test_telegram_api_error_message(monkeypatch):
    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: FakeResponse(
        {"ok": False, "description": "chat not found"}))
    with pytest.raises(notify.NotifyError, match="chat not found"):
        notify.send_telegram(READY, "x")


def test_detect_chat_id(monkeypatch):
    payload = {"ok": True, "result": [{"message": {"chat": {"id": 7}}},
                                      {"message": {"chat": {"id": 99}}}]}
    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: FakeResponse(payload))
    assert notify.detect_telegram_chat_id(TOKEN) == "99"
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, json, timeout: FakeResponse({"ok": True, "result": []}))
    with pytest.raises(notify.NotifyError, match="/start"):
        notify.detect_telegram_chat_id(TOKEN)


def test_not_configured_raises():
    with pytest.raises(notify.NotifyError, match="non configurat"):
        notify.send_email(Settings(), "s", "b")
    with pytest.raises(notify.NotifyError, match="non configurat"):
        notify.send_telegram(Settings(), "t")


class FakeSMTP:
    sent: list = []
    fail_login = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def starttls(self, context=None) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad")

    def send_message(self, msg) -> None:
        FakeSMTP.sent.append(msg)


def test_send_email_ssl_and_starttls(monkeypatch):
    monkeypatch.setattr(FakeSMTP, "sent", [])
    monkeypatch.setattr(FakeSMTP, "fail_login", False)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    notify.send_email(READY, "Oggetto", "Corpo")
    notify.send_email(replace(READY, smtp_port=587), "Oggetto2", "Corpo")
    assert [m["Subject"] for m in FakeSMTP.sent] == ["Oggetto", "Oggetto2"]


def test_send_email_bad_credentials(monkeypatch):
    monkeypatch.setattr(FakeSMTP, "fail_login", True)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    with pytest.raises(notify.NotifyError, match="password per le app"):
        notify.send_email(READY, "s", "b")


def test_deliver_retries_then_reports(monkeypatch):
    attempts = {"email": 0, "tg": 0}

    def flaky_email(settings, subject, body):
        attempts["email"] += 1
        if attempts["email"] < 2:
            raise notify.NotifyError("Email: invio fallito (OSError)")

    def broken_tg(settings, text):
        attempts["tg"] += 1
        raise notify.NotifyError("Telegram: impossibile contattare il server (rete?)")

    monkeypatch.setattr(notify, "send_email", flaky_email)
    monkeypatch.setattr(notify, "send_telegram", broken_tg)
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    errors = notify.deliver(READY, make_due(), retries=(1, 1))
    assert attempts == {"email": 2, "tg": 3}
    assert len(errors) == 1 and "Telegram" in errors[0] and "Dentista" in errors[0]


def test_deliver_does_not_retry_when_not_configured(monkeypatch):
    monkeypatch.setattr(notify.time, "sleep", lambda s: pytest.fail("non deve aspettare"))
    errors = notify.deliver(Settings(), make_due(), retries=(5,))
    assert len(errors) == 2
