"""Tema grafico: palette chiara/scura e foglio di stile Qt."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    primary: str
    primary_hover: str
    primary_soft: str
    on_primary: str
    danger: str
    danger_soft: str
    success: str
    warning: str
    priority_low: str
    priority_normal: str
    priority_high: str


LIGHT = Palette(
    dark=False, bg="#f6f7fb", sidebar="#eef0f7", surface="#ffffff", surface_alt="#f1f3f9",
    border="#e1e4ee", text="#1d2130", muted="#6b7185", primary="#5b5bf0",
    primary_hover="#4a4ad9", primary_soft="#e8e8fd", on_primary="#ffffff",
    danger="#e5484d", danger_soft="#fdecec", success="#2fa36b", warning="#d9822b",
    priority_low="#9aa0b2", priority_normal="#5b5bf0", priority_high="#e5484d",
)
DARK = Palette(
    dark=True, bg="#15161c", sidebar="#1b1c24", surface="#20222b", surface_alt="#272934",
    border="#2f3240", text="#eceef5", muted="#9399ad", primary="#7c7cff",
    primary_hover="#8f8fff", primary_soft="#2b2c4a", on_primary="#ffffff",
    danger="#ff6369", danger_soft="#3a2226", success="#3dd68c", warning="#f5a524",
    priority_low="#6f7588", priority_normal="#7c7cff", priority_high="#ff6369",
)

_current: Palette = LIGHT
CHECK_ICON = (Path(__file__).parent / "assets" / "check.svg").as_posix()


def current() -> Palette:
    return _current


def priority_color(priority: int) -> str:
    p = _current
    return {0: p.priority_low, 1: p.priority_normal, 2: p.priority_high}.get(priority, p.primary)


def system_is_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return app.palette().window().color().lightness() < 128


def resolve(app: QApplication, mode: str) -> Palette:
    if mode == "light":
        return LIGHT
    if mode == "dark":
        return DARK
    return DARK if system_is_dark(app) else LIGHT


def apply(app: QApplication, mode: str = "auto") -> Palette:
    global _current
    _current = resolve(app, mode)
    p = _current
    font = QFont("Segoe UI Variable Text")
    if not font.exactMatch():
        font = QFont("Segoe UI")
    font.setPointSizeF(10)
    app.setFont(font)

    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.bg, QPalette.ColorRole.WindowText: p.text,
        QPalette.ColorRole.Base: p.surface, QPalette.ColorRole.AlternateBase: p.surface_alt,
        QPalette.ColorRole.Text: p.text, QPalette.ColorRole.Button: p.surface,
        QPalette.ColorRole.ButtonText: p.text, QPalette.ColorRole.Highlight: p.primary,
        QPalette.ColorRole.HighlightedText: p.on_primary, QPalette.ColorRole.ToolTipBase: p.surface,
        QPalette.ColorRole.ToolTipText: p.text, QPalette.ColorRole.PlaceholderText: p.muted,
        QPalette.ColorRole.Link: p.primary,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p.muted))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p.muted))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(p))
    return p


def stylesheet(p: Palette) -> str:
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border};
    border-radius: 6px; padding: 4px 8px; }}

/* ---- barra laterale ---- */
#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#AppName {{ font-size: 17px; font-weight: 700; }}
#SectionLabel {{ color: {p.muted}; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; padding: 14px 10px 4px 10px; }}
QPushButton#Nav {{ background: transparent; border: none; border-radius: 8px;
    text-align: left; padding: 8px 10px; min-height: 20px; }}
QPushButton#Nav:hover {{ background: {p.surface_alt}; }}
QPushButton#Nav:checked {{ background: {p.primary_soft}; color: {p.primary}; font-weight: 600; }}
#NavText[active="true"] {{ color: {p.primary}; font-weight: 600; }}
#NavCount {{ background: {p.surface_alt}; color: {p.muted}; border-radius: 9px;
    padding: 1px 7px; font-size: 11px; font-weight: 600; }}
#NavCount[alert="true"] {{ background: {p.danger}; color: white; }}

/* ---- intestazione ---- */
#PageTitle {{ font-size: 26px; font-weight: 700; }}
#PageSubtitle {{ color: {p.muted}; font-size: 13px; }}
#GroupHeader {{ color: {p.muted}; font-size: 12px; font-weight: 700;
    letter-spacing: 0.5px; padding: 14px 4px 4px 4px; }}
#GroupHeader[alert="true"] {{ color: {p.danger}; }}
#Muted {{ color: {p.muted}; }}
#Hint {{ color: {p.muted}; font-size: 12px; }}

/* ---- campi ---- */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QDateTimeEdit {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {p.primary}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QDateTimeEdit:focus {{ border: 1px solid {p.primary}; }}
QLineEdit#QuickAdd {{ font-size: 14px; padding: 11px 14px; border-radius: 12px; }}
QLineEdit#Search {{ border-radius: 16px; padding: 6px 14px; }}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
    selection-background-color: {p.primary_soft}; selection-color: {p.text}; padding: 4px; }}

/* ---- pulsanti ---- */
QPushButton {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 7px 14px; }}
QPushButton:hover {{ background: {p.surface_alt}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton#Primary {{ background: {p.primary}; color: {p.on_primary}; border: none;
    font-weight: 600; }}
QPushButton#Primary:hover {{ background: {p.primary_hover}; }}
QPushButton#Danger {{ color: {p.danger}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.muted}; }}
QPushButton#Ghost:hover {{ color: {p.text}; background: {p.surface_alt}; }}
QPushButton#Chip {{ background: {p.surface_alt}; border: 1px solid transparent;
    border-radius: 13px; padding: 4px 12px; font-size: 12px; }}
QPushButton#Chip:hover {{ border: 1px solid {p.primary}; color: {p.primary}; }}
QPushButton#Chip:checked {{ background: {p.primary_soft}; color: {p.primary};
    border: 1px solid {p.primary}; font-weight: 600; }}
QToolButton#CardAction {{ background: transparent; border: none; border-radius: 6px;
    padding: 4px; color: {p.muted}; font-size: 14px; }}
QToolButton#CardAction:hover {{ background: {p.surface_alt}; color: {p.text}; }}
QToolButton#CardDelete:hover {{ background: {p.danger_soft}; color: {p.danger}; }}
QToolButton#CardDelete {{ background: transparent; border: none; border-radius: 6px;
    padding: 4px; color: {p.muted}; font-size: 14px; }}

/* ---- card ---- */
#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
#Card:hover {{ border: 1px solid {p.primary}; }}
#CardTitle {{ font-size: 14px; font-weight: 600; }}
#CardTitle[done="true"] {{ color: {p.muted}; text-decoration: line-through; font-weight: 400; }}
#CardNotes {{ color: {p.muted}; font-size: 12px; }}
#Badge {{ background: {p.surface_alt}; color: {p.muted}; border-radius: 9px;
    padding: 2px 8px; font-size: 11px; font-weight: 600; }}
#Badge[kind="late"] {{ background: {p.danger_soft}; color: {p.danger}; }}
#Badge[kind="time"] {{ background: {p.primary_soft}; color: {p.primary}; }}
#EmptyIcon {{ font-size: 46px; }}
#EmptyTitle {{ font-size: 16px; font-weight: 600; }}

/* ---- scroll ---- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- calendario ---- */
#CalendarCard, #Panel {{ background: {p.surface}; border: 1px solid {p.border};
    border-radius: 14px; }}
#qt_calendar_navigationbar {{ background: {p.surface}; padding: 6px; }}
QCalendarWidget QTableView {{ alternate-background-color: {p.surface}; background: {p.surface}; }}
QCalendarWidget QToolButton {{ color: {p.text}; background: transparent; border: none;
    border-radius: 6px; padding: 4px 8px; font-size: 15px; font-weight: 700; }}
QCalendarWidget QToolButton:hover {{ background: {p.surface_alt}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
QCalendarWidget QMenu {{ background: {p.surface}; border: 1px solid {p.border}; }}
QCalendarWidget QSpinBox {{ border: none; background: transparent; font-weight: 700; }}
QCalendarWidget QAbstractItemView {{ background: {p.surface}; color: {p.text};
    selection-background-color: {p.primary}; selection-color: {p.on_primary};
    border: none; font-size: 13px; }}
QCalendarWidget QAbstractItemView:disabled {{ color: {p.muted}; }}

/* ---- sezioni dei dialog ---- */
QGroupBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
    margin-top: 22px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 6px; top: 2px; color: {p.muted}; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px;
    border: 1.5px solid {p.muted}; background: {p.surface}; }}
QCheckBox::indicator:checked {{ background: {p.primary}; border: 1.5px solid {p.primary};
    image: url({CHECK_ICON}); }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QLineEdit, QPlainTextEdit {{ selection-color: {p.on_primary}; }}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; background: {p.surface};
    top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {p.muted};
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.primary}; border-bottom: 2px solid {p.primary};
    font-weight: 600; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.primary_soft}; color: {p.text}; }}

/* ---- toast e popup ---- */
#Toast {{ background: {"#eceef5" if p.dark else "#1d2130"}; border-radius: 10px; }}
#Toast QLabel {{ color: {"#1d2130" if p.dark else "#ffffff"}; }}
#Toast QPushButton {{ background: transparent; border: none; font-weight: 700;
    color: {p.primary if p.dark else "#a5a5ff"}; padding: 4px 8px; }}
#PopupAccent {{ border-top-left-radius: 0; }}
#PopupTitle {{ font-size: 19px; font-weight: 700; }}
#PopupWhen {{ font-size: 13px; color: {p.muted}; }}
#PopupNotes {{ background: {p.surface_alt}; border-radius: 8px; padding: 10px; }}
#PopupWarning {{ color: {p.warning}; font-weight: 600; }}
"""
