"""Finestra principale: barra laterale, inserimento rapido, agenda e calendario."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from itertools import groupby
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core import engine
from ..core.formatting import (
    MONTHS, day_label, format_day, format_recurrence, format_relative,
)
from ..core.models import AgendaItem, Channels, Reminder
from ..core.quickparse import parse
from ..core.settings import Settings
from . import theme
from .calendar_page import CalendarPage
from .cards import CardList, EmptyState, Group
from .common import app_icon
from .event_dialog import EventDialog
from .sidebar import VIEWS, Sidebar
from .toast import Toast

QUICK_HINT = "Scrivi in italiano: «Dentista domani alle 15:30», «Palestra ogni lunedì alle 18», «Chiama Luca tra 2 ore»"


def default_channels(s: Settings) -> Channels:
    return Channels(popup=True, sound=s.default_sound, email=s.default_email,
                    telegram=s.default_telegram)


def _next_only(items: list[AgendaItem]) -> list[AgendaItem]:
    """Per i promemoria ricorrenti tiene solo la prossima occorrenza."""
    seen: set[int] = set()
    result = []
    for item in sorted(items, key=lambda i: i.occurrence):
        if item.reminder.is_recurring:
            if item.reminder.id in seen:
                continue
            seen.add(item.reminder.id)
        result.append(item)
    return result


def _by_day(items: list[AgendaItem], today: date, reverse: bool = False) -> list[Group]:
    ordered = sorted(items, key=lambda i: i.occurrence, reverse=reverse)
    return [Group(day_label(d, today), tuple(group))
            for d, group in groupby(ordered, key=lambda i: i.occurrence.date())]


class MainWindow(QMainWindow):
    data_changed = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, repo, get_settings: Callable[[], Settings]) -> None:
        super().__init__()
        self._repo = repo
        self._get_settings = get_settings
        self.quitting = False
        self.view = "today"
        self.setWindowTitle("Promemoria")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(980, 640)
        self.resize(1200, 780)

        self.sidebar = Sidebar()
        self.sidebar.selected.connect(self.set_view)
        self.sidebar.new_requested.connect(lambda: self.create())
        self.sidebar.settings_requested.connect(self.settings_requested.emit)
        self.sidebar.quit_requested.connect(self.quit_requested.emit)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("🔍  Cerca  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _: self.refresh())
        header = QHBoxLayout()
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(self.search, 0, Qt.AlignmentFlag.AlignTop)

        self.quick = QLineEdit()
        self.quick.setObjectName("QuickAdd")
        self.quick.setPlaceholderText("＋  Aggiungi un promemoria e premi Invio…   (Ctrl+L)")
        self.quick.textChanged.connect(self._quick_preview)
        self.quick.returnPressed.connect(self._quick_submit)
        self.quick_hint = QLabel(QUICK_HINT)
        self.quick_hint.setObjectName("Hint")

        self.agenda = CardList()
        self.calendar_page = CalendarPage()
        cal = self.calendar_page.calendar
        cal.selectionChanged.connect(self._refresh_calendar_day)
        cal.currentPageChanged.connect(lambda *_: self._refresh_calendar())
        self.calendar_page.add_requested.connect(lambda d: self.create(day=d))
        for cards in (self.agenda, self.calendar_page.cards):
            cards.toggled.connect(self.toggle_done)
            cards.edit.connect(self.edit)
            cards.delete.connect(self.delete)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.agenda)
        self.stack.addWidget(self.calendar_page)

        content = QVBoxLayout()
        content.setContentsMargins(32, 26, 32, 18)
        content.setSpacing(10)
        content.addLayout(header)
        content.addSpacing(8)
        content.addWidget(self.quick)
        content.addWidget(self.quick_hint)
        content.addSpacing(6)
        content.addWidget(self.stack, 1)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addLayout(content, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)
        self._install_shortcuts()
        self.sidebar.select("today")
        self.refresh()

    # ---- scorciatoie ---------------------------------------------------------
    def _install_shortcuts(self) -> None:
        bindings = [
            ("Ctrl+N", lambda: self.create()),
            ("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
            ("Ctrl+L", self.quick.setFocus),
            ("Ctrl+,", self.settings_requested.emit),
        ]
        for i, (key, *_rest) in enumerate(VIEWS, start=1):
            bindings.append((f"Ctrl+{i}", lambda k=key: (self.sidebar.select(k), self.set_view(k))))
        for seq, slot in bindings:
            QShortcut(QKeySequence(seq), self, activated=slot)

    # ---- navigazione -----------------------------------------------------------
    def set_view(self, key: str) -> None:
        self.view = key
        self.refresh()

    def _matches(self, item: AgendaItem) -> bool:
        text = self.search.text().strip().lower()
        r = item.reminder
        return not text or any(text in s.lower() for s in (r.title, r.notes, r.category))

    def _filter(self, items: list[AgendaItem]) -> list[AgendaItem]:
        return [i for i in items if self._matches(i)]

    def refresh(self) -> None:
        now = datetime.now()
        day_start = datetime.combine(now.date(), time.min)
        day_end = datetime.combine(now.date(), time.max)
        today_pending = [i for i in engine.agenda(self._repo, day_start, day_end) if not i.done]
        late_before_today = engine.overdue(self._repo, day_start)
        overdue = engine.overdue(self._repo, now)
        upcoming = engine.agenda(self._repo, now, now + timedelta(days=90))
        self.sidebar.set_counts({
            "today": (len(today_pending) + len(late_before_today), False),
            "overdue": (len(overdue), True),
        })
        categories = sorted({r.category for r in self._repo.list() if r.category},
                            key=str.lower)
        pending_ids: dict[str, set[int]] = {}
        for item in upcoming:
            if not item.done and item.reminder.category:
                pending_ids.setdefault(item.reminder.category, set()).add(item.reminder.id)
        cat_counts = {cat: len(ids) for cat, ids in pending_ids.items()}
        self.sidebar.set_categories(categories, cat_counts)
        if self.view.startswith("cat:") and self.view[4:] not in categories:
            self.view = "today"
            self.sidebar.select("today")

        if self.view == "calendar":
            self.stack.setCurrentWidget(self.calendar_page)
            self._refresh_calendar()
            return
        self.stack.setCurrentWidget(self.agenda)
        title, subtitle, groups, empty = self._agenda_view(now, day_start, day_end)
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        self.agenda.set_content(groups, empty)

    def _agenda_view(self, now: datetime, day_start: datetime, day_end: datetime):
        today = now.date()
        if self.view == "today":
            items = self._filter(engine.agenda(self._repo, day_start, day_end))
            late = self._filter(engine.overdue(self._repo, day_start))
            pending = [i for i in items if not i.done]
            groups = [Group("In ritardo", tuple(late), alert=True, show_date=True),
                      Group("Da fare", tuple(pending)),
                      Group("Fatto oggi", tuple(i for i in items if i.done))]
            count = len(pending) + len(late)
            sub = f"{format_day(today).capitalize()} · " + (
                f"{count} da fare" if count else "tutto fatto")
            return "Oggi", sub, groups, EmptyState(
                "🌤️", "Giornata libera!", "Usa la barra qui sopra per aggiungere qualcosa.")
        if self.view == "upcoming":
            items = _next_only([i for i in self._filter(engine.agenda(
                self._repo, now, now + timedelta(days=30))) if not i.done])
            return "Prossimi giorni", f"{len(items)} promemoria nei prossimi 30 giorni" \
                " · i ricorrenti appaiono alla prossima scadenza", \
                _by_day(items, today), EmptyState("🧘", "Niente in arrivo", "I prossimi 30 giorni sono liberi.")
        if self.view == "overdue":
            items = self._filter(engine.overdue(self._repo, now))
            return "In ritardo", f"{len(items)} da recuperare", \
                [Group("", tuple(items), show_date=True)], \
                EmptyState("🎉", "Sei in pari!", "Nessun promemoria scaduto.")
        if self.view == "done":
            items = [i for i in self._filter(engine.agenda(
                self._repo, now - timedelta(days=365), now + timedelta(days=365))) if i.done]
            return "Completati", f"{len(items)} nell'ultimo anno", \
                _by_day(items, today, reverse=True), \
                EmptyState("📭", "Ancora niente", "Spunta il cerchio di un promemoria per completarlo.")
        category = self.view[4:]
        items = _next_only([i for i in self._filter(engine.agenda(
            self._repo, now, now + timedelta(days=90)))
            if i.reminder.category == category and not i.done])
        late = [i for i in self._filter(engine.overdue(self._repo, now))
                if i.reminder.category == category]
        groups = [Group("In ritardo", tuple(late), alert=True, show_date=True), *_by_day(items, today)]
        return category, "Prossimi 90 giorni", groups, EmptyState(
            "🗂️", f"Nessun promemoria in «{category}»", "Aggiungine uno: verrà messo in questa categoria.")

    def _refresh_calendar(self) -> None:
        cal = self.calendar_page.calendar
        cal.apply_palette()
        first = date(cal.yearShown(), cal.monthShown(), 1)
        self.page_title.setText("Calendario")
        self.page_subtitle.setText(f"{MONTHS[first.month - 1].capitalize()} {first.year}")
        frm = datetime.combine(first - timedelta(days=7), time.min)
        to = datetime.combine(first + timedelta(days=45), time.max)
        marks: dict[date, tuple[int, str]] = {}
        for item in self._filter(engine.agenda(self._repo, frm, to)):
            d = item.occurrence.date()
            rank = -1 if item.done else item.reminder.priority
            color = theme.current().muted if item.done else theme.priority_color(item.reminder.priority)
            if d not in marks or rank > marks[d][0]:
                marks[d] = (rank, color)
        cal.set_marks({d: c for d, (_, c) in marks.items()})
        self._refresh_calendar_day()

    def _refresh_calendar_day(self) -> None:
        d = self.calendar_page.selected_date()
        self.calendar_page.day_title.setText(day_label(d, date.today()))
        items = self._filter(engine.agenda(
            self._repo, datetime.combine(d, time.min), datetime.combine(d, time.max)))
        self.calendar_page.cards.set_content(
            [Group("", tuple(items))],
            EmptyState("📅", "Nessun promemoria", "Doppio clic sul giorno o «＋ Aggiungi»."))

    # ---- inserimento rapido -----------------------------------------------------
    def _quick_preview(self, text: str) -> None:
        if not text.strip():
            self.quick_hint.setText(QUICK_HINT)
            return
        p = parse(text)
        if p.found_when:
            extra = f" · ↻ {format_recurrence(p.recurrence)}" if p.recurrence.freq != "none" else ""
            self.quick_hint.setText(
                f"↵  Invio per creare «{p.title}» — {format_relative(p.start, datetime.now())}{extra}")
        else:
            self.quick_hint.setText("↵  Invio per scegliere data e ora nel modulo completo")

    def _quick_submit(self) -> None:
        text = self.quick.text().strip()
        if not text:
            return
        p = parse(text)
        category = self.view[4:] if self.view.startswith("cat:") else ""
        if not p.found_when:
            day = self.calendar_page.selected_date() if self.view == "calendar" else None
            if self.create(day=day, title=p.title, category=category):
                self.quick.clear()
            return
        now = datetime.now()
        alerts = (0, 10) if p.start - now > timedelta(minutes=10) else (0,)
        reminder = self._repo.add(Reminder(
            title=p.title, start=p.start, recurrence=p.recurrence, alerts=alerts,
            category=category, channels=default_channels(self._get_settings())))
        self.quick.clear()
        self._changed()
        self.toast.show_message(
            f"✓  Creato «{reminder.title}» per {format_relative(reminder.start, now)}",
            "Annulla", lambda: self._undo_create(reminder.id))

    def _undo_create(self, reminder_id: int) -> None:
        self._repo.delete(reminder_id)
        self._changed()

    # ---- azioni --------------------------------------------------------------------
    def create(self, day: date | None = None, title: str = "", category: str = "") -> bool:
        start = None
        if day is not None:
            now = datetime.now()
            start = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                     if day == now.date() else datetime.combine(day, time(9, 0)))
        settings = self._get_settings()
        dialog = EventDialog(settings, default_start=start, default_title=title,
                             default_category=category,
                             default_channels=default_channels(settings), parent=self)
        if dialog.exec() and dialog.result_reminder:
            r = self._repo.add(dialog.result_reminder)
            self._changed()
            self.toast.show_message(f"✓  Creato «{r.title}»")
            return True
        return False

    def edit(self, item: AgendaItem) -> None:
        dialog = EventDialog(self._get_settings(), reminder=item.reminder, parent=self)
        if dialog.exec() and dialog.result_reminder:
            self._repo.update(dialog.result_reminder)
            self._changed()
            self.toast.show_message("✓  Modifiche salvate")

    def delete(self, item: AgendaItem) -> None:
        r = item.reminder
        self._repo.delete(r.id)
        self._changed()
        what = "e tutte le ripetizioni" if r.is_recurring else ""
        self.toast.show_message(f"🗑  Eliminato «{r.title}» {what}".strip(), "Annulla",
                                lambda: self._restore(r), ms=7000)

    def _restore(self, reminder: Reminder) -> None:
        self._repo.add(replace(reminder, id=None))
        self._changed()

    def toggle_done(self, item: AgendaItem) -> None:
        engine.mark_done(self._repo, item, not item.done)
        self._changed()
        if not item.done:
            self.toast.show_message(f"✓  «{item.reminder.title}» completato", "Annulla",
                                    lambda: self._undo_done(item))

    def _undo_done(self, item: AgendaItem) -> None:
        engine.mark_done(self._repo, item, False)
        self._changed()

    def _changed(self) -> None:
        self.refresh()
        self.data_changed.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self.quitting:
            event.accept()
            return
        # La X nasconde la finestra: niente "trattino" sulla barra, ma l'app resta
        # attiva in background e gli avvisi continuano. Cliccando l'icona fissata
        # sulla barra la finestra riappare. Per uscire davvero c'è "Esci".
        event.ignore()
        self.hide()
