"""Persistenza SQLite. Da usare solo dal thread principale."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .models import Channels, Recurrence, Reminder

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    start TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 1,
    category TEXT NOT NULL DEFAULT '',
    freq TEXT NOT NULL DEFAULT 'none',
    interval INTEGER NOT NULL DEFAULT 1,
    weekdays TEXT NOT NULL DEFAULT '[]',
    until TEXT,
    alerts TEXT NOT NULL DEFAULT '[0]',
    ch_popup INTEGER NOT NULL DEFAULT 1,
    ch_sound INTEGER NOT NULL DEFAULT 0,
    ch_email INTEGER NOT NULL DEFAULT 0,
    ch_telegram INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    armed_from TEXT
);
CREATE TABLE IF NOT EXISTS fired (
    reminder_id INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    occurrence TEXT NOT NULL,
    offset_min INTEGER NOT NULL,
    PRIMARY KEY (reminder_id, occurrence, offset_min)
);
CREATE TABLE IF NOT EXISTS done (
    reminder_id INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    occurrence TEXT NOT NULL,
    PRIMARY KEY (reminder_id, occurrence)
);
CREATE TABLE IF NOT EXISTS gcal_map (
    reminder_id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snoozes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    occurrence TEXT NOT NULL,
    fire_at TEXT NOT NULL
);
"""

KEY_FMT = "%Y-%m-%dT%H:%M"


def key(dt: datetime) -> str:
    """Chiave testuale di un'occorrenza (precisione al minuto)."""
    return dt.strftime(KEY_FMT)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


class Repository:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- promemoria -------------------------------------------------
    @staticmethod
    def _from_row(row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=row["id"],
            title=row["title"],
            notes=row["notes"],
            start=datetime.fromisoformat(row["start"]),
            priority=row["priority"],
            category=row["category"],
            recurrence=Recurrence(
                freq=row["freq"],
                interval=row["interval"],
                weekdays=tuple(json.loads(row["weekdays"])),
                until=_parse(row["until"]),
            ),
            alerts=tuple(json.loads(row["alerts"])),
            channels=Channels(
                popup=bool(row["ch_popup"]),
                sound=bool(row["ch_sound"]),
                email=bool(row["ch_email"]),
                telegram=bool(row["ch_telegram"]),
            ),
            completed=bool(row["completed"]),
            armed_from=_parse(row["armed_from"]),
        )

    @staticmethod
    def _params(r: Reminder) -> tuple:
        return (
            r.title.strip(), r.notes, _iso(r.start), r.priority, r.category.strip(),
            r.recurrence.freq, r.recurrence.interval,
            json.dumps(sorted(r.recurrence.weekdays)), _iso(r.recurrence.until),
            json.dumps(sorted(set(r.alerts))),
            int(r.channels.popup), int(r.channels.sound),
            int(r.channels.email), int(r.channels.telegram),
            int(r.completed), _iso(r.armed_from),
        )

    _COLS = (
        "title, notes, start, priority, category, freq, interval, weekdays, until,"
        " alerts, ch_popup, ch_sound, ch_email, ch_telegram, completed, armed_from"
    )

    def add(self, reminder: Reminder, now: datetime | None = None) -> Reminder:
        armed = replace(reminder, armed_from=now or datetime.now())
        cur = self._conn.execute(
            f"INSERT INTO reminders ({self._COLS}) VALUES ({','.join('?' * 16)})",
            self._params(armed),
        )
        self._conn.commit()
        return replace(armed, id=cur.lastrowid)

    def get(self, reminder_id: int) -> Reminder | None:
        row = self._conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[Reminder]:
        rows = self._conn.execute("SELECT * FROM reminders ORDER BY start").fetchall()
        return [self._from_row(r) for r in rows]

    def update(self, reminder: Reminder, now: datetime | None = None) -> Reminder:
        if reminder.id is None:
            raise ValueError("Impossibile aggiornare un promemoria senza id")
        old = self.get(reminder.id)
        if old is None:
            raise KeyError(reminder.id)
        armed = replace(reminder, armed_from=now or datetime.now())
        sets = ", ".join(f"{c.strip()} = ?" for c in self._COLS.split(","))
        with self._conn:
            self._conn.execute(
                f"UPDATE reminders SET {sets} WHERE id = ?",
                (*self._params(armed), reminder.id),
            )
            self._conn.execute("DELETE FROM snoozes WHERE reminder_id = ?", (reminder.id,))
            # Le occorrenze già gestite restano valide solo se il calendario non è cambiato.
            if old.start != reminder.start or old.recurrence != reminder.recurrence:
                self._conn.execute("DELETE FROM done WHERE reminder_id = ?", (reminder.id,))
                self._conn.execute("DELETE FROM fired WHERE reminder_id = ?", (reminder.id,))
        return armed

    def delete(self, reminder_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def set_completed(self, reminder_id: int, completed: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE reminders SET completed = ? WHERE id = ?", (int(completed), reminder_id)
            )

    # ---- categorie ----------------------------------------------------
    def ids_in_category(self, category: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT id FROM reminders WHERE category = ?", (category,)).fetchall()
        return [r[0] for r in rows]

    def set_category(self, reminder_ids: list[int], category: str) -> int:
        """Cambia solo la categoria (gli avvisi non vengono riarmati). Ritorna quanti."""
        if not reminder_ids:
            return 0
        marks = ",".join("?" * len(reminder_ids))
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE reminders SET category = ? WHERE id IN ({marks})",
                (category.strip(), *reminder_ids))
        return cur.rowcount

    # ---- avvisi già inviati ----------------------------------------
    def mark_fired(self, reminder_id: int, occurrence: datetime, offset_min: int) -> bool:
        """True se l'avviso è nuovo (e viene registrato), False se già inviato."""
        with self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO fired VALUES (?, ?, ?)",
                (reminder_id, key(occurrence), offset_min),
            )
        return cur.rowcount == 1

    # ---- occorrenze completate -------------------------------------
    def set_done(self, reminder_id: int, occurrence: datetime, done: bool = True) -> None:
        with self._conn:
            if done:
                self._conn.execute(
                    "INSERT OR IGNORE INTO done VALUES (?, ?)", (reminder_id, key(occurrence))
                )
            else:
                self._conn.execute(
                    "DELETE FROM done WHERE reminder_id = ? AND occurrence = ?",
                    (reminder_id, key(occurrence)),
                )

    def done_set(self) -> set[tuple[int, str]]:
        rows = self._conn.execute("SELECT reminder_id, occurrence FROM done").fetchall()
        return {(r[0], r[1]) for r in rows}

    # ---- posticipi ---------------------------------------------------
    def add_snooze(self, reminder_id: int, occurrence: datetime, fire_at: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO snoozes (reminder_id, occurrence, fire_at) VALUES (?, ?, ?)",
                (reminder_id, key(occurrence), _iso(fire_at)),
            )

    def pop_due_snoozes(self, now: datetime) -> list[tuple[int, datetime]]:
        rows = self._conn.execute(
            "SELECT id, reminder_id, occurrence FROM snoozes WHERE fire_at <= ?", (_iso(now),)
        ).fetchall()
        with self._conn:
            for row in rows:
                self._conn.execute("DELETE FROM snoozes WHERE id = ?", (row["id"],))
        return [(r["reminder_id"], datetime.strptime(r["occurrence"], KEY_FMT)) for r in rows]

    # ---- Google Calendar ------------------------------------------------------
    # Nessuna FOREIGN KEY: se un promemoria viene eliminato, la riga resta finché
    # la sincronizzazione non cancella anche l'evento su Google.
    def gcal_map(self) -> dict[int, tuple[str, str]]:
        rows = self._conn.execute("SELECT reminder_id, event_id, hash FROM gcal_map").fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    def set_gcal(self, reminder_id: int, event_id: str, event_hash: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO gcal_map VALUES (?, ?, ?)",
                (reminder_id, event_id, event_hash))

    def delete_gcal(self, reminder_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM gcal_map WHERE reminder_id = ?", (reminder_id,))

    def clear_gcal(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM gcal_map")
