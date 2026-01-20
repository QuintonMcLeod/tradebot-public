"""Shared utilities, theme definitions, and regex patterns for the Tradebot SCI GUI.

This module centralizes functionality that is used across multiple GUI components.
By extracting these definitions from :mod:`tradebot_sci.gui.app`, we reduce
coupling and help prevent circular imports as the GUI codebase is broken
into smaller, focused modules. Nothing in this file has any side effects:
functions are pure helpers and dataclasses describe immutable configuration.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

__all__ = [
    "Theme",
    "THEMES",
    "STRUCTURE_RE",
    "SELECT_RE",
    "DECISION_RE",
    "EXEC_RE",
    "TS_RE",
    "IBKR_ORDERID_RE",
    "IBKR_ACTION_RE",
    "IBKR_QTY_RE",
    "IBKR_TIF_RE",
    "IBKR_STATUS_RE",
    "IBKR_FILLED_RE",
    "IBKR_AVG_FILL_RE",
    "IBKR_LMT_RE",
    "IBKR_ORDERTYPE_RE",
    "IBKR_CONTRACT_SYM_RE",
    "IBKR_CONTRACT_CUR_RE",
    "_now_epoch",
    "_pick_symbol",
    "filter_auto_schedule_symbols",
]


@dataclass(frozen=True)
class Theme:
    """Represents a color scheme used by the GUI.

    Each field corresponds to a particular element of the user interface.  In
    addition to basic colours (window, base, card, header, border, etc.),
    optional Qt Style Sheet (QSS) strings can be provided to support
    gradients.  Alpha values control the transparency applied when
    generating the final QSS.
    """

    key: str
    name: str
    window: str
    base: str
    card: str
    header: str
    border: str
    stroke: str
    text: str
    muted: str
    accent: str
    good: str
    warn: str
    bad: str
    window_qss: str | None = None
    base_qss: str | None = None
    card_qss: str | None = None
    header_qss: str | None = None
    card_alpha: float = 0.78
    base_alpha: float = 0.72
    header_alpha: float = 0.85
    menubar_alpha: float = 0.65
    menu_alpha: float = 0.95

    def qss(self) -> str:
        """Return a Qt Style Sheet string for this theme.

        The resulting QSS is a long concatenated string which customises
        virtually every Qt widget used by the application.  This method is
        intentionally verbose but remains pure – it neither reads nor writes
        any external state.  See :mod:`tradebot_sci.gui.app` for usage.
        """

        def rgba(hex_color: str, alpha: float) -> str:
            s = (hex_color or "").strip()
            if s.startswith("rgba(") or s.startswith("rgb("):
                return s
            if s.startswith("#") and len(s) == 7:
                r = int(s[1:3], 16)
                g = int(s[3:5], 16)
                b = int(s[5:7], 16)
                a = max(0.0, min(1.0, float(alpha)))
                return f"rgba({r},{g},{b},{a:.2f})"
            return s

        window_bg = self.window_qss or self.window
        base_bg = rgba(self.base, self.base_alpha)
        card_bg = rgba(self.card, self.card_alpha)
        header_bg = rgba(self.header, self.header_alpha)
        menubar_bg = rgba(self.window, self.menubar_alpha)
        menu_bg = rgba(self.card, self.menu_alpha)
        border_soft = rgba(self.border, 0.12)
        return (
            "QMainWindow { background: " + window_bg + "; }"
            "QWidget { color: " + self.text + "; }"
            "QSplitter::handle { background: transparent; }"
            "QMenuBar { background: " + menubar_bg + "; color: " + self.text + "; }"
            "QMenuBar::item:selected { background: " + header_bg + "; }"
            "QMenu { background: " + menu_bg + "; color: " + self.text + "; border: 1px solid " + border_soft + "; }"
            "QMenu::item:selected { background: " + header_bg + "; }"
            "QStatusBar { background: " + menubar_bg + "; color: " + self.muted + "; }"
            "QGroupBox {"
            "  background: transparent;"
            "  border: 1px solid " + border_soft + ";"
            "  border-radius: 10px;"
            "  margin-top: 14px;"
            "  padding: 10px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 8px;"
            "  color: " + self.accent + ";"
            "  font-weight: 700;"
            "}"
            "QPlainTextEdit, QTextEdit {"
            "  background: " + base_bg + ";"
            "  color: " + self.text + ";"
            "  border: 1px solid " + border_soft + ";"
            "  border-radius: 8px;"
            "  padding: 8px;"
            "  selection-background-color: " + header_bg + ";"
            "  font-family: JetBrains Mono, DejaVu Sans Mono, monospace;"
            "  font-size: 11pt;"
            "}"
            "QPlainTextEdit#logView { font-size: 9pt; }"
            "QTableWidget {"
            "  background: " + base_bg + ";"
            "  color: " + self.text + ";"
            "  border: 1px solid " + border_soft + ";"
            "  border-radius: 8px;"
            "  font-family: JetBrains Mono, DejaVu Sans Mono, monospace;"
            "  font-size: 11pt;"
            "}"
            "QHeaderView::section {"
            "  background: " + header_bg + ";"
            "  color: " + self.accent + ";"
            "  border: none;"
            "  padding: 6px 8px;"
            "  font-weight: 700;"
            "}"
            "QScrollBar:vertical {"
            "  background: transparent;"
            "  width: 10px;"
            "  margin: 0px;"
            "  border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: " + rgba(self.border, 0.55) + ";"
            "  min-height: 28px;"
            "  border-radius: 5px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: " + rgba(self.header, 0.70) + "; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
            "QScrollBar:horizontal {"
            "  background: transparent;"
            "  height: 10px;"
            "  margin: 0px;"
            "  border: none;"
            "}"
            "QScrollBar::handle:horizontal {"
            "  background: " + rgba(self.border, 0.55) + ";"
            "  min-width: 28px;"
            "  border-radius: 5px;"
            "}"
            "QScrollBar::handle:horizontal:hover { background: " + rgba(self.header, 0.70) + "; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }"
            "QTabWidget::pane {"
            "  border: 1px solid " + border_soft + ";"
            "  background: transparent;"
            "  border-radius: 10px;"
            "}"
            "QTabBar { background: transparent; }"
            "QTabBar::tab {"
            "  background: " + rgba(self.card, 0.28) + ";"
            "  border: 1px solid " + rgba(self.border, 0.16) + ";"
            "  border-bottom: none;"
            "  padding: 7px 14px;"
            "  margin-right: 6px;"
            "  border-top-left-radius: 10px;"
            "  border-top-right-radius: 10px;"
            "  color: " + rgba(self.text, 0.85) + ";"
            "}"
            "QTabBar::tab:selected {"
            "  background: " + rgba(self.header, 0.50) + ";"
            "  border: 1px solid " + rgba(self.border, 0.24) + ";"
            "  border-bottom: none;"
            "  color: " + self.text + ";"
            "  font-weight: 700;"
            "}"
            "QTabBar::tab:hover { background: " + rgba(self.header, 0.38) + "; }"
        )


# Regular expression patterns used by log parsing and IBKR log ingestion.
# Regex patterns for parsing log lines. Symbols may contain characters like / : - . 
# We update the capture group from [A-Z0-9]+ to [-A-Z0-9/:.]+ to support complex tickers (e.g. BTC/USD:USD-250328).
STRUCTURE_RE: re.Pattern[str] = re.compile(r"\[STRUCTURE\]\s+(?P<symbol>[-A-Z0-9/:.]+)\s+(?P<fields>.*)")
SELECT_RE: re.Pattern[str] = re.compile(r"\[SELECT\]\s+Active symbol:\s+(?P<symbol>[-A-Z0-9/:.]+)\b")
# Handle potential double 'Decision: Decision:' prefix in logs
DECISION_RE: re.Pattern[str] = re.compile(r"Decision:\s+(?:Decision:\s+)?(?P<symbol>[-A-Z0-9/:.]+)\s+(?P<tf>[^|]+)\|\s+(?P<rest>.*)$")
EXEC_RE: re.Pattern[str] = re.compile(r"\[EXEC\]\s+(?P<symbol>[-A-Z0-9/:.]+)\s+outcome=(?P<outcome>[^\\s]+)\s+reason=(?P<reason>.*)$")
TS_RE: re.Pattern[str] = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\b")
IBKR_ORDERID_RE: re.Pattern[str] = re.compile(r"\borderId=(?P<id>\d+)\b")
IBKR_ACTION_RE: re.Pattern[str] = re.compile(r"\baction='(?P<action>BUY|SELL)'")
IBKR_QTY_RE: re.Pattern[str] = re.compile(r"\btotalQuantity=(?P<qty>[-0-9.]+)")
IBKR_TIF_RE: re.Pattern[str] = re.compile(r"\btif='(?P<tif>[^']+)'")
IBKR_STATUS_RE: re.Pattern[str] = re.compile(r"\bstatus='(?P<status>[^']+)'")
IBKR_FILLED_RE: re.Pattern[str] = re.compile(r"\bfilled=(?P<filled>[-0-9.]+)")
IBKR_AVG_FILL_RE: re.Pattern[str] = re.compile(r"\bavgFillPrice=(?P<avg>[-0-9.]+)")
IBKR_LMT_RE: re.Pattern[str] = re.compile(r"\blmtPrice=(?P<lmt>[-0-9.]+)")
IBKR_ORDERTYPE_RE: re.Pattern[str] = re.compile(r"\border=(?P<type>[A-Za-z0-9_]+)\(")
IBKR_CONTRACT_SYM_RE: re.Pattern[str] = re.compile(r"\bcontract=.*?\bsymbol='(?P<sym>[^']+)'")
IBKR_CONTRACT_CUR_RE: re.Pattern[str] = re.compile(r"\bcurrency='(?P<cur>[^']+)'")


def _now_epoch() -> float:
    """Return the current time as a POSIX timestamp in seconds."""
    return time.time()


def filter_auto_schedule_symbols(symbols: Iterable[str]) -> list[str]:
    """Filter symbols using auto-schedule (equities in-hours, crypto off-hours)."""
    raw = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not raw:
        return []
    if os.getenv("BUG_BYPASS_SCHEDULE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return raw
    auto_enabled = False
    try:
        from tradebot_sci.config.loader import load_settings, get_settings  # type: ignore

        settings_obj = get_settings()
        profile_settings = settings_obj.get_active_profile()
        auto_enabled = bool(getattr(profile_settings, "auto_schedule_enabled", False))
        
        # [ANTIGRAVITY FIX] Mirror loop.py logic: if crypto_only is set, bypass schedule and force crypto
        force_crypto = bool(getattr(profile_settings, "crypto_only", False))
        if force_crypto:
            # We don't have is_crypto here easily without potentially circular imports, 
            # but usually the input 'symbols' are just the allowed universe logic. 
            # If we just return 'raw', we respect the profile's symbol list.
            # But let's try to be safe.
            return raw 

    except Exception:
        profile = (os.getenv("PROFILE_NAME") or "").strip().lower()
        auto_env = os.getenv("PROFILE_AUTO_SCHEDULE_ENABLED", "").strip().lower()
        auto_enabled = profile == "auto_schedule" or auto_env in {"1", "true", "yes", "on"}
        # Fallback check for crypto_only env var if needed, but profile loading usually works
        
    if not auto_enabled:
        return raw
    try:
        from tradebot_sci.runtime.auto_schedule import select_auto_schedule_symbols  # type: ignore

        selection = select_auto_schedule_symbols(raw, datetime.now(timezone.utc))
        return selection.symbols
    except Exception as e:
        logger.debug(f"Failed to apply auto-schedule to symbols: {e}")
        return raw


def _top_symbols(state: Any, n: int, symbols_filter: Iterable[str] | None = None) -> list[str]:
    """Return the top *n* symbols ranked by readiness and selection score.

    This helper looks into ``state.structure_by_symbol`` to produce a sorted
    list of symbols.  It is intended to be used only by :func:`_pick_symbol`.
    """
    items: list[Tuple[str, Any]] = list((getattr(state, "structure_by_symbol", {}) or {}).items())
    if symbols_filter:
        allowed = {str(s).upper() for s in symbols_filter}
        items = [(sym, info) for sym, info in items if str(sym).upper() in allowed]
    # Sort by readiness then selection score descending.
    items.sort(key=lambda kv: (getattr(kv[1], "readiness", 0.0), getattr(kv[1], "selection_score", 0.0)), reverse=True)
    return [sym for sym, _ in items[:n]]


def _pick_symbol(
    state: Any, *, rotate_seconds: int, symbols_filter: Iterable[str] | None = None
) -> tuple[str | None, str]:
    """Choose which symbol to display on the candle chart.

    If the user has an active symbol selected, that symbol is returned along
    with the reason ``"active_symbol"``.  Otherwise the top three symbols
    (based on readiness and selection score) are rotated over time using
    ``rotate_seconds`` to determine the interval.  If no symbols are
    available, ``(None, "no symbols yet")`` is returned.
    """
    active = getattr(state, "active_symbol", None)
    if active:
        return active, "active_symbol"
    top3 = _top_symbols(state, 3, symbols_filter=symbols_filter)
    if not top3:
        return None, "no symbols yet"
    idx = int((_now_epoch() // rotate_seconds) % len(top3))
    return top3[idx], "rotating top3"


# Collection of built-in themes.  New themes may be added here without
# modifying the consuming code.  Keys correspond to the ``key`` field of
# :class:`Theme` instances.
THEMES: Dict[str, Theme] = {
    "dark": Theme(
        key="dark",
        name="Dark (Purple)",
        window="#1a1226",
        base="#141022",
        card="#211a33",
        header="#2f2550",
        border="#3b2f5a",
        stroke="rgba(255,255,255,0.10)",
        text="#ece9f7",
        muted="#b5adcc",
        accent="#4cc9f0",
        good="#22c55e",
        warn="#f59e0b",
        bad="#ef4444",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1226, stop:1 #24133d)",
        card_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #211a33, stop:1 #1c1630)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f2550, stop:1 #2a1f46)",
    ),
    "midnight": Theme(
        key="midnight",
        name="Dark (Midnight Blue)",
        window="#0b1020",
        base="#0a0f1c",
        card="#101a33",
        header="#18244a",
        border="#26355f",
        stroke="rgba(255,255,255,0.10)",
        text="#e7ecff",
        muted="#9aa6c7",
        accent="#7dd3fc",
        good="#34d399",
        warn="#fbbf24",
        bad="#fb7185",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0b1020, stop:1 #0f1b3a)",
        card_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #101a33, stop:1 #0f1630)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #18244a, stop:1 #1b2a55)",
    ),
    "nord": Theme(
        key="nord",
        name="Dark (Nord Frost)",
        window="#2e3440",
        base="#2b313c",
        card="#3b4252",
        header="#434c5e",
        border="#4c566a",
        stroke="rgba(255,255,255,0.10)",
        text="#eceff4",
        muted="#d8dee9",
        accent="#88c0d0",
        good="#a3be8c",
        warn="#ebcb8b",
        bad="#bf616a",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2e3440, stop:1 #252b36)",
        card_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b4252, stop:1 #353b49)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #434c5e, stop:1 #3d4556)",
    ),
    "solarized_dark": Theme(
        key="solarized_dark",
        name="Dark (Solarized)",
        window="#002b36",
        base="#073642",
        card="#073642",
        header="#0b3f4e",
        border="#1f4b57",
        stroke="rgba(255,255,255,0.10)",
        text="#eee8d5",
        muted="#93a1a1",
        accent="#268bd2",
        good="#859900",
        warn="#b58900",
        bad="#dc322f",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0b3f4e, stop:1 #0a3441)",
    ),
    "monokai": Theme(
        key="monokai",
        name="Dark (Monokai Neon)",
        window="#1b1d1e",
        base="#121314",
        card="#1f2021",
        header="#2a2b2c",
        border="#3a3b3c",
        stroke="rgba(255,255,255,0.10)",
        text="#f8f8f2",
        muted="#a6a6a6",
        accent="#66d9ef",
        good="#a6e22e",
        warn="#fd971f",
        bad="#f92672",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1b1d1e, stop:1 #151617)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a2b2c, stop:1 #242526)",
    ),
    "gruvbox": Theme(
        key="gruvbox",
        name="Dark (Gruvbox)",
        window="#1d2021",
        base="#1b1f20",
        card="#282828",
        header="#3c3836",
        border="#504945",
        stroke="rgba(255,255,255,0.10)",
        text="#ebdbb2",
        muted="#a89984",
        accent="#83a598",
        good="#b8bb26",
        warn="#fabd2f",
        bad="#fb4934",
        card_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #282828, stop:1 #242424)",
    ),
    "light": Theme(
        key="light",
        name="Light (Beige)",
        window="#f2e8d6",
        base="#fffaf2",
        card="#fffefd",
        header="#efe2c8",
        border="#d8c9ae",
        stroke="rgba(15,23,42,0.12)",
        text="#1f1732",
        muted="#5b546b",
        accent="#6d28d9",
        good="#16a34a",
        warn="#b45309",
        bad="#dc2626",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e9d7b0, stop:0.30 #f0d1e8, stop:0.60 #bfe9ff, stop:1 #ffe6c4)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #efe2c8, stop:1 #f6eddc)",
        base_alpha=0.54,
        card_alpha=0.58,
        header_alpha=0.74,
        menubar_alpha=0.52,
    ),
    "light_mint": Theme(
        key="light_mint",
        name="Light (Mint)",
        window="#eefcf6",
        base="#fbfffd",
        card="#ffffff",
        header="#dcf7ee",
        border="#c6eadb",
        stroke="rgba(15,23,42,0.12)",
        text="#0f172a",
        muted="#475569",
        accent="#0ea5e9",
        good="#16a34a",
        warn="#b45309",
        bad="#dc2626",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b8f3d6, stop:0.36 #c7f9ef, stop:0.70 #bfe0ff, stop:1 #ffd6e7)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dcf7ee, stop:1 #e9f7ff)",
        base_alpha=0.54,
        card_alpha=0.58,
        header_alpha=0.74,
        menubar_alpha=0.52,
    ),
    "light_solarized": Theme(
        key="light_solarized",
        name="Light (Solarized)",
        window="#fdf6e3",
        base="#fffaf0",
        card="#ffffff",
        header="#efe6c8",
        border="#d5cdbb",
        stroke="rgba(15,23,42,0.12)",
        text="#073642",
        muted="#586e75",
        accent="#268bd2",
        good="#2aa198",
        warn="#b58900",
        bad="#dc322f",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e8d7a8, stop:0.40 #f6e3b4, stop:0.74 #bfe6ff, stop:1 #ffe0bf)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #efe6c8, stop:1 #f6efd8)",
        base_alpha=0.54,
        card_alpha=0.58,
        header_alpha=0.74,
        menubar_alpha=0.52,
    ),
    "light_sky": Theme(
        key="light_sky",
        name="Light (The Sky Is Blue)",
        window="#d7edff",
        base="#f5fbff",
        card="#fbfeff",
        header="#cfe4ff",
        border="#aac8ee",
        stroke="rgba(2,6,23,0.12)",
        text="#0f172a",
        muted="#475569",
        accent="#0284c7",
        good="#16a34a",
        warn="#b45309",
        bad="#dc2626",
        # "Sky with clouds": blue gradient + soft white cloud bands.
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #66b8ff, stop:0.22 #a7dbff, stop:0.35 #f4fbff, stop:0.48 #bfe7ff, stop:0.62 #ffffff, stop:0.78 #a7dbff, stop:1 #4aa2ff)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cfe4ff, stop:1 #eaf7ff)",
        base_alpha=0.52,
        card_alpha=0.56,
        header_alpha=0.72,
        menubar_alpha=0.50,
    ),
    "light_rose": Theme(
        key="light_rose",
        name="Light (Rose)",
        window="#fff3f7",
        base="#fffafc",
        card="#ffffff",
        header="#ffe0ea",
        border="#ffc9d7",
        stroke="rgba(2,6,23,0.12)",
        text="#1f0a14",
        muted="#6b5460",
        accent="#e11d48",
        good="#16a34a",
        warn="#b45309",
        bad="#b91c1c",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffb3c7, stop:0.32 #ffd3e1, stop:0.66 #cbe6ff, stop:1 #ffe0bf)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffe0ea, stop:1 #fff0f5)",
        base_alpha=0.54,
        card_alpha=0.58,
        header_alpha=0.74,
        menubar_alpha=0.52,
    ),
    "light_slate": Theme(
        key="light_slate",
        name="Light (Slate)",
        window="#f8fafc",
        base="#fbfcff",
        card="#ffffff",
        header="#e5e7ff",
        border="#cbd5e1",
        stroke="rgba(2,6,23,0.12)",
        text="#0f172a",
        muted="#475569",
        accent="#334155",
        good="#16a34a",
        warn="#b45309",
        bad="#dc2626",
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #c7d2fe, stop:0.40 #e0e7ff, stop:0.72 #cbe6ff, stop:1 #ffffff)",
        header_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e5e7ff, stop:1 #eef2f7)",
        base_alpha=0.54,
        card_alpha=0.58,
        header_alpha=0.74,
        menubar_alpha=0.52,
    ),
    "mockup_pro": Theme(
        key="mockup_pro",
        name="Mockup Pro (Cyberpunk)",
        window="#050510",     # Deepest void blue
        base="#0a0a1a",       # Slightly lighter bg
        card="#11112b",       # Card bg
        header="#1a1a3d",     # Header bg
        border="#2a2a5d",     # Borders
        stroke="rgba(0, 255, 255, 0.15)", # Neon cyan stroke
        text="#e0e0ff",       # White-blue text
        muted="#6060aa",      # Muted purple-blue
        accent="#00ffff",     # Cyan Neon
        good="#00ff99",       # Neon Green
        warn="#ffcc00",       # Neon Yellow
        bad="#ff3366",        # Neon Pink/Red
        window_qss="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #050510, stop:1 #080818)",
        card_qss="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #11112b, stop:1 #0e0e24)",
        header_qss="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a3d, stop:1 #141430)",
    ),
}
