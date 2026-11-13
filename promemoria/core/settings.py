"""Impostazioni utente salvate in JSON (i segreti sono cifrati con DPAPI)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import secrets

SECRET_FIELDS = ("smtp_password", "tg_token")


def default_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Promemoria"


@dataclass(frozen=True)
class Settings:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    email_to: str = ""
    tg_token: str = ""
    tg_chat_id: str = ""
    autostart: bool = True
    snooze_default: int = 10
    lookback_hours: int = 24
    categories: tuple[str, ...] = ("Personale", "Lavoro", "Salute", "Casa")
    theme: str = "auto"  # auto | light | dark
    default_sound: bool = False
    default_email: bool = False
    default_telegram: bool = False

    @property
    def email_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.email_to)

    @property
    def telegram_ready(self) -> bool:
        return bool(self.tg_token and self.tg_chat_id)


class SettingsStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "settings.json"

    def load(self) -> Settings:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, json.JSONDecodeError):
            return Settings()
        known = {f.name for f in fields(Settings)}
        data = {k: v for k, v in raw.items() if k in known}
        for name in SECRET_FIELDS:
            if name in data:
                try:
                    data[name] = secrets.unprotect(data[name])
                except (OSError, ValueError):
                    data[name] = ""
        if "categories" in data:
            data["categories"] = tuple(data["categories"])
        return Settings(**data)

    def save(self, settings: Settings) -> None:
        data = asdict(settings)
        for name in SECRET_FIELDS:
            data[name] = secrets.protect(data[name])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
