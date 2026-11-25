"""Accesso OAuth a Google (app desktop, flusso con browser e server locale).

Le librerie Google si importano solo quando servono: l'app funziona anche senza.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/calendar.app.created"]
CLIENT_FILE_NAME = "google_client.json"
LOGIN_TIMEOUT_S = 300
EXPIRED_MESSAGE = ("Accesso a Google scaduto o revocato. Vai in Impostazioni → Google Calendar → "
                   "Ricollega account Google. Se ricapita ogni 7 giorni, il progetto Google è "
                   "ancora «in test»: pubblicalo prima di ricollegare.")


class GAuthError(Exception):
    """Errore leggibile dall'utente."""


def client_file(data_dir: Path) -> Path:
    return data_dir / CLIENT_FILE_NAME


def validate_client_file(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GAuthError("Impossibile leggere il file: è il JSON scaricato da Google Cloud?") from exc
    if "installed" not in data:
        raise GAuthError("File non valido: crea un client OAuth di tipo «App desktop» "
                         "(non «Applicazione web») e scarica il suo JSON")
    if not data["installed"].get("client_id"):
        raise GAuthError("File non valido: manca il client_id")


def import_client_file(source: Path, data_dir: Path) -> Path:
    validate_client_file(source)
    target = client_file(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def login(client_path: Path) -> str:
    """Apre il browser per l'accesso Google. Ritorna le credenziali in JSON.

    Bloccante (fino a LOGIN_TIMEOUT_S): da eseguire in un thread di lavoro.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    validate_client_file(client_path)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    try:
        creds = flow.run_local_server(
            port=0, open_browser=True, timeout_seconds=LOGIN_TIMEOUT_S,
            authorization_prompt_message="",
            success_message="Promemoria è collegato a Google Calendar. Puoi chiudere questa scheda.")
    except Exception as exc:  # noqa: BLE001 - qualunque errore del flusso va spiegato
        raise GAuthError("Accesso a Google non completato (annullato o scaduto)") from exc
    if not creds or not creds.refresh_token:
        raise GAuthError("Google non ha concesso un accesso permanente: riprova il collegamento")
    return creds.to_json()


def session(credentials_json: str):
    """Sessione HTTP autenticata (rinnova da sola il token di accesso)."""
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials

    class ReadableSession(AuthorizedSession):
        """Traduce gli errori di rinnovo del token in errori gestiti dall'app."""

        def request(self, *args, **kwargs):
            try:
                return super().request(*args, **kwargs)
            except RefreshError as exc:
                if exc.retryable:
                    raise ConnectionError("Rinnovo dell'accesso a Google non riuscito") from exc
                raise GAuthError(EXPIRED_MESSAGE) from exc
            except TransportError as exc:
                raise ConnectionError("Google non raggiungibile") from exc

    try:
        info = json.loads(credentials_json)
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    except (ValueError, KeyError) as exc:
        raise GAuthError("Credenziali Google non valide: ricollega l'account") from exc
    return ReadableSession(creds)
