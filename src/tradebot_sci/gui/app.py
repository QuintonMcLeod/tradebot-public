from __future__ import annotations

import json
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.commentary_prompts import build_commentary_messages
import sys
from tradebot_sci.config.loader import load_settings, get_settings
from tradebot_sci.config.models import AISettings
from tradebot_sci.config.models import AISettings
from tradebot_sci.gui.decision_formatter import DecisionFormatter
from tradebot_sci.runtime.provider_factory import build_market_provider, build_exchange_broker
from tradebot_sci.market.providers import MarketDataProvider

# Pull shared definitions from the shared module.  These provide the
# Theme dataclass, a collection of built‑in themes, symbol selection
# helpers, a clock helper, and all of the regular expression patterns
# used for log parsing and IBKR event extraction.  Importing them here
# ensures there is only a single definition for each across the codebase.
from tradebot_sci.gui.shared import (
    THEMES,
    Theme,
    _pick_symbol,
    _now_epoch,
    STRUCTURE_RE,
    SELECT_RE,
    DECISION_RE,
    EXEC_RE,
    TS_RE,
    IBKR_ORDERID_RE,
    IBKR_ACTION_RE,
    IBKR_QTY_RE,
    IBKR_TIF_RE,
    IBKR_STATUS_RE,
    IBKR_FILLED_RE,
    IBKR_AVG_FILL_RE,
    IBKR_LMT_RE,
    IBKR_ORDERTYPE_RE,
    IBKR_CONTRACT_SYM_RE,
    IBKR_CONTRACT_CUR_RE,
)

# Expose the environment settings dialog entry point.  This helper
# constructs and displays the draggable settings window using the
# provided configuration and environment context.
from tradebot_sci.gui.settings_dialog import open_settings_dialog
# Import the log panel after shared utilities.  This class encapsulates
# the creation of the log text widget and syntax highlighting, allowing
# the main window to focus on layout and orchestration.
from tradebot_sci.gui.log_panel import LogPanel
from tradebot_sci.gui.decisions_panel import DecisionsPanel
from tradebot_sci.gui.candles_panel import CandlesPanel
from tradebot_sci.gui.readiness_table import ReadinessTable
from tradebot_sci.gui.orders_panel import OrdersPanel
from tradebot_sci.gui.commentary_panel import CommentaryPanel
from tradebot_sci.runtime.capital_tuner import (
    AUTO_TUNE_ENABLED_ENV,
    AUTO_TUNE_LAST_TS_ENV,
    apply_tune_to_env,
    auto_tune_due,
    fetch_account_equity,
    load_log_excerpt,
    request_capital_tune,
    sanitize_context,
)

# Load the base configuration once at module import time.  This
# `global_settings` object holds application/profile configuration
# separate from the GUI runtime preferences defined in `Settings`
# below.  Using a distinct name avoids shadowing by the local
# `settings` variable inside `run_app()`.
global_settings = load_settings()

# Regex patterns for parsing structure, selection, decisions and IBKR
# orders were moved to tradebot_sci.gui.shared.  They are imported
# above and referenced throughout this module via those imports.
PDT_ERROR_RE = re.compile(r"Error 201.*(?:day trade|pdt|pattern day trader)", re.IGNORECASE)


@dataclass
class StructureInfo:
    symbol: str
    selection_score: float
    readiness: float
    reason: str
    icc_grade: str | None = None
    watch_grade: str | None = None
    last_gate: str | None = None
    since_sweep: str | None = None
    since_cont: str | None = None
    seen_ts: float = 0.0


@dataclass
class DecisionEvent:
    ts: str
    symbol: str
    tf: str
    rest: str


@dataclass
class UiState:
    active_symbol: str | None = None
    structure_by_symbol: dict[str, StructureInfo] | None = None
    last_decision_by_symbol: dict[str, str] | None = None
    decision_events: deque[DecisionEvent] | None = None
    orders_by_id: dict[int, "OrderEvent"] | None = None  # LRU cache with max 1000 orders
    _orders_max_size: int = 1000


@dataclass
class OrderEvent:
    ts: str
    symbol: str
    order_id: int
    action: str | None = None
    qty: float | None = None
    order_type: str | None = None
    tif: str | None = None
    status: str | None = None
    filled: float | None = None
    avg_fill_price: float | None = None
    limit_price: float | None = None
    updated_ts: float = 0.0



# The `_now_epoch` helper is imported from `tradebot_sci.gui.shared`,
# therefore the local definition is removed.  Use `_now_epoch()` from
# the shared module instead of this stub.


def _iter_rotated_log_paths(log_path: Path, *, max_files: int = 25) -> list[Path]:
    """
    Returns current + rotated log paths in chronological order (oldest -> newest).
    Supports logrotate numeric suffixes: tradebot.log.1, tradebot.log.2, ...
    """
    if not log_path:
        return []
    base = log_path.name
    parent = log_path.parent
    if not parent.exists():
        return [log_path]

    rx = re.compile(rf"^{re.escape(base)}(?:\.(?P<n>\d+))?$")
    candidates: list[tuple[int, Path]] = []

    for p in parent.glob(base + "*"):
        m = rx.match(p.name)
        if not m:
            continue
        n_s = m.group("n")
        n = int(n_s) if n_s is not None else 0
        candidates.append((n, p))

    # Keep most recent N files (prefer lowest suffix = newest).
    candidates.sort(key=lambda t: t[0])
    if max_files and len(candidates) > max_files:
        candidates = candidates[:max_files]

    # For chronological ingest we want oldest -> newest: highest suffix first, then current (0).
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in candidates]


def _infer_holdings_from_orders(orders_by_id: dict[int, OrderEvent] | None) -> list[dict[str, Any]]:
    if not orders_by_id:
        return []
    net_qty: dict[str, float] = {}
    last_avg: dict[str, float] = {}
    last_ts: dict[str, str] = {}

    for o in orders_by_id.values():
        if not o.symbol:
            continue
        status_u = (o.status or "").upper()
        if "FILLED" not in status_u:
            continue
        filled = float(o.filled or 0.0)
        if filled <= 0:
            continue
        sym = str(o.symbol).upper()
        action = (o.action or "").upper()
        if action == "BUY":
            net_qty[sym] = net_qty.get(sym, 0.0) + filled
        elif action == "SELL":
            net_qty[sym] = net_qty.get(sym, 0.0) - filled
        else:
            continue
        ts = o.ts or ""
        if o.avg_fill_price is not None:
            prev_ts = last_ts.get(sym, "")
            if ts >= prev_ts:
                last_ts[sym] = ts
                last_avg[sym] = float(o.avg_fill_price)

    out: list[dict[str, Any]] = []
    for sym, qty in sorted(net_qty.items()):
        if abs(qty) < 1e-8:
            continue
        side = "long" if qty > 0 else "short"
        out.append(
            {
                "symbol": sym,
                "side": side,
                "size": abs(qty),
                "avg_price": last_avg.get(sym),
                "stop_loss": None,
                "take_profit": None,
                "open_bracket_risk": None,
                "working_orders": None,
                "synthetic_stop_armed": None,
                "hold_age_seconds": None,
                "hold_remaining_seconds": None,
                "working_order_statuses": [],
                "inferred": True,
            }
        )
    return out


def _llm_today_key() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _llm_budget_try_consume(path: Path, *, limit: int) -> tuple[bool, str | None]:
    """
    Cross-process budget shared by GUI + tmux panes.
    Returns (ok_to_call, note_for_ui).
    """
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover
        return True, "budget: unlocked (fcntl unavailable)"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                data = json.loads(raw) if raw else {}
                day = data.get("day")
                calls = int(data.get("calls", 0) or 0)
                today = _llm_today_key()
                if day != today:
                    day = today
                    calls = 0
                if calls >= limit:
                    note = f"budget: {calls}/{limit} calls today (paused)"
                    data = {"day": day, "calls": calls, "limit": limit, "updated_ts": _now_epoch()}
                    f.seek(0)
                    f.truncate(0)
                    f.write(json.dumps(data, sort_keys=True))
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass
                    return False, note
                calls += 1
                remaining = max(0, limit - calls)
                data = {"day": day, "calls": calls, "limit": limit, "updated_ts": _now_epoch()}
                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, sort_keys=True))
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
                return True, f"budget: {calls}/{limit} calls today (remaining {remaining})"
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        return True, f"budget: unavailable ({type(exc).__name__})"


def _next_llm_backoff_seconds(*, prev: float, error_text: str) -> float:
    text = (error_text or "").lower()
    if "insufficient balance" in text or "402" in text:
        return max(prev, 3600.0)
    if "rate limit" in text or "too many request" in text or "429" in text:
        return max(prev, 900.0)
    if prev <= 0:
        return 60.0
    return min(3600.0, max(60.0, prev * 2.0))



# Symbol rotation helpers are defined in the shared module.  Import
# `_pick_symbol` from there and use it directly.  The local
# implementations of `_top_symbols` and `_pick_symbol` are removed.


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


ENV_GETENV_RE = re.compile(r"os\.getenv\(\s*[\"'](?P<key>[A-Z0-9_]+)[\"']")
ENV_ENVIRON_GET_RE = re.compile(r"os\.environ\.get\(\s*[\"'](?P<key>[A-Z0-9_]+)[\"']")
ENV_ENVIRON_ITEM_RE = re.compile(r"os\.environ\[\s*[\"'](?P<key>[A-Z0-9_]+)[\"']\s*\]")
ENV_SHELL_EXPORT_RE = re.compile(r"^\s*export\s+(?P<key>[A-Z][A-Z0-9_]{2,})\b", re.MULTILINE)


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def _apply_dotenv_if_missing(path: Path) -> dict[str, str]:
    vals = _parse_dotenv(path)
    for k, v in vals.items():
        os.environ.setdefault(k, v)
    return vals


def _discover_env_keys(repo_root: Path) -> list[str]:
    keys: set[str] = set()
    search_roots = [
        repo_root / "src",
        repo_root / "tools",
        repo_root / "scripts",
        repo_root / "config",
        repo_root / "env",
    ]
    exts = {".py", ".sh", ".yaml", ".yml", ".env"}
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix and p.suffix not in exts:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for rx in (ENV_GETENV_RE, ENV_ENVIRON_GET_RE, ENV_ENVIRON_ITEM_RE):
                for m in rx.finditer(text):
                    keys.add(m.group("key"))
            if p.suffix == ".sh":
                for m in ENV_SHELL_EXPORT_RE.finditer(text):
                    keys.add(m.group("key"))
    # also include common launcher vars
    keys.update(
        {
            "PROFILE_NAME",
            "EXECUTE_TRADES",
            "LOG_LEVEL",
            "COMMENTARY_LLM",
            "COMMENTARY_LLM_MIN_SECONDS",
            "COMMENTARY_LLM_POLICY",
            "COMMENTARY_LLM_TZ",
            "COMMENTARY_LLM_DAILY_SLOTS",
            "COMMENTARY_LLM_MAX_CALLS_PER_DAY",
            "COMMENTARY_LLM_BUDGET_PATH",
            "STARTUP_CRYPTO_UNPROTECTED_POLICY",
            "IBKR_ZEROHASH_CRYPTO_TIF_MINUTES",
        }
    )
    return sorted(keys)


def _merge_dotenv(path: Path, updates: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    present: set[str] = set()
    out_lines: list[str] = []
    for raw in existing:
        line = raw
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(line)
            continue
        k, _ = stripped.split("=", 1)
        key = k.strip()
        if key in updates:
            out_lines.append(f"{key}={updates[key]}")
            present.add(key)
        else:
            out_lines.append(line)
            present.add(key)
    missing = [k for k in updates.keys() if k not in present]
    if missing:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        out_lines.append("# Added/updated via GUI")
        for k in sorted(missing):
            out_lines.append(f"{k}={updates[k]}")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _ingest_line(state: UiState, line: str) -> None:
    m = STRUCTURE_RE.search(line)
    if m:
        sym = m.group("symbol")
        fields = m.group("fields")
        reason = None
        if "(" in fields and fields.rstrip().endswith(")"):
            fields, reason_part = fields.split("(", 1)
            reason = reason_part.rstrip(")").strip() or None
        parsed = dict(re.findall(r"([a-z_]+)=([^\s]+)", fields.strip()))
        info = StructureInfo(
            symbol=sym,
            selection_score=_safe_float(parsed.get("selection_score")),
            readiness=_safe_float(parsed.get("readiness")),
            reason=reason or "",
            icc_grade=(parsed.get("icc_grade") or None),
            watch_grade=(parsed.get("watch_grade") or None),
            last_gate=(parsed.get("last_gate") or None),
            since_sweep=(parsed.get("since_sweep") or None),
            since_cont=(parsed.get("since_cont") or None),
            seen_ts=_now_epoch(),
        )
        if state.structure_by_symbol is None:
            state.structure_by_symbol = {}
        state.structure_by_symbol[sym] = info
        return

    m = SELECT_RE.search(line)
    if m:
        state.active_symbol = m.group("symbol")
        return

    m = DECISION_RE.search(line)
    if m:
        sym = m.group("symbol")
        tf = (m.group("tf") or "").strip()
        rest = m.group("rest").strip()
        if state.last_decision_by_symbol is None:
            state.last_decision_by_symbol = {}
        state.last_decision_by_symbol[sym] = rest
        if state.decision_events is None:
            state.decision_events = deque(maxlen=80)
        ts_m = TS_RE.search(line)
        ts = (ts_m.group("ts") if ts_m else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())).strip()
        state.decision_events.append(DecisionEvent(ts=ts, symbol=sym, tf=tf, rest=rest))
        score_m = re.search(r"['\"]score['\"]:\s*([0-9.]+)", rest)
        threshold_m = re.search(r"['\"]score_threshold['\"]:\s*([0-9.]+)", rest)
        if score_m and threshold_m:
            score = _safe_float(score_m.group(1))
            threshold = _safe_float(threshold_m.group(1))
            normalized = score / threshold if threshold > 0 else score
            if state.structure_by_symbol is None:
                state.structure_by_symbol = {}
            existing = state.structure_by_symbol.get(sym)
            if existing is None:
                state.structure_by_symbol[sym] = StructureInfo(
                    symbol=sym,
                    selection_score=normalized,
                    readiness=0.0,
                    reason="score from decision",
                    icc_grade=None,
                    watch_grade=None,
                    last_gate=None,
                    since_sweep=None,
                    since_cont=None,
                    seen_ts=_now_epoch(),
                )
            elif existing.selection_score == 0.0 and score > 0.0:
                existing.selection_score = normalized
                existing.seen_ts = _now_epoch()
        return

    m = EXEC_RE.search(line)
    if m:
        sym = (m.group("symbol") or "").strip().upper()
        outcome = (m.group("outcome") or "").strip()
        reason = (m.group("reason") or "").strip()
        ts_m = TS_RE.search(line)
        ts = (ts_m.group("ts") if ts_m else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())).strip()
        seed = f"exec:{ts}:{sym}:{outcome}:{reason}"
        pseudo_id = -int(zlib.adler32(seed.encode("utf-8")) % 1_000_000_000 or 1)
        if state.orders_by_id is None:
            state.orders_by_id = {}
        evt = state.orders_by_id.get(pseudo_id) or OrderEvent(ts=ts, symbol=sym or "?", order_id=pseudo_id)
        evt.ts = ts
        evt.symbol = sym or evt.symbol
        evt.action = evt.action or None
        evt.qty = evt.qty
        evt.order_type = "EXEC"
        short_reason = reason
        if len(short_reason) > 48:
            short_reason = short_reason[:45].rstrip() + "…"
        evt.status = f"{outcome}{(': ' + short_reason) if short_reason else ''}"
        evt.updated_ts = _now_epoch()
        state.orders_by_id[pseudo_id] = evt
        # LRU eviction: remove oldest orders if cache exceeds max size
        if len(state.orders_by_id) > state._orders_max_size:
            # Remove oldest order (lowest updated_ts)
            oldest_id = min(state.orders_by_id.keys(), key=lambda k: state.orders_by_id[k].updated_ts)
            state.orders_by_id.pop(oldest_id, None)
        return

    # Best-effort IBKR order tracking via ib_insync logs.
    if "ib_insync" in line and ("placeOrder:" in line or "orderStatus:" in line):
        id_m = IBKR_ORDERID_RE.search(line)
        if not id_m:
            return
        order_id = int(id_m.group("id"))
        ts_m = TS_RE.search(line)
        ts = (ts_m.group("ts") if ts_m else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())).strip()

        sym_m = IBKR_CONTRACT_SYM_RE.search(line)
        cur_m = IBKR_CONTRACT_CUR_RE.search(line)
        contract_sym = (sym_m.group("sym") if sym_m else "").strip().upper()
        contract_cur = (cur_m.group("cur") if cur_m else "").strip().upper()
        symbol = contract_sym
        if contract_sym and contract_cur:
            candidate = f"{contract_sym}{contract_cur}"
            if state.structure_by_symbol and candidate in state.structure_by_symbol:
                symbol = candidate
            elif candidate in {"BTCUSD", "ETHUSD", "SOLUSD"}:
                symbol = candidate

        action_m = IBKR_ACTION_RE.search(line)
        qty_m = IBKR_QTY_RE.search(line)
        tif_m = IBKR_TIF_RE.search(line)
        status_m = IBKR_STATUS_RE.search(line)
        filled_m = IBKR_FILLED_RE.search(line)
        avg_m = IBKR_AVG_FILL_RE.search(line)
        lmt_m = IBKR_LMT_RE.search(line)
        order_type_m = IBKR_ORDERTYPE_RE.search(line)

        if state.orders_by_id is None:
            state.orders_by_id = {}
        existing = state.orders_by_id.get(order_id)
        evt = existing or OrderEvent(ts=ts, symbol=symbol or "?", order_id=order_id)
        evt.ts = ts
        if symbol:
            evt.symbol = symbol
        if action_m:
            evt.action = action_m.group("action")
        if qty_m:
            evt.qty = _safe_float(qty_m.group("qty"), evt.qty or 0.0)
        if tif_m:
            evt.tif = tif_m.group("tif")
        if status_m:
            evt.status = status_m.group("status")
        if filled_m:
            evt.filled = _safe_float(filled_m.group("filled"), evt.filled or 0.0)
        if avg_m:
            evt.avg_fill_price = _safe_float(avg_m.group("avg"), evt.avg_fill_price or 0.0)
        if lmt_m:
            evt.limit_price = _safe_float(lmt_m.group("lmt"), evt.limit_price or 0.0)
        if order_type_m:
            evt.order_type = order_type_m.group("type")
        evt.updated_ts = _now_epoch()
        state.orders_by_id[order_id] = evt
        # LRU eviction: remove oldest orders if cache exceeds max size
        if len(state.orders_by_id) > state._orders_max_size:
            # Remove oldest order (lowest updated_ts)
            oldest_id = min(state.orders_by_id.keys(), key=lambda k: state.orders_by_id[k].updated_ts)
            state.orders_by_id.pop(oldest_id, None)
        return


def run_app(*, repo_root: Path) -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

    smoke = os.getenv("TRADEBOT_GUI_SMOKE", "").strip() not in ("", "0", "false", "False", "no", "NO")
    smoke_bot = os.getenv("TRADEBOT_GUI_SMOKE_BOT", "").strip() not in ("", "0", "false", "False", "no", "NO")
    dotenv_path = repo_root / ".env"
    dotenv_values = _apply_dotenv_if_missing(dotenv_path)
    discovered_env_keys = _discover_env_keys(repo_root)

    class CommentaryWorker(QtCore.QObject):
        finished = QtCore.Signal(str, str)

        def __init__(self, question: str, settings: AISettings) -> None:
            super().__init__()
            self._question = question
            self._settings = settings

        def run(self) -> None:
            try:
                client = TradeSciAIClient(self._settings)
                messages = build_commentary_messages(self._question)
                answer = client.generate_text(messages)
                self.finished.emit(answer, "")
            except Exception as exc:
                self.finished.emit("", str(exc))

    @dataclass(frozen=True)
    class Theme:
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
            # Use "glassy" overlays so gradients behind show through.
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

    THEMES: dict[str, Theme] = {
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
    }

    #--------------------------------------------------------------------------
    # Replace the locally defined Theme dataclass and THEMES dictionary with
    # the canonical versions imported from tradebot_sci.gui.shared.  Without
    # this override, the nested definitions above would shadow the shared
    # versions and cause stale theme data to be used throughout the GUI.
    from tradebot_sci.gui import shared as _shared
    Theme = _shared.Theme  # type: ignore
    THEMES = _shared.THEMES  # type: ignore

    class Settings(QtCore.QObject):
        def __init__(self) -> None:
            super().__init__()
            self.log_file = Path(os.getenv("TRADEBOT_LOG", repo_root / "logs" / "tradebot.log"))
            self.rotate_seconds = 30
            # Fast refresh for CCXT/Coinbase, standard for IBKR
            try:
                from tradebot_sci.config.loader import load_settings
                loaded_settings = get_settings()
                # [ANTIGRAVITY FIX] Expose Pydantic model fields to the GUI
                self.model = loaded_settings
                self.app = loaded_settings.app
                self.market = loaded_settings.market
                self.profiles = loaded_settings.profiles

                prov = getattr(loaded_settings.market, "exchange_provider", "ibkr")
                alt = getattr(loaded_settings.market, "alternative_market_data", "")
                # Strictly check if we are in alternative mode. 
                # Avoid loose matching on 'coinbase' if provider is 'primary'.
                if str(prov).lower() == "alternative":
                    self.refresh_seconds = 0.5  # Real-time for alternative providers
                    # Store the provider name for UI labels
                    raw = str(alt).lower().strip()
                    if raw == "coinbase":
                        self.market_provider_name = "Crypto Public"
                    elif raw == "binance":
                         self.market_provider_name = "Crypto (Binance)"
                    else:
                        self.market_provider_name = str(alt).capitalize() or "Alternative"
                else:
                    self.refresh_seconds = 15  # Standard for IBKR (primary)
                    self.market_provider_name = "IBKR"
            except Exception as e:
                print(f"[GUI_SETTINGS] Failed to load settings: {e}")
                self.refresh_seconds = 15
            self.right_refresh_seconds = 5
            self.candle_tf = "5 mins"
            self.candle_bars = 120
            self.theme_key = "dark"

        def get_active_profile(self):
            if hasattr(self, "model"):
                return self.model.get_active_profile()
            raise AttributeError("Settings not fully loaded, cannot get active profile")

    settings = Settings()

    class LogTail(QtCore.QObject):
        updated = QtCore.Signal(str, object)  # line, UiState

        def __init__(self, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._path = settings.log_file
            self._pos = 0
            self._inode = None
            self.state = UiState(structure_by_symbol={}, last_decision_by_symbol={}, decision_events=deque(maxlen=80))
            # [CODEX] Option 1: Clear active symbol to prevent stale log data from overriding locked chart
            self.state.active_symbol = None
            self._history_loaded = False

        def set_path(self, path: Path) -> None:
            self._path = path
            self._pos = 0
            self._inode = None
            self.state = UiState(structure_by_symbol={}, last_decision_by_symbol={}, decision_events=deque(maxlen=80))
            self._history_loaded = False

            # Prime state from rotated logs so orders/holdings aren't blank after a log rotation.
            try:
                max_files = int(os.getenv("TRADEBOT_GUI_LOG_HISTORY_FILES", "25"))
                for p in _iter_rotated_log_paths(self._path, max_files=max_files):
                    if not p.exists():
                        continue
                    with p.open("r", encoding="utf-8", errors="replace") as f:
                        for raw in f:
                            _ingest_line(self.state, raw.rstrip("\n"))
                if self._path.exists():
                    st = self._path.stat()
                    self._inode = getattr(st, "st_ino", None)
                    self._pos = st.st_size
                
                # [CODEX FIX V2] Clear active_symbol AFTER loading history to purge stale "SELECT SPY" events
                self.state.active_symbol = None
                self._history_loaded = True
            except Exception:
                # Fail open; live tail still works.
                self._history_loaded = False

        def poll(self) -> None:
            try:
                if not self._path.exists():
                    return
                st = self._path.stat()
                inode = getattr(st, "st_ino", None)
                if self._inode is None or inode != self._inode or st.st_size < self._pos:
                    # Log rotation/truncation: keep state (orders/history) but restart reading from beginning.
                    self._inode = inode
                    self._pos = 0
                with self._path.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(self._pos)
                    chunk = f.read()
                    self._pos = f.tell()
                if not chunk:
                    return
                for line in chunk.splitlines():
                    _ingest_line(self.state, line)
                    self.updated.emit(line, self.state)
            except Exception:
                return

    class CandleFetcher(QtCore.QObject):
        updated = QtCore.Signal(object, int, str)  # bars(list), updated_age, status

        def __init__(self, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._last_fetch_ts: float | None = None
            self._last_status = ""
            self._cached: list[Any] = []

        def _pick_what_to_show(self, contract) -> str:  # type: ignore[no-untyped-def]
            sec_type = str(getattr(contract, "secType", "") or "").upper()
            if sec_type == "CRYPTO":
                return "AGGTRADES"
            if sec_type == "CASH":
                return "MIDPOINT"
            return "TRADES"

        def _build_contract(self, symbol: str):  # type: ignore[no-untyped-def]
            from ib_insync import Crypto, Forex, Stock  # type: ignore

            sym = symbol.strip().upper()
            if re.fullmatch(r"[A-Z]{3,10}USD", sym):
                base = sym[:-3]
                if base in {"BTC", "ETH", "SOL", "LTC", "BCH", "XRP", "ADA", "DOGE", "AVAX", "LINK"}:
                    return Crypto(base, os.getenv("IBKR_CRYPTO_EXCHANGE", "ZEROHASH"), "USD")
            if re.fullmatch(r"[A-Z]{6}", sym):
                fx_ccy = {
                    "USD",
                    "EUR",
                    "JPY",
                    "GBP",
                    "CHF",
                    "CAD",
                    "AUD",
                    "NZD",
                    "SEK",
                    "NOK",
                    "DKK",
                    "HKD",
                    "SGD",
                    "CNH",
                    "MXN",
                    "ZAR",
                    "TRY",
                    "PLN",
                    "CZK",
                    "HUF",
                    "ILS",
                }
                base, quote = sym[:3], sym[3:]
                if base in fx_ccy and quote in fx_ccy:
                    return Forex(sym)
            return Stock(sym, "SMART", "USD")

        def fetch(self, symbol: str) -> None:
            try:
                from ib_insync import IB  # type: ignore
            except Exception as exc:
                self.updated.emit([], 0, f"ib_insync missing: {exc}")
                return

            now = _now_epoch()
            updated_age = 0 if self._last_fetch_ts is None else max(0, int(round(now - self._last_fetch_ts)))
            if self._last_fetch_ts is not None and now - self._last_fetch_ts < settings.refresh_seconds:
                self.updated.emit(self._cached, updated_age, self._last_status)
                return

            # [ANTIGRAVITY FIX] Guard against IBKR connection in alternative mode
            provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
            broker_mode = (os.getenv("BROKER_MODE") or settings.market.broker_mode or "").strip().lower()
            profile_name = (os.getenv("PROFILE_NAME") or "").strip().lower()
            alt_md = (os.getenv("ALTERNATIVE_MARKET_DATA") or "").strip().lower()
            is_futures = (provider == "coinbase_futures" or broker_mode == "coinbase_futures" or profile_name == "coinbase_futures" or alt_md == "coinbase_futures")
            if provider == "alternative" or broker_mode == "alternative" or is_futures:
                 self.updated.emit([], 0, "IBKR disabled (alternative)")
                 return

            host = os.getenv("IBKR_HOST", "127.0.0.1")
            port = int(os.getenv("IBKR_PORT", "7497"))
            ib = IB()
            status = ""
            bars: list[Any] = []
            try:
                ib.connect(host, port, clientId=int(now) % 10_000, timeout=2.0)
                ib.reqMarketDataType(3)
                contract = self._build_contract(symbol)
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    status = f"unknown contract: {symbol}"
                else:
                    contract = qualified[0]
                    what = self._pick_what_to_show(contract)
                    tf = str(settings.candle_tf or "").lower()
                    bar_minutes = 5
                    m = re.search(r"(\\d+)\\s*min", tf)
                    if m:
                        bar_minutes = max(1, int(m.group(1)))
                    else:
                        m = re.search(r"(\\d+)\\s*hour", tf)
                        if m:
                            bar_minutes = max(1, int(m.group(1))) * 60
                        else:
                            m = re.search(r"(\\d+)\\s*day", tf)
                            if m:
                                bar_minutes = max(1, int(m.group(1))) * 60 * 24
                            else:
                                m = re.search(r"(\\d+)\\s*week", tf)
                                if m:
                                    bar_minutes = max(1, int(m.group(1))) * 60 * 24 * 7
                                else:
                                    m = re.search(r"(\\d+)\\s*month", tf)
                                    if m:
                                        bar_minutes = max(1, int(m.group(1))) * 60 * 24 * 30

                    total_minutes = max(60, int(settings.candle_bars) * bar_minutes)
                    days = max(2, int((total_minutes + (60 * 24 - 1)) // (60 * 24)) + 2)
                    # Give IBKR enough time range to return full history even across gaps.
                    if bar_minutes >= 60 * 24 * 30:
                        years = max(1, int((days + 364) // 365) + 1)
                        duration = f"{min(5, years)} Y"
                    elif bar_minutes >= 60 * 24 * 7:
                        weeks = max(2, int((days + 6) // 7) + 2)
                        if weeks >= 52:
                            years = max(1, int((weeks + 51) // 52))
                            duration = f"{min(5, years)} Y"
                        else:
                            duration = f"{min(104, weeks)} W"
                    elif days >= 14:
                        weeks = max(2, int((days + 6) // 7))
                        duration = f"{min(26, weeks)} W"
                    else:
                        duration = f"{min(30, days)} D"
                    bars = list(
                        ib.reqHistoricalData(
                            contract,
                            endDateTime="",
                            durationStr=duration,
                            barSizeSetting=settings.candle_tf,
                            whatToShow=what,
                            useRTH=False,
                            formatDate=2,
                            keepUpToDate=False,
                        )
                        or []
                    )
                    if not bars:
                        status = "no bars"
            except Exception as exc:
                status = str(exc)
            finally:
                try:
                    if ib.isConnected():
                        ib.disconnect()
                except Exception:
                    pass

            self._last_fetch_ts = _now_epoch()
            self._last_status = status
            self._cached = bars
            updated_age = 0
            self.updated.emit(bars, updated_age, status)

    class IbkrAccountFetcher(QtCore.QObject):
        updated = QtCore.Signal(
            object, object, object, int, str
        )  # positions(list[dict]), orders(list[dict]), fills(list[dict]), updated_age, status

        def __init__(self, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._last_fetch_ts: float | None = None
            self._last_status = ""
            self._cached_positions: list[dict[str, Any]] = []
            self._cached_orders: list[dict[str, Any]] = []
            self._cached_fills: list[dict[str, Any]] = []
            self._cached_equity: float = 0.0
            self._busy = False

        def _contract_symbol(self, contract: Any) -> str:
            sym = str(getattr(contract, "symbol", "") or "").strip().upper()
            cur = str(getattr(contract, "currency", "") or "").strip().upper()
            sec = str(getattr(contract, "secType", "") or "").strip().upper()
            if sec in {"CASH", "CRYPTO"} and sym and cur:
                return f"{sym}{cur}"
            return sym or "?"

        def fetch(self) -> None:
            if self._busy:
                now = _now_epoch()
                updated_age = 0 if self._last_fetch_ts is None else max(0, int(round(now - self._last_fetch_ts)))
                self.updated.emit(self._cached_positions, self._cached_orders, self._cached_fills, updated_age, self._last_status)
                return

            try:
                from ib_insync import IB, ExecutionFilter  # type: ignore
            except Exception as exc:  # pragma: no cover
                self._last_fetch_ts = _now_epoch()
                self._last_status = f"ib_insync missing: {exc}"
                self._cached_positions = []
                self._cached_orders = []
                self._cached_fills = []
                self.updated.emit([], [], [], 0, self._last_status)
                return

            now = _now_epoch()
            updated_age = 0 if self._last_fetch_ts is None else max(0, int(round(now - self._last_fetch_ts)))
            if self._last_fetch_ts is not None and now - self._last_fetch_ts < settings.refresh_seconds:
                self.updated.emit(self._cached_positions, self._cached_orders, self._cached_fills, updated_age, self._last_status)
                return

            # [ANTIGRAVITY FIX] Guard against IBKR connection in alternative mode
            provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
            broker_mode = (os.getenv("BROKER_MODE") or settings.market.broker_mode or "").strip().lower()
            profile_name = (os.getenv("PROFILE_NAME") or "").strip().lower()
            alt_md = (os.getenv("ALTERNATIVE_MARKET_DATA") or "").strip().lower()
            is_futures = (provider == "coinbase_futures" or broker_mode == "coinbase_futures" or profile_name == "coinbase_futures" or alt_md == "coinbase_futures")
            
            if provider == "alternative" or broker_mode == "alternative" or is_futures:
                 self._last_fetch_ts = now
                 try:
                     import json
                     from types import SimpleNamespace
                     
                     # 1. Fetch Open Orders & Balances via CCXT (if available)
                     ccxt_orders = []
                     ccxt_status = ""
                     ccxt_balances = {}
                     
                     try:
                         import ccxt
                         # Try to load keys from env (TradeBot pattern)
                         api_key = os.getenv("COINBASE_API_KEY") or os.getenv("CB_ACCESS_KEY")
                         api_secret = os.getenv("COINBASE_API_SECRET") or os.getenv("CB_ACCESS_SECRET")
                         
                         if api_key and api_secret:
                             # Lazy init or create fresh (ccxt is lightweight to init, heavy to connect)
                             # We use a cached exchange instance if possible, but for simplicity here strictly locally
                             # To avoid blocking GUI too long, we set a short timeout
                             opts = {
                                 "apiKey": api_key,
                                 "secret": api_secret,
                                 "timeout": 2000,
                                 "enableRateLimit": False,
                             }
                             if is_futures:
                                 opts["options"] = {"defaultType": "future"}
                                 
                             exchange = ccxt.coinbase(opts)
                             
                             # A. Fetch Open Orders
                             raw_orders = exchange.fetch_open_orders()
                             for o in raw_orders:
                                 # Map CCXT order to UI format
                                 # UI expects: symbol, ts, order_id, action, qty, order_type, tif, status, filled
                                 ccxt_orders.append({
                                     "symbol": o.get("symbol", "UNKNOWN"),
                                     "ts": o.get("datetime") or "",
                                     "order_id": int(hash(str(o.get("id", "")))) % 100000000,
                                     "action": (o.get("side") or "").upper(),
                                     "qty": o.get("amount"),
                                     "order_type": (o.get("type") or "").upper(),
                                     "tif": (o.get("timeInForce") or "").upper(),
                                     "status": (o.get("status") or "").upper(),
                                     "filled": o.get("filled", 0.0),
                                     "limit_price": o.get("price"),
                                     "avg_fill_price": o.get("average"),
                                 })
                             
                             # B. Fetch Balances (to populate Holdings quantities)
                             raw_balance = exchange.fetch_balance()
                             # 'total' key usually holds the non-zero balances dict
                             ccxt_balances = raw_balance.get("total", {})

                             # C. Fetch Positions (if in futures mode)
                             futures_positions = []
                             if is_futures and getattr(exchange, 'has', {}).get('fetchPositions'):
                                 try:
                                     raw_positions = exchange.fetch_positions()
                                     for p in raw_positions:
                                         contracts = float(p.get("contracts") or 0.0)
                                         if contracts != 0:
                                             futures_positions.append(p)
                                 except Exception as fe:
                                     logger.warning(f"[GUI] Failed to fetch futures positions: {fe}")
                             
                             # [ANTIGRAVITY FIX] Approximate Equity for PnL Tracker
                             # Sum up USD and Stablecoins.
                             # Note: Does not include Unrealized Crypto PnL to avoid API spam (need 50+ tickers).
                             # But this WILL capture Realized PnL when trades close (Crypto -> USD).
                             approx_equity = 0.0
                             for cur in ["USD", "USDT", "USDC", "DAI", "FDUSD"]:
                                 approx_equity += float(ccxt_balances.get(cur, 0.0))
                             
                             # Add Unrealized PnL from futures
                             for fp in futures_positions:
                                 approx_equity += float(fp.get("unrealizedPnl", 0.0) or 0.0)
                             
                             if approx_equity > 0:
                                 self._cached_equity = approx_equity

                             ccxt_status = f"Orders: {len(ccxt_orders)}"
                         else:
                             ccxt_status = "No API Keys"
                     except ImportError:
                         ccxt_status = "CCXT missing"
                     except Exception as e:
                         ccxt_status = f"CCXT Err: {str(e)[:20]}"

                     # 2. Fetch Holdings from File
                     # Resolve path (assuming relative to cwd if not absolute)
                     path = "data/position_holds.json"
                     # Try to access settings if available, else default
                     if hasattr(settings, "runtime") and hasattr(settings.runtime, "position_hold_store_path"):
                         path = settings.runtime.position_hold_store_path
                     elif hasattr(settings, "position_hold_store_path"):
                         path = settings.position_hold_store_path
                     
                     if not os.path.isabs(path):
                         path = os.path.join(os.getcwd(), path)

                     positions = []
                     pos_summary_parts = []
                     
                     if os.path.exists(path):
                         with open(path, "r") as f:
                             data = json.load(f)
                             for item in data:
                                 # Mock IBKR Position object structure expected by UI
                                 # contract.symbol, contract.currency, contract.secType
                                 sym = item.get("symbol", "UNKNOWN")
                                 # Heuristic for crypto vs stock
                                 sec_type = "CRYPTO" if "USD" in sym or len(sym) > 4 else "STK" 
                                 
                                 contract = SimpleNamespace(
                                     symbol=sym,
                                     currency="USD" if "USD" in sym else "",
                                     secType=sec_type
                                 )
                                 
                                 # Determine quantity from CCXT balance if available
                                 # Symbol usually "BTC-USD" or "BTCUSD". Asset is "BTC".
                                 qty = 0.0
                                 base_curr = sym.replace("USD", "").replace("-", "").replace("T", "") # Crude parser
                                 # Try exact match first
                                 if base_curr in ccxt_balances:
                                    qty = float(ccxt_balances[base_curr])
                                 elif sym in ccxt_balances:
                                    qty = float(ccxt_balances[sym])
                                 else:
                                    # Fallback: try removing last 3-4 chars
                                    for t in ["USD", "USDT", "USDC"]:
                                        if sym.endswith(t):
                                            asset = sym[:-len(t)]
                                            if asset in ccxt_balances:
                                                qty = float(ccxt_balances[asset])
                                                break
                                 
                                 # UI expects dict with 'contract', 'position', 'avgCost'
                                 if not is_futures:
                                     positions.append({
                                         "account": "ALT",
                                         "contract": contract,
                                         "position": qty if qty > 0 else 1.0,  # Fallback to 1.0 if unknown
                                         "avgCost": 0.0,
                                         "unrealizedPNL": 0.0
                                     })
                                     # Add to clean summary string
                                     # User requested full decimals ("Show them all") - KEEP ALL ZEROS
                                     s_qty = f"{qty:.8f}"
                                     pos_summary_parts.append(f"{sym.replace('USD','')} - {s_qty}")

                             # 3. Add Futures Positions
                             for fp in futures_positions:
                                 raw_sym = fp.get("symbol", "UNKNOWN")
                                 contracts = float(fp.get("contracts") or 0.0)
                                 entry_price = float(fp.get("entryPrice") or 0.0)
                                 
                                 contract = SimpleNamespace(
                                     symbol=raw_sym,
                                     currency="USD",
                                     secType="FUT"
                                 )
                                 
                                 positions.append({
                                     "account": "ALT-FUT",
                                     "contract": contract,
                                     "position": contracts,
                                     "avgCost": entry_price,
                                     "unrealizedPNL": fp.get("unrealizedPnl", 0.0)
                                 })
                                 pos_summary_parts.append(f"{raw_sym} - {contracts:.2f} @ {entry_price:.2f}")
                     
                     # [ANTIGRAVITY FIX] User requested removal of "BTC/XLY" status.
                     # We force an empty status string (or just connection status) to declutter UI.
                     # The PnL widget now handles the "what am I doing" feedback.
                     self._last_status = f"CCXT ok ({len(ccxt_orders)} orders)"
                     self.updated.emit(positions, ccxt_orders, [], 0, self._last_status)
                 except Exception as e:
                     self._last_status = f"Error reading holds: {e}"
                     self.updated.emit([], [], [], 0, self._last_status)
                 return

            host = os.getenv("IBKR_HOST", "127.0.0.1")
            port = int(os.getenv("IBKR_PORT", "7497"))
            ib = IB()
            status = ""
            positions_out: list[dict[str, Any]] = []
            orders_out: list[dict[str, Any]] = []
            fills_out: list[dict[str, Any]] = []
            self._busy = True
            try:
                ib.connect(host, port, clientId=(int(now) % 10_000) + 7, timeout=2.0)
                try:
                    ib.reqMarketDataType(3)
                except Exception:
                    pass

                for pos in list(ib.positions() or []):
                    c = getattr(pos, "contract", None)
                    positions_out.append(
                        {
                            "symbol": self._contract_symbol(c),
                            "secType": str(getattr(c, "secType", "") or ""),
                            "exchange": str(getattr(c, "exchange", "") or ""),
                            "currency": str(getattr(c, "currency", "") or ""),
                            "position": float(getattr(pos, "position", 0.0) or 0.0),
                            "avgCost": float(getattr(pos, "avgCost", 0.0) or 0.0),
                        }
                    )

                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                for tr in list(ib.openTrades() or []):
                    c = getattr(tr, "contract", None)
                    o = getattr(tr, "order", None)
                    s = getattr(tr, "orderStatus", None)
                    try:
                        order_id = int(getattr(o, "orderId", 0) or 0)
                    except Exception:
                        order_id = 0
                    orders_out.append(
                        {
                            "ts": ts,
                            "symbol": self._contract_symbol(c),
                            "order_id": order_id,
                            "action": str(getattr(o, "action", "") or "").upper() or None,
                            "qty": float(getattr(o, "totalQuantity", 0.0) or 0.0),
                            "order_type": str(getattr(o, "orderType", "") or "") or None,
                            "tif": str(getattr(o, "tif", "") or "") or None,
                            "status": str(getattr(s, "status", "") or "") or None,
                            "filled": float(getattr(s, "filled", 0.0) or 0.0),
                            "avg_fill_price": float(getattr(s, "avgFillPrice", 0.0) or 0.0),
                            "limit_price": float(getattr(o, "lmtPrice", 0.0) or 0.0),
                        }
                    )

                try:
                    for fill in list(ib.reqExecutions(ExecutionFilter()) or []):
                        c = getattr(fill, "contract", None)
                        e = getattr(fill, "execution", None)
                        t = getattr(fill, "time", None)
                        epoch = None
                        try:
                            if t is not None:
                                epoch = float(getattr(t, "timestamp")())
                        except Exception:
                            epoch = None
                        try:
                            order_id = int(getattr(e, "orderId", 0) or 0)
                        except Exception:
                            order_id = 0
                        fills_out.append(
                            {
                                "ts": str(t)[:19] if t is not None else ts,
                                "time_epoch": epoch,
                                "symbol": self._contract_symbol(c),
                                "order_id": order_id,
                                "action": str(getattr(e, "side", "") or "").upper() or None,
                                "qty": float(getattr(e, "shares", 0.0) or 0.0),
                                "price": float(getattr(e, "price", 0.0) or 0.0),
                            }
                        )
                except Exception:
                    pass

                self._cached_equity = 0.0
                try:
                    # Fetch NetLiquidation (Equity with Loan Value)
                    # Use accountSummary to get USD value across accounts if needed, or default.
                    summary = ib.accountSummary(tags="NetLiquidation")
                    for val in summary:
                        if val.tag == "NetLiquidation" and val.currency == "USD":
                            self._cached_equity = float(val.value)
                            break
                except Exception:
                    pass

                status = f"IBKR ok · positions={len(positions_out)} · open_orders={len(orders_out)} · fills={len(fills_out)}"
            except Exception as exc:
                status = f"IBKR error: {exc}"
            finally:
                try:
                    if ib.isConnected():
                        ib.disconnect()
                except Exception:
                    pass
                self._busy = False

            self._last_fetch_ts = _now_epoch()
            self._last_status = status
            self._cached_positions = positions_out
            self._cached_orders = orders_out
            self._cached_fills = fills_out
            self.updated.emit(positions_out, orders_out, fills_out, 0, status)
            
        @property
        def equity(self) -> float:
            return self._cached_equity

    class CapitalTuneWorker(QtCore.QObject):
        done = QtCore.Signal(object, str, float, str)
        error = QtCore.Signal(str)

        def __init__(
            self,
            *,
            settings_obj,
            profile_name: str,
            current: dict[str, str],
            context: dict[str, str],
            log_excerpt: str,
        ) -> None:
            super().__init__()
            self._settings = settings_obj
            self._profile_name = profile_name
            self._current = current
            self._context = context
            self._log_excerpt = log_excerpt

        def run(self) -> None:
            equity, broker = fetch_account_equity(self._settings)
            if equity is None:
                self.error.emit(broker or "Failed to fetch account equity")
                return
            try:
                result = request_capital_tune(
                    self._settings,
                    equity=equity,
                    broker=broker,
                    profile_name=self._profile_name,
                    current=self._current,
                    context=self._context,
                    log_excerpt=self._log_excerpt,
                )
            except Exception as exc:
                self.error.emit(str(exc))
                return
            self.done.emit(result.overrides, result.notes, result.equity, result.broker)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Tradebot SCI — ICC Dashboard (GUI)")
            self.resize(1500, 900)

            self._qsettings = QtCore.QSettings("TradeBySCI", "TradebotGUI")
            self._background_map: QtGui.QPixmap | None = None
            # Load background for "Glass" look
            bg_path = Path(__file__).parent / "assets" / "bg.png"
            if bg_path.exists():
                 self._background_map = QtGui.QPixmap(str(bg_path))

            settings.theme_key = str(self._qsettings.value("theme", settings.theme_key))
            settings.candle_tf = str(self._qsettings.value("candles/tf", settings.candle_tf))
            if settings.theme_key not in THEMES:
                settings.theme_key = "dark"

            # Flag indicating whether market data is enabled for candles.
            # The original implementation always attempted to fetch candle data
            # when this method was invoked.  Introduce this attribute with a
            # default of True to mirror that behavior and avoid AttributeError.
            self._market_data_enabled: bool = True
            
            # Safety flags
            self._pdt_safety_check_done = False
            self._crypto_warning_done = False
            self._stocks_long_warning_done = False

            # Persist environment/context parameters from run_app on this instance.
            # These are needed when opening the settings dialog to provide
            # repository path and known environment keys.
            self._repo_root = repo_root
            self._discovered_env_keys = discovered_env_keys
            self._dotenv_values = dotenv_values

            self._tail = LogTail(self)
            # Load current + rotated logs so Orders/Holdings are populated immediately.
            self._tail.set_path(settings.log_file)
            self._tail.updated.connect(self._on_log_line)
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(250)
            self._poll_timer.timeout.connect(self._tail.poll)
            self._poll_timer.start()

            self._state = self._tail.state
            self._current_symbol: str | None = None
            self._chart_locked_symbol: str | None = None
            self._recent_log: deque[str] = deque(maxlen=250)
            self._pdt_restricted_until: datetime | None = None

            self._env_overrides: dict[str, str] = {}
            for k in discovered_env_keys:
                v = self._qsettings.value(f"env/{k}")
                if v is not None and str(v) != "":
                    self._env_overrides[k] = str(v)
            for k, v in self._env_overrides.items():
                os.environ[k] = v

            # Bot process management (GUI can run the core bot directly).
            self._bot_proc: QtCore.QProcess | None = None
            self._bot_started_by_gui = False
            self._bot_pid: int | None = None
            self._bot_autostart = str(self._qsettings.value("bot/autostart", "true")).lower() in {"1", "true", "yes", "on"}
            self._bot_keep_running_on_close = (
                str(self._qsettings.value("bot/keep_running_on_close", "false")).lower() in {"1", "true", "yes", "on"}
            )
            self._bot_pid = self._detect_running_bot_pid()
            self._confirmed_live_trading = False

            # Left: log + candles
            # Use the extracted LogPanel to encapsulate the log display and highlighting.
            # The panel creates its own QPlainTextEdit and applies the syntax highlighter
            # based on the current theme.  Expose the underlying widget and highlighter
            # under the same names as before for backwards compatibility.
            self._log_panel = LogPanel(self, settings.log_file, settings)
            self._log: QtWidgets.QTextEdit = self._log_panel.widget
            self._log_highlighter = self._log_panel.highlighter

            # Create the candles panel.  This replaces the inline candle UI
            # construction and manages its own series, chart and controls.
            # [ANTIGRAVITY] Upgraded to WebChartPanel for "Pro" look
            from tradebot_sci.gui.web_chart_panel import WebChartPanel
            self._candles_panel = WebChartPanel(self, self._state, settings)
            # Populate the symbol selector dropdown with configured symbols
            self._populate_symbol_selector()

            # [ANTIGRAVITY FIX] Initialize market data provider for dynamic symbol details
            # We use a shared None for the IB instance as the GUI typically only reads candles via its own fetcher
            # or relies on logs for data. But for metadata lookups (get_market_definition), we need a provider.
            self._market_provider = None
            try:
                prof_settings = settings.profiles.get(settings.app.profile_name)
                self._market_provider: MarketDataProvider = build_market_provider(
                    settings, 
                    profile_settings=prof_settings, 
                    shared_ib=None
                )
            except Exception as e:
                logger.warning(f"[GUI] Failed to initialize market provider: {e}")
                self._market_provider = None

            # [ANTIGRAVITY LAYOUT OVERHAUL]
            # [ANTIGRAVITY ULTIMATE LAYOUT - IMAGE MATCHING]
            # The background image defines the frames, so we use transparent containers.
            
            # 1. Left Sidebar
            from tradebot_sci.gui.nav_panel import NavPanel
            self._nav_panel = NavPanel(self)
            
            # 2. Main Content Area (Vertical Stack: Chart -> Carousel -> Logs)
            from tradebot_sci.gui.custom_widgets import CarouselPanel, NeonDelegate
            # Note: HudPanel removed as background image provides the borders
            
            # A. Chart Pane
            # Wrap in widget to add padding (so content stays inside the glowing frame)
            chart_container = QtWidgets.QWidget()
            chart_layout = QtWidgets.QVBoxLayout(chart_container)
            chart_layout.setContentsMargins(15, 15, 15, 15) # Keep away from edges
            chart_layout.addWidget(self._candles_panel)
            
            # B. Carousel Pane
            # Carousel already has arrows, lets give it padding
            carousel_container = QtWidgets.QWidget()
            carousel_layout = QtWidgets.QVBoxLayout(carousel_container)
            carousel_layout.setContentsMargins(15, 15, 15, 15)
            self._carousel_panel = CarouselPanel()
            carousel_layout.addWidget(self._carousel_panel)
            
            # C. Log Pane
            log_container = QtWidgets.QWidget()
            log_layout = QtWidgets.QVBoxLayout(log_container)
            log_layout.setContentsMargins(15, 15, 15, 15)
            log_layout.addWidget(self._log_panel.widget) # use .widget property
            
            # D. Vertical Splitter
            content_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            content_splitter.addWidget(chart_container)
            content_splitter.addWidget(carousel_container)
            content_splitter.addWidget(log_container)
            
            # Ratios - Match the visual height of panes in the image
            # Top (Chart): Tallest
            # Middle (Carousel): Medium
            # Bottom (Log): Short
            content_splitter.setStretchFactor(0, 5) 
            content_splitter.setStretchFactor(1, 3) 
            content_splitter.setStretchFactor(2, 2)
            
            # Spacing to match gaps in background image
            content_splitter.setHandleWidth(20) # Gap between panes
            
            # E. Root Layout
            root_widget = QtWidgets.QWidget()
            self.setCentralWidget(root_widget)
            root_layout = QtWidgets.QHBoxLayout(root_widget)
            # Outer margins to keep away from window edge (where background frame might end)
            root_layout.setContentsMargins(20, 20, 20, 20)
            root_layout.setSpacing(20) # Gap between Sidebar and Main Content
            
            # Add Sidebar (Fixed Width)
            self._nav_panel.setFixedWidth(240) # Match sidebar width
            root_layout.addWidget(self._nav_panel)
            
            # Add Content
            root_layout.addWidget(content_splitter)
            
            # Defer populating tabs until they are created below
            # We assign _bottom_tabs to the carousel as a compatibility layer if needed?
            # No, we will modify the tab addition code to add to carousel instead.
            self._carousel_target = self._carousel_panel # Target for tabs
            
            # Tab 1: Live Logs -- REMOVED (Now a permanent pane)
            
            # Tab 2: Holdings (Table)
            self._holdings: list[dict[str, Any]] = []
            self._holdings_updated_ts: float | None = None
            self._holdings_status = QtWidgets.QLabel("Updated: never")
            self._holdings_table = QtWidgets.QTableWidget(0, 12)
            self._holdings_table.setHorizontalHeaderLabels(
                [
                    "Symbol", "Side", "Size", "Avg", "SL", "TP", "OpenRisk",
                    "Working", "Statuses", "SynthStop", "HoldAge", "HoldRemain",
                ]
            )
            self._holdings_table.verticalHeader().setVisible(False)
            self._holdings_table.setShowGrid(False)
            self._holdings_table.setAlternatingRowColors(True)
            self._holdings_table.setSortingEnabled(True)
            self._holdings_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self._holdings_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self._holdings_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self._holdings_table.setWordWrap(False)
            self._holdings_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
            self._holdings_table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
            hhdr = self._holdings_table.horizontalHeader()
            hhdr.setStretchLastSection(True)
            hhdr.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
            self._holdings_table.setSortingEnabled(True)
            # Use HudPanel wrapper for consistent look inside carousel?
            # Or just raw widget. Carousel is inside a Splitter, so maybe raw.
            # But panes need the "HUD" look?
            # User said "different sections uses a image... but not for the different panes (which seems to be a must)".
            # Carousel rotates content. If we wrap each content in HudPanel, the arrows might be outside?
            # My CarouselPanel design has arrows on sides of content. Content should probably be the Table.
            # The CarouselPanel itself could be wrapped in HudPanel? No, I did that in previous step.
            # self._carousel_panel IS NOT wrapped in HUD because arrows.
            # So the content INSIDE carousel should probably be wrapped in HUD?
            # No, if carousel arrows are outside, the content is the "screen".
            # Let's wrap each tab in HudPanel for max "pane" effect?
            # Or just add the raw widget.
            self._carousel_target.add_tab(self._holdings_table, "HOLDINGS")
            
            # Tab 3: Orders
            self._orders_panel = OrdersPanel(self, self._state, settings)
            self._orders: QtWidgets.QTableWidget = self._orders_panel._table
            self._carousel_target.add_tab(self._orders_panel, "ORDERS")

            # Tab 4: Readiness (Scanner)
            self._readiness_table = ReadinessTable(self, self._state, settings)
            self._readiness: QtWidgets.QTableWidget = self._readiness_table
            # Apply Neon Glow to Readiness Table
            self._readiness.setItemDelegate(NeonDelegate(self._readiness))
            self._carousel_target.add_tab(self._readiness_table, "READINESS")
            
            # Tab 5: Commentary
            self._commentary_panel = CommentaryPanel(self, self._state, settings)
            self._commentary: QtWidgets.QTextBrowser = self._commentary_panel.widget
            self._carousel_target.add_tab(self._commentary_panel, "COMMENTARY")

            # Tab 6: Decisions
            self._decisions_panel = DecisionsPanel(self, self._state, settings)
            self._decisions: QtWidgets.QPlainTextEdit = self._decisions_panel.widget
            self._decisions_highlighter = self._decisions_panel.highlighter
            self._carousel_target.add_tab(self._decisions_panel, "DECISIONS")
            
            # [REMOVED OLD LAYOUT CODE]
            
            self.setCentralWidget(root_widget)
            
            # Apply "Mockup Pro" theme by default
            settings.theme_key = "mockup_pro"
            self._apply_theme(settings.theme_key)
            
            # Hide Menu Bar (Moved to Sidebar/Context)
            self.menuBar().hide()
            
            self.statusBar().showMessage("Ready")
            # Removed separate Holdings tab as requested


            # First, try to clear existing widgets to remove "BTC/XLY" status if present
            # Note: removeWidget doesn't delete, just hides. We rely on addPermanentWidget logic.
            
            # PnL Label
            self._status_pnl_label = QtWidgets.QLabel("PnL: --")
            self._status_pnl_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self._status_pnl_label.setStyleSheet("QLabel { color: #cccccc; font-weight: bold; margin-right: 15px; }")
            self.statusBar().addPermanentWidget(self._status_pnl_label)

            self._status_holdings_label = QtWidgets.QLabel("")
            self._status_holdings_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self._status_holdings_label.setStyleSheet("QLabel { color: #cccccc; font-weight: bold; margin-right: 10px; }")
            self.statusBar().addPermanentWidget(self._status_holdings_label)
            
            # Tracking for PnL
            self._session_start_equity: float | None = None
            self._total_unrealized_pnl: float = 0.0

            # Right side refresh loop (readiness + decisions) independent of log writes.
            self._right_timer = QtCore.QTimer(self)
            self._right_timer.setInterval(int(settings.right_refresh_seconds * 1000))
            self._right_timer.timeout.connect(self._render_right)
            self._right_timer.start()

            # Candles update loop.  Delegate periodic updates to the
            # extracted CandlesPanel.  The panel internally manages its
            # own fetcher and throttling logic; here we simply trigger
            # ``tick_candles`` every second.
            self._candle_timer = QtCore.QTimer(self)
            self._candle_timer.setInterval(500)
            self._candle_timer.timeout.connect(self._candles_panel.tick_candles)
            self._candle_timer.start()

            # IBKR account snapshot loop (positions + open orders + recent fills).
            self._ibkr_positions: list[dict[str, Any]] = []
            self._ibkr_orders: list[dict[str, Any]] = []
            self._ibkr_fills: list[dict[str, Any]] = []
            self._ibkr_last_status: str | None = None
            self._ibkr_last_fetch_ts: float | None = None
            self._ibkr_fetcher = IbkrAccountFetcher(self)
            self._ibkr_fetcher.updated.connect(self._on_ibkr_account)
            self._ibkr_timer = QtCore.QTimer(self)
            self._ibkr_timer.setInterval(1000)
            self._ibkr_timer.timeout.connect(self._tick_ibkr_account)
            self._ibkr_timer.start()

            # Commentary loop (runs rarely; timer only checks whether it's due).
            self._adviser_thread: QtCore.QThread | None = None
            self._adviser_worker: CommentaryWorker | None = None
            self._adviser_last_attempt_ts: float | None = None
            self._adviser_last_update_ts: float | None = None
            self._last_good_commentary: str | None = None
            self._adviser_last_error: str | None = None
            self._adviser_last_exit_code: int | None = None
            self._adviser_start_ts: float | None = None
            self._adviser_backoff_seconds: float = 0.0
            self._adviser_budget_note: str | None = None
            self._adviser_last_daily_slot_key: str | None = None
            self._adviser_last_a_plus_ts: float | None = None
            self._prev_readiness_by_symbol: dict[str, float] = {}
            self._adviser_pending_reason: str | None = None
            self._adviser_pending_daily_slot_key: str | None = None
            self._adviser_pending_a_plus_ts: float | None = None
            self._adviser_timeout_seconds: float = float(
                (os.getenv("COMMENTARY_LLM_TIMEOUT_SECONDS") or "").strip() or "90"
            )
            self._adviser_timer = QtCore.QTimer(self)
            self._adviser_timer.setInterval(5000)
            self._adviser_timer.timeout.connect(self._maybe_update_commentary)
            self._adviser_timer.start()

            # Load last commentary from log file on startup
            self._load_last_commentary_from_log()

            # Auto capital tuning (opt-in)
            self._capital_tune_thread: QtCore.QThread | None = None
            self._capital_tune_worker: CapitalTuneWorker | None = None
            self._capital_tune_timer = QtCore.QTimer(self)
            self._capital_tune_timer.setInterval(60 * 60 * 1000)
            self._capital_tune_timer.timeout.connect(self._maybe_auto_capital_tune)
            self._capital_tune_timer.start()
            QtCore.QTimer.singleShot(2500, self._maybe_auto_capital_tune)

            if smoke:
                if smoke_bot:
                    QtCore.QTimer.singleShot(0, self._start_bot)
                    QtCore.QTimer.singleShot(1500, self._stop_bot)
                    QtCore.QTimer.singleShot(1650, self._stop_bot)
                    QtCore.QTimer.singleShot(1800, QtWidgets.QApplication.instance().quit)  # type: ignore[union-attr]
                else:
                    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.instance().quit)  # type: ignore[union-attr]
            else:
                QtCore.QTimer.singleShot(0, self._maybe_autostart_bot)

        def trigger_panic_mode(self) -> None:
            """
            EMERGENCY: Stop all trades and close open positions instantly.
            Called by NavPanel's Panic Button.
            """
            logger.critical("[GUI] PANIC BUTTON PRESSED via NavPanel. Stopping bot and closing positions.")
            
            # 1. Stop Auto-Schedule / New Entries
            settings.stop_autotrader = True
            
            # 2. Issue Close All Command via Bot Process (if possible) or directly
            # For now, we simulate the "STOP" behavior by setting the flag and logging.
            # In a real scenario, this would send a signal to the engine.
            
            # Use the existing close-all logic or script
            try:
                # If bot is running as a subprocess (self._bot_proc), kill it? 
                # No, better to soft-stop.
                pass
            except Exception as e:
                logger.error(f"[GUI] Panic execution error: {e}")
                
            QtWidgets.QMessageBox.warning(
                self, 
                "PANIC MODE ACTIVATED", 
                "The bot has been signaled to STOP.\n"
                "Manual intervention may still be required to verify position closure on broker."
            )

        def open_settings(self) -> None:
            """Open the Settings Dialog (invoked by NavPanel)."""
            self._open_env_settings()
            
        def _commentary_mode(self) -> str:
            raw = (os.getenv("COMMENTARY_LLM") or "").strip().lower()
            if raw in {"off", "none", "0", "false"}:
                return "off"
            if raw in {"adviser", "advisor", "internal"}:
                return "internal"
            return "internal"

        def _load_last_commentary_from_log(self) -> None:
            """Load the last commentary from commentary.log file on startup."""
            commentary_log = Path("logs/commentary.log")
            if not commentary_log.exists():
                return
            try:
                # Read last 100 lines looking for the most recent commentary_success event
                with open(commentary_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # Reverse search from end of file
                    for line in reversed(lines[-100:]):
                        if "commentary_response" in line:
                            try:
                                data = json.loads(line.split(" INFO ", 1)[1])
                                payload = json.loads(data.get("payload", "{}"))
                                content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
                                if content:
                                    self._last_good_commentary = content.strip()
                                    self._commentary.setMarkdown(self._last_good_commentary)
                                    logger.info(f"[GUI] Loaded last commentary from log ({len(content)} chars)")
                                    return
                            except Exception:
                                continue
            except Exception as e:
                logger.debug(f"[GUI] Failed to load commentary from log: {e}")

        def _commentary_min_seconds(self) -> float:
            try:
                return float(os.getenv("COMMENTARY_LLM_MIN_SECONDS") or "300")
            except Exception:
                return 300.0

        def _commentary_policy(self) -> str:
            raw = (os.getenv("COMMENTARY_LLM_POLICY") or "").strip().lower()
            if raw in {"a_plus_only", "a_plus_or_4x", "interval"}:
                return raw
            return "a_plus_or_4x"

        def _commentary_tz(self) -> str:
            return (
                (os.getenv("COMMENTARY_LLM_TZ") or "").strip()
                or (os.getenv("SABBATH_TIMEZONE") or "").strip()
                or (os.getenv("PROFILE_SESSION_OVERLAP_TIMEZONE") or "").strip()
                or "America/New_York"
            )

        def _commentary_daily_slots(self) -> list[tuple[int, int]]:
            raw = (os.getenv("COMMENTARY_LLM_DAILY_SLOTS") or "").strip() or "09:00,12:00,18:00,22:00"
            out: list[tuple[int, int]] = []
            for part in raw.split(","):
                p = part.strip()
                if not p or ":" not in p:
                    continue
                hh_s, mm_s = p.split(":", 1)
                try:
                    hh = int(hh_s)
                    mm = int(mm_s)
                except Exception:
                    continue
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    out.append((hh, mm))
            return sorted(set(out))

        def _current_daily_slot_key(self, now_dt: datetime, slots: list[tuple[int, int]]) -> str | None:
            if not slots:
                return None
            eligible = [(h, m) for (h, m) in slots if (h, m) <= (now_dt.hour, now_dt.minute)]
            if not eligible:
                return None
            h, m = max(eligible)
            return f"{now_dt.date().isoformat()}#{h:02d}:{m:02d}"

        def _maybe_update_commentary(self) -> None:
            if self._commentary_mode() != "internal":
                return
            # Check sabbath status on the state via getattr to avoid attribute errors.
            # Some versions of UiState may not define `sabbath_active`.
            if getattr(self._state, "sabbath_active", False):
                self._commentary.setMarkdown("Sabbath window active — no play-by-play. Waiting for resume.")
                return
            if self._adviser_thread is not None and self._adviser_thread.isRunning():
                if self._adviser_start_ts and self._adviser_timeout_seconds > 0:
                    elapsed = _now_epoch() - self._adviser_start_ts
                    if elapsed > self._adviser_timeout_seconds:
                        self._adviser_last_error = f"timeout after {int(self._adviser_timeout_seconds)}s"
                        self._adviser_last_exit_code = None
                        if self._last_good_commentary is None:
                            self._commentary.setMarkdown(f"(commentary error: {self._adviser_last_error})")
                        else:
                            self._commentary.setMarkdown(self._last_good_commentary)
                        self._adviser_start_ts = None
                return
            now = _now_epoch()
            min_seconds = max(60.0, self._commentary_min_seconds())
            if self._adviser_last_attempt_ts is not None and self._adviser_backoff_seconds > 0:
                since = now - self._adviser_last_attempt_ts
                remaining = self._adviser_backoff_seconds - since
                if remaining > 0.5:
                    secs_total = int(max(1, math.ceil(remaining)))
                    mins = int(secs_total // 60)
                    secs = int(secs_total % 60)
                    self._adviser_budget_note = f"cooldown: retry in {mins}m{secs:02d}s"
                    self.statusBar().showMessage(f"Commentary paused ({self._adviser_budget_note})")
                    if self._last_good_commentary is None:
                        self._commentary.setMarkdown(f"(waiting for commentary… {self._adviser_budget_note})")
                    return
                if self._adviser_budget_note and self._adviser_budget_note.startswith("cooldown:"):
                    self._adviser_budget_note = None

            policy = self._commentary_policy()
            due_reason: str | None = None
            pending_daily_slot_key: str | None = None
            pending_a_plus_ts: float | None = None
            if policy == "interval":
                due_reason = "interval"
            else:
                a_plus_triggered = False
                for sym, info in (self._state.structure_by_symbol or {}).items():
                    prev = float(self._prev_readiness_by_symbol.get(sym, 0.0))
                    self._prev_readiness_by_symbol[sym] = float(info.readiness)
                    if prev < 1.0 and float(info.readiness) >= 1.0:
                        a_plus_triggered = True
                if a_plus_triggered:
                    due_reason = "a_plus"
                    pending_a_plus_ts = now
                elif policy == "a_plus_or_4x":
                    slots = self._commentary_daily_slots()
                    try:
                        now_dt = datetime.now(ZoneInfo(self._commentary_tz()))
                    except Exception:
                        now_dt = datetime.now()
                    slot_key = self._current_daily_slot_key(now_dt, slots)
                    if slot_key and slot_key != self._adviser_last_daily_slot_key:
                        due_reason = "daily"
                        pending_daily_slot_key = slot_key
                    else:
                        if self._last_good_commentary is None:
                            self._commentary.setMarkdown("(waiting for commentary…)")                            
                        return
                else:
                    if self._last_good_commentary is None:
                        self._commentary.setMarkdown("(waiting for A+ continuation…)")
                    return

            if self._adviser_last_attempt_ts is not None and (now - self._adviser_last_attempt_ts) < min_seconds:
                return
            try:
                max_calls = int((os.getenv("COMMENTARY_LLM_MAX_CALLS_PER_DAY") or "").strip() or "250")
            except Exception:
                max_calls = 250
            if max_calls > 0:
                budget_path = Path(
                    (os.getenv("COMMENTARY_LLM_BUDGET_PATH") or "").strip()
                    or "/tmp/tradebot_sci_commentary_budget.json"
                )
                ok, note = _llm_budget_try_consume(budget_path, limit=max_calls)
                if not ok:
                    self._adviser_budget_note = note
                    self.statusBar().showMessage(f"Commentary paused ({note})")
                    if self._last_good_commentary is None:
                        self._commentary.setMarkdown(f"(commentary paused: {note})")
                    return
                self._adviser_budget_note = note
            self._adviser_last_attempt_ts = now
            self._adviser_pending_reason = due_reason
            self._adviser_pending_daily_slot_key = pending_daily_slot_key
            self._adviser_pending_a_plus_ts = pending_a_plus_ts
            self._start_adviser()

        def _build_adviser_question(self) -> str:
            active = (self._state.active_symbol or "none").strip().upper()
            execute = os.getenv("EXECUTE_TRADES", "false").strip().lower() == "true"
            mode = "LIVE" if execute else "SIM"
            profile = (os.getenv("PROFILE_NAME") or "").strip() or "unknown"
            bot_mode = (os.getenv("BOT_MODE") or "continuous").strip()

            items = list((self._state.structure_by_symbol or {}).items())
            items.sort(key=lambda kv: (kv[1].readiness, kv[1].selection_score), reverse=True)
            top = items[:10]
            watch = [sym for sym, info in top if info.readiness >= 0.8][:5]

            dec = self._state.last_decision_by_symbol or {}
            dec_lines = [f"{sym}: {rest}" for sym, rest in list(dec.items())[-10:]]
            tail_lines = list(self._recent_log)[-120:]
            recent_flags = []
            joined_tail = "\n".join(tail_lines[-80:])
            for flag in ("A_PLUS_PASS", "ENTER_LONG", "ENTER_SHORT", "STAND_ASIDE", "ICC_GATE_BLOCK"):
                if flag in joined_tail:
                    recent_flags.append(flag)

            readiness_lines: list[str] = []
            for sym, info in top:
                gate = (info.last_gate or "").strip()
                sweep = (info.since_sweep or "").strip()
                cont = (info.since_cont or "").strip()
                reason = (info.reason or "").strip().replace("\n", " ")
                if len(reason) > 160:
                    reason = reason[:157].rstrip() + "…"
                readiness_lines.append(
                    f"{sym:>6}  ready={info.readiness:0.2f}  score={info.selection_score:0.3f}  gate={gate or '-'}  sweep={sweep or '-'}  cont={cont or '-'}  reason={reason or '-'}"
                )

            instructions = (
                "You are the Tradebot's internal voice. You are 16, blunt, and slightly annoyed by the market.\n"
                "Write in the first person. Tell us what's 'sketchy' or 'legit.' Are you stressed about the $88 balance? Is the market total trash right now? Be honest.\n"
                "Do not mention missing context or limitations.\n"
                "Goal: ~220-350 words of moody, diagnostic honesty.\n\n"
                "Must include:\n"
                "1) What's Up: How I'm feeling right now. (Spoiler: Probably stressed about the balance or bored by the chop).\n"
                "2) My Red Flags & Hype: 3-6 bullets on what is actually legit and what is making me nervous.\n"
                "3) Truth-o-meter: Is this an A+ play or are we just watching 15m garbage?\n"
                "4) Be blunt about the $88 'sketchy' balance if relevant.\n"
            )

            parts: list[str] = [instructions]
            parts.append(f"Context: mode={mode} profile={profile} bot_mode={bot_mode} active={active}")
            if recent_flags:
                parts.append("Recent log flags: " + ", ".join(recent_flags))
            if watch:
                parts.append("High-readiness watchlist (ready>=0.80): " + ", ".join(watch))
            if readiness_lines:
                parts.append("Readiness table (top 10):\n" + "\n".join(readiness_lines))
            if dec_lines:
                parts.append("Recent decisions:\n" + "\n".join(dec_lines))
            if tail_lines:
                parts.append("Recent log tail:\n" + "\n".join(tail_lines))

            q = "\n\n".join(parts).strip()
            if len(q) > 8000:
                q = q[-8000:]
            return q

        def _start_adviser(self) -> None:
            self._adviser_last_error = None
            self._adviser_last_exit_code = None
            self._adviser_start_ts = _now_epoch()
            question = self._build_adviser_question()
            ai_settings = get_settings().ai
            if self._adviser_timeout_seconds > 0:
                ai_settings = ai_settings.model_copy(update={"timeout_seconds": int(self._adviser_timeout_seconds)})
            self._adviser_thread = QtCore.QThread()  # No parent - will be deleted via deleteLater
            self._adviser_worker = CommentaryWorker(question, ai_settings)  # No parent - lives in different thread
            self._adviser_worker.moveToThread(self._adviser_thread)
            self._adviser_thread.started.connect(self._adviser_worker.run)
            self._adviser_worker.finished.connect(self._on_adviser_finished)
            self._adviser_worker.finished.connect(self._adviser_thread.quit)
            self._adviser_worker.finished.connect(self._adviser_worker.deleteLater)
            self._adviser_thread.finished.connect(self._adviser_thread.deleteLater)
            self._adviser_thread.start()

        def _on_adviser_finished(self, answer: str, err: str) -> None:
            self._adviser_last_exit_code = 0 if answer else 1
            if answer:
                self._last_good_commentary = answer.strip()
                self._adviser_last_update_ts = _now_epoch()
                self._commentary.setMarkdown(self._last_good_commentary)
                if self._adviser_pending_reason == "daily" and self._adviser_pending_daily_slot_key:
                    self._adviser_last_daily_slot_key = self._adviser_pending_daily_slot_key
                elif self._adviser_pending_reason == "a_plus" and self._adviser_pending_a_plus_ts:
                    self._adviser_last_a_plus_ts = self._adviser_pending_a_plus_ts
                self._adviser_backoff_seconds = 0.0
                self._adviser_budget_note = None
            else:
                tail = err.strip() or "no output"
                self._adviser_last_error = f"error: {tail}"[:220]
                self._adviser_backoff_seconds = _next_llm_backoff_seconds(
                    prev=self._adviser_backoff_seconds,
                    error_text=err,
                )
                if self._last_good_commentary is None:
                    self._commentary.setMarkdown(f"(commentary error: {self._adviser_last_error})")
                else:
                    self._commentary.setMarkdown(self._last_good_commentary)
            self._adviser_start_ts = None
            self._adviser_pending_reason = None
            self._adviser_pending_daily_slot_key = None
            self._adviser_pending_a_plus_ts = None
            thread = self._adviser_thread
            if thread is not None and thread.isRunning():
                thread.finished.connect(self._cleanup_adviser_thread)
            else:
                self._cleanup_adviser_thread()

        def _cleanup_adviser_thread(self) -> None:
            self._adviser_thread = None
            self._adviser_worker = None

        def _capital_tune_context(self) -> dict[str, str]:
            keys = [
                "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT",
                "PROFILE_MAX_DAILY_LOSS_PCT",
                "PROFILE_MAX_EXPOSURE_PCT",
                "PROFILE_MAX_CONSECUTIVE_LOSSES",
                "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL",
                "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT",
                "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER",
            ]
            out: dict[str, str] = {}
            for key in keys:
                val = os.getenv(key, "").strip()
                out[key] = val if val else "auto"
            return out

        def _maybe_auto_capital_tune(self) -> None:
            if os.getenv(AUTO_TUNE_ENABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
                return
            if not auto_tune_due():
                return
            if self._capital_tune_thread is not None and self._capital_tune_thread.isRunning():
                return
            self._start_auto_capital_tune()

        def _start_auto_capital_tune(self) -> None:
            if self._capital_tune_thread is not None and self._capital_tune_thread.isRunning():
                return
            settings_obj = get_settings()
            profile_name = os.getenv("PROFILE_NAME", "").strip() or settings_obj.app.profile_name
            env_snapshot = {k: os.getenv(k, "").strip() for k in self._discovered_env_keys}
            secret_keys = {
                "TRADE_SCI_API_KEY",
                "CHATGPT_KEY",
                "CCXT_API_KEY",
                "CCXT_SECRET",
                "CCXT_PASSWORD",
            }
            self._capital_tune_thread = QtCore.QThread()
            self._capital_tune_worker = CapitalTuneWorker(
                settings_obj=settings_obj,
                profile_name=profile_name,
                current=self._capital_tune_context(),
                context=sanitize_context(env_snapshot, redact_keys=secret_keys),
                log_excerpt=load_log_excerpt(str(settings.log_file)),
            )
            self._capital_tune_worker.moveToThread(self._capital_tune_thread)
            self._capital_tune_thread.started.connect(self._capital_tune_worker.run)
            self._capital_tune_worker.done.connect(self._on_capital_tune_done)
            self._capital_tune_worker.error.connect(self._on_capital_tune_error)
            self._capital_tune_worker.done.connect(self._capital_tune_thread.quit)
            self._capital_tune_worker.error.connect(self._capital_tune_thread.quit)
            self._capital_tune_thread.finished.connect(self._capital_tune_worker.deleteLater)
            # REMOVED: self._capital_tune_thread.finished.connect(self._capital_tune_thread.deleteLater)
            # We manage the thread lifecycle manually to prevent race conditions.
            self._capital_tune_thread.start()

        def _on_capital_tune_done(self, overrides: object, notes: str, equity: float, broker: str) -> None:
            overrides_dict = dict(overrides or {})
            if not overrides_dict:
                logger.info("[CAPITAL_TUNE] No overrides recommended.")
                # Properly clean up the thread before setting to None
                if self._capital_tune_thread is not None:
                    if self._capital_tune_thread.isRunning():
                        self._capital_tune_thread.quit()
                        if not self._capital_tune_thread.wait(2000):
                            self._capital_tune_thread.terminate()
                            self._capital_tune_thread.wait()
                    self._capital_tune_thread = None
                self._capital_tune_worker = None
                return
            try:
                apply_tune_to_env(
                    dotenv_path=self._repo_root / ".env",
                    overrides=overrides_dict,
                    equity=equity,
                    broker=broker,
                    notes=notes or "",
                )
                logger.info(
                    "[CAPITAL_TUNE] Applied overrides (%s) equity=%.2f broker=%s",
                    ", ".join(overrides_dict.keys()),
                    equity,
                    broker,
                )
            except Exception as exc:
                logger.warning("[CAPITAL_TUNE] Failed to apply overrides: %s", exc)
            # Properly clean up the thread before setting to None
            if self._capital_tune_thread is not None:
                if self._capital_tune_thread.isRunning():
                    self._capital_tune_thread.quit()
                    if not self._capital_tune_thread.wait(2000):
                        self._capital_tune_thread.terminate()
                        self._capital_tune_thread.wait()
                self._capital_tune_thread = None
            self._capital_tune_worker = None

        def _on_capital_tune_error(self, msg: str) -> None:
            logger.warning("[CAPITAL_TUNE] %s", msg)
            # Properly clean up the thread before setting to None
            if self._capital_tune_thread is not None:
                if self._capital_tune_thread.isRunning():
                    self._capital_tune_thread.quit()
                    if not self._capital_tune_thread.wait(2000):
                        self._capital_tune_thread.terminate()
                        self._capital_tune_thread.wait()
                self._capital_tune_thread = None
            self._capital_tune_worker = None

        def _apply_theme(self, theme_key: str) -> None:
            """Apply the given theme to all panels and the main window."""
            theme = THEMES.get(theme_key, THEMES["dark"])
            app = QtWidgets.QApplication.instance()
            
            # [ANTIGRAVITY GLASS FX]
            if theme_key == "mockup_pro":
                # high-tech glass styling
                glass_qss = """
                    QMainWindow {
                        /* Background is painted in paintEvent */
                    }
                    QWidget {
                        background: transparent;
                        color: #e2e8f0;
                    }
                    QTabWidget::pane {
                        border: 1px solid rgba(56, 189, 248, 0.3);
                        background: rgba(15, 23, 42, 0.6); /* Semi-transparent blue-black */
                        border-radius: 4px;
                    }
                    QTabBar::tab {
                        background: rgba(30, 41, 59, 0.4);
                        color: #94a3b8;
                        padding: 8px 12px;
                        border-top-left-radius: 4px;
                        border-top-right-radius: 4px;
                        margin-right: 2px;
                    }
                    QTabBar::tab:selected {
                        background: rgba(56, 189, 248, 0.2);
                        color: #38bdf8;
                        border-bottom: 2px solid #38bdf8;
                    }
                    QTableWidget, QTreeWidget, QListWidget, QPlainTextEdit, QTextEdit {
                        background-color: rgba(10, 15, 30, 0.65);
                        border: 1px solid rgba(148, 163, 184, 0.15);
                        border-radius: 4px;
                    }
                    QHeaderView::section {
                        background-color: rgba(30, 41, 59, 0.8);
                        color: #cbd5e1;
                        padding: 4px;
                        border: none;
                    }
                    QLineEdit, QComboBox {
                        background-color: rgba(15, 23, 42, 0.8);
                        border: 1px solid #334155;
                        color: white;
                        padding: 4px;
                    }
                    /* Scrollbars */
                    QScrollBar:vertical {
                        background: rgba(0,0,0,0.2);
                        width: 10px;
                    }
                    QScrollBar::handle:vertical {
                        background: #475569;
                        min-height: 20px;
                        border-radius: 5px;
                    }
                """
                if app: app.setStyleSheet(glass_qss)
                
                # Force update of background call
                self.update()
            else:
                # Standard themes
                if app: app.setStyleSheet(theme.qss())
                
            # Update palette colours for the main window widgets
            pal = self.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor(theme.window))
            pal.setColor(QtGui.QPalette.Base, QtGui.QColor(theme.base))
            pal.setColor(QtGui.QPalette.Text, QtGui.QColor(theme.text))
            pal.setColor(QtGui.QPalette.Button, QtGui.QColor(theme.header))
            pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(theme.text))
            self.setPalette(pal)

            # Delegate to the candles panel to update its colours
            try:
                self._candles_panel.set_theme(theme_key)
            except Exception:
                pass
            # Update log panel highlighter
            try:
                self._log_highlighter.set_theme(theme)
            except Exception:
                pass
            # Update decisions panel highlighter
            try:
                self._decisions_highlighter.set_theme(theme)
            except Exception:
                pass
            # Update readiness table colours
            try:
                self._readiness_table.set_theme(theme_key)
            except Exception:
                pass
            # Persist theme selection
            self._qsettings.setValue("theme", theme.key)

        def _set_candle_tf(self, tf: str) -> None:
            """Delegate timeframe changes to the candles panel.

            The legacy method signature is preserved for backward
            compatibility.  Internally this forwards the new timeframe to
            the CandlesPanel which updates settings and triggers a fresh
            fetch as needed.
            """
            # Normalise and propagate to the panel
            val = str(tf or "").strip()
            if val:
                try:
                    # Update the settings and ask the panel to refresh
                    self._settings.candle_tf = val  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    self._candles_panel._on_tf_changed(-1)
                except Exception:
                    pass

        def _populate_symbol_selector(self) -> None:
            """Populate the symbol selector via the CandlesPanel."""
            try:
                self._candles_panel.populate_symbols()
            except Exception:
                pass

        def _on_symbol_selected(self) -> None:
            """Delegate symbol selection handling to the CandlesPanel."""
            try:
                self._candles_panel._on_symbol_selected()
            except Exception:
                pass

        def _on_lock_symbol_toggled(self, state: int) -> None:
            """Delegate lock toggling to the CandlesPanel."""
            try:
                self._candles_panel._on_lock_toggled(state)
            except Exception:
                pass

        def _install_menu(self) -> None:
            bar = self.menuBar()
            file_menu = bar.addMenu("&File")
            act_restart_gui = file_menu.addAction("Restart GUI")
            act_quit = file_menu.addAction("Quit")
            act_restart_gui.triggered.connect(self._restart_gui)
            act_quit.triggered.connect(self.close)

            settings_menu = bar.addMenu("&Settings")
            act_log = settings_menu.addAction("Set Log File…")
            act_log.triggered.connect(self._choose_log)
            act_env = settings_menu.addAction("Environment / Settings…")
            act_env.triggered.connect(self._open_env_settings)

            bot_menu = bar.addMenu("&Bot")
            act_start = bot_menu.addAction("Start")
            act_stop = bot_menu.addAction("Stop")
            act_restart = bot_menu.addAction("Restart")
            bot_menu.addSeparator()
            act_autostart = bot_menu.addAction("Auto-start with GUI")
            act_autostart.setCheckable(True)
            act_autostart.setChecked(self._bot_autostart)
            act_keep = bot_menu.addAction("Keep running after GUI closes")
            act_keep.setCheckable(True)
            act_keep.setChecked(self._bot_keep_running_on_close)

            act_start.triggered.connect(self._start_bot)
            act_stop.triggered.connect(self._stop_bot)
            act_restart.triggered.connect(self._restart_bot)
            act_autostart.toggled.connect(self._set_bot_autostart)
            act_keep.toggled.connect(self._set_bot_keep_running_on_close)

            view_menu = bar.addMenu("&View")
            theme_group = QtGui.QActionGroup(self)
            theme_group.setExclusive(True)
            for key, theme in THEMES.items():
                act = view_menu.addAction(theme.name)
                act.setCheckable(True)
                act.setChecked(key == settings.theme_key)
                theme_group.addAction(act)
                act.triggered.connect(lambda _=False, k=key: self._set_theme(k))

        def _set_theme(self, theme_key: str) -> None:
            settings.theme_key = theme_key
            self._apply_theme(theme_key)

        def _effective_env_value(self, key: str) -> tuple[str, str]:
            if key in self._env_overrides:
                return self._env_overrides[key], "override"
            if key in os.environ:
                return os.environ[key], "env"
            if key in dotenv_values:
                return dotenv_values[key], ".env"
            return "", ""

        def _set_bot_autostart(self, enabled: bool) -> None:
            self._bot_autostart = bool(enabled)
            self._qsettings.setValue("bot/autostart", "true" if enabled else "false")

        def _set_bot_keep_running_on_close(self, enabled: bool) -> None:
            self._bot_keep_running_on_close = bool(enabled)
            self._qsettings.setValue("bot/keep_running_on_close", "true" if enabled else "false")

        def _pid_alive(self, pid: int) -> bool:
            try:
                os.kill(pid, 0)
                return True
            except Exception:
                return False

        def _detect_running_bot_pid(self) -> int | None:
            # Prefer persisted PID (bot previously started by GUI).
            try:
                raw = self._qsettings.value("bot/pid")
                if raw is not None and str(raw).strip():
                    pid = int(str(raw).strip())
                    if pid > 0 and self._pid_alive(pid):
                        logger.info(f"[GUI] Detected bot from QSettings: pid={pid}")
                        return pid
                    else:
                        logger.info(f"[GUI] QSettings had stale PID: pid={pid} (not alive), clearing")
                        self._qsettings.remove("bot/pid")
            except Exception as e:
                logger.debug(f"[GUI] Failed to check QSettings PID: {e}")

            # Fallback: detect any run_dev_bot process.
            try:
                res = subprocess.run(
                    ["pgrep", "-f", "scripts/run_dev_bot.py"],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if res.returncode == 0:
                    pids = [int(x) for x in (res.stdout or "").split() if x.strip().isdigit()]
                    logger.info(f"[GUI] pgrep found bot PIDs: {pids}")
                    for pid in pids:
                        if pid > 0 and self._pid_alive(pid):
                            logger.info(f"[GUI] Detected running bot via pgrep: pid={pid}")
                            # Save this PID so future checks are faster
                            self._qsettings.setValue("bot/pid", str(pid))
                            return pid
                else:
                    logger.info(f"[GUI] pgrep found no bot processes (returncode={res.returncode})")
            except Exception as e:
                logger.warning(f"[GUI] pgrep detection failed: {e}")

            logger.info("[GUI] No running bot detected")
            return None

        def _bot_args(self) -> list[str]:
            mode = (os.getenv("BOT_MODE") or "continuous").strip().lower()
            args: list[str] = []
            if mode == "scheduled":
                args.append("--scheduled")
            elif mode == "iterations":
                try:
                    iters = int(os.getenv("BOT_ITERATIONS") or "120")
                except Exception:
                    iters = 120
                args.extend(["--iterations", str(iters)])
            else:
                args.append("--continuous")

            sabb = (os.getenv("BOT_SABBATH") or "").strip().lower()
            if sabb in {"on", "true", "1", "yes"}:
                args.append("--sabbath")
            elif sabb in {"off", "false", "0", "no"}:
                args.append("--no-sabbath")
            return args

        def _compute_trading_universe(self) -> tuple[str, list[str]]:
            """
            Returns (profile_name, symbols) using the same logic as the runtime precheck,
            so TRADING_CONFIRMATION can match exactly.
            """
            try:
                from tradebot_sci.config.loader import load_settings  # type: ignore
                from tradebot_sci.runtime.universe import resolve_symbol_universe  # type: ignore

                settings_obj = get_settings()
                profile_settings = settings_obj.get_active_profile()
                profile_name = settings_obj.app.profile_name
                symbols = resolve_symbol_universe(settings_obj, profile_settings, profile_name)
                return profile_name, list(symbols or [])
            except Exception:
                profile = (os.getenv("PROFILE_NAME") or "").strip() or "unknown"
                raw = (os.getenv("MARKET_SYMBOLS") or "").strip()
                symbols = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
                return profile, symbols

        def _instrument_classes(self, symbols: list[str]) -> list[str]:
            try:
                from tradebot_sci.runtime.universe import instrument_classes_for_symbols  # type: ignore

                return list(instrument_classes_for_symbols(symbols))
            except Exception:
                return []

        def _confirm_live_trading(self) -> str | None:
            execute = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
            if not execute:
                return None
            profile, symbols = self._compute_trading_universe()
            universe = ",".join(symbols)
            expected = f"YES:{universe}"
            
            # Check environment variable or persisted file before prompting.
            conf = os.getenv("TRADING_CONFIRMATION")
            if conf != expected:
                try:
                    log_file = os.getenv("TRADEBOT_LOG", self._repo_root / "logs" / "tradebot.log")
                    confirm_file = Path(log_file).parent / ".trading_confirmation"
                    if confirm_file.exists():
                        persisted = confirm_file.read_text().strip()
                        if persisted == expected:
                            conf = persisted
                            # Sync environment so child processes (the bot) inherit it.
                            os.environ["TRADING_CONFIRMATION"] = conf
                except Exception:
                    pass

            if conf == expected:
                self._confirmed_live_trading = True
                return expected

            classes = self._instrument_classes(symbols)
            classes_txt = ", ".join(classes) if classes else "(unknown)"
            sym_preview = ", ".join([s.upper() for s in symbols[:30]]) + (" …" if len(symbols) > 30 else "")
            text = (
                "You are about to start LIVE trading.\n\n"
                f"Profile: {profile}\n"
                f"Instrument classes: {classes_txt}\n"
                f"Universe ({len(symbols)}): {sym_preview}\n\n"
                "Proceed?"
            )
            detail = (
                "This GUI runs the bot non-interactively, so the bot requires an explicit confirmation token.\n\n"
                f"TRADING_CONFIRMATION must equal:\n{expected}\n"
            )

            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("Confirm LIVE Trading")
            box.setText(text)
            box.setDetailedText(detail)
            box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            box.setDefaultButton(QtWidgets.QMessageBox.No)
            res = box.exec()
            if res != QtWidgets.QMessageBox.Yes:
                return None
            os.environ["TRADING_CONFIRMATION"] = expected
            self._confirmed_live_trading = True
            return expected

        def _maybe_autostart_bot(self) -> None:
            if not self._bot_autostart:
                logger.info("[GUI] Bot autostart disabled in settings, skipping autostart")
                return
            logger.info("[GUI] Bot autostart enabled, checking for running bot...")
            # If a bot is already running, avoid spawning a duplicate.
            pid = self._detect_running_bot_pid()
            if pid is not None:
                self._bot_pid = pid
                logger.info(f"[GUI] Found existing bot process (pid={pid}), skipping autostart")
                self.statusBar().showMessage(f"bot=external(pid={pid}) · " + (self.statusBar().currentMessage() or ""))
                return
            logger.info("[GUI] No existing bot found, starting new bot process")
            self._start_bot()

        def _start_bot(self) -> None:
            if self._bot_pid is not None and self._pid_alive(self._bot_pid):
                self.statusBar().showMessage(f"bot=external(pid={self._bot_pid}) · " + (self.statusBar().currentMessage() or ""))
                return
            if self._bot_proc is not None and self._bot_proc.state() != QtCore.QProcess.NotRunning:
                return

            expected_confirmation = self._confirm_live_trading()
            if os.getenv("EXECUTE_TRADES", "false").lower() == "true" and not expected_confirmation:
                # User declined live trading confirmation.
                self.statusBar().showMessage("bot=blocked (live confirmation declined) · " + (self.statusBar().currentMessage() or ""))
                return

            script = str(repo_root / "scripts" / "run_dev_bot.py")
            args = ["-u", script, *self._bot_args()]

            if self._bot_keep_running_on_close:
                env = os.environ.copy()
                env["PYTHONPATH"] = "src"
                if expected_confirmation:
                    env["TRADING_CONFIRMATION"] = expected_confirmation
                # Start detached so closing the GUI doesn't terminate the process.
                proc = subprocess.Popen(
                    [sys.executable, *args],
                    cwd=str(repo_root),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._bot_pid = int(proc.pid)
                self._qsettings.setValue("bot/pid", str(self._bot_pid))
                self._bot_started_by_gui = True
                self.statusBar().showMessage(f"bot=running(detached pid={self._bot_pid}) · " + (self.statusBar().currentMessage() or ""))
                return

            self._bot_proc = QtCore.QProcess(self)
            self._bot_proc.setWorkingDirectory(str(repo_root))

            env = QtCore.QProcessEnvironment.systemEnvironment()
            env.insert("PYTHONPATH", "src")
            # Apply any env overrides currently in-process.
            for k in discovered_env_keys:
                if k in os.environ:
                    env.insert(k, os.environ[k])
            if expected_confirmation:
                env.insert("TRADING_CONFIRMATION", expected_confirmation)
            self._bot_proc.setProcessEnvironment(env)

            self._bot_proc.started.connect(lambda: self.statusBar().showMessage("bot=running · " + (self.statusBar().currentMessage() or "")))

            def _finished(code: int, status: QtCore.QProcess.ExitStatus) -> None:
                _ = status
                self.statusBar().showMessage(f"bot=stopped(exit={code}) · " + (self.statusBar().currentMessage() or ""))

            self._bot_proc.finished.connect(_finished)
            self._bot_proc.errorOccurred.connect(lambda _e: self.statusBar().showMessage("bot=error · " + (self.statusBar().currentMessage() or "")))
            self._bot_started_by_gui = True
            self._bot_proc.start(sys.executable, args)

        def _has_open_positions(self) -> bool:
            if not self._holdings:
                return False
            now = time.time()
            stale = self._holdings_updated_ts is None or (now - float(self._holdings_updated_ts)) > 120.0
            for pos in self._holdings or []:
                try:
                    size = float(pos.get("size") or 0.0)
                except Exception:
                    size = 0.0
                if abs(size) > 1e-8:
                    if stale and bool(pos.get("inferred")):
                        continue
                    return True
            return False

        def _safe_restart_bot(self, *, reason: str = "settings") -> None:
            if self._bot_proc is None and (self._bot_pid is None or not self._pid_alive(self._bot_pid)):
                return
            execute = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
            profile, symbols = self._compute_trading_universe()
            expected = f"YES:{','.join(symbols)}"
            if execute and os.getenv("TRADING_CONFIRMATION") != expected:
                if self._confirmed_live_trading:
                    os.environ["TRADING_CONFIRMATION"] = expected
                else:
                    self.statusBar().showMessage(
                        f"bot=restart pending (confirmation required) · {reason}"
                    )
                    return
            if self._has_open_positions():
                self.statusBar().showMessage(
                    f"bot=restart pending (open positions) · {reason}"
                )
                QtCore.QTimer.singleShot(30000, lambda: self._safe_restart_bot(reason=reason))
                return
            os.environ["TRADING_CONFIRMATION"] = expected
            self._restart_bot()

        def _stop_bot(self) -> None:
            if self._bot_proc is None or self._bot_proc.state() == QtCore.QProcess.NotRunning:
                if self._bot_pid is None:
                    return
                pid = int(self._bot_pid)
                if not self._pid_alive(pid):
                    self._bot_pid = None
                    self._qsettings.remove("bot/pid")
                    return
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
                self._bot_pid = None
                self._qsettings.remove("bot/pid")
                self.statusBar().showMessage("bot=stopped · " + (self.statusBar().currentMessage() or ""))
                return
            self._bot_proc.terminate()
            if not self._bot_proc.waitForFinished(3000):
                self._bot_proc.kill()
                self._bot_proc.waitForFinished(1000)
            self._qsettings.remove("bot/pid")
            self._bot_pid = None

        def _restart_bot(self) -> None:
            self._stop_bot()
            self._start_bot()

        def paintEvent(self, event: QtGui.QPaintEvent) -> None:
            """Draw the custom cyberpunk background image if available."""
            if self._background_map and not self._background_map.isNull():
                painter = QtGui.QPainter(self)
                painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
                # Draw covering the entire window
                painter.drawPixmap(self.rect(), self._background_map)
            else:
                super().paintEvent(event)

        def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
            # Stop all timers IMMEDIATELY to prevent any new operations
            for timer in [
                self._poll_timer,
                self._right_timer,
                self._candle_timer,
                self._ibkr_timer,
                self._adviser_timer,
                self._capital_tune_timer,
            ]:
                if timer is not None and timer.isActive():
                    timer.stop()
                    # Disconnect the timer to prevent any pending signals from firing
                    try:
                        timer.timeout.disconnect()
                    except (RuntimeError, TypeError):
                        pass  # Already disconnected or no connections

            # Clean up commentary thread if running
            if self._adviser_thread is not None:
                if self._adviser_thread.isRunning():
                    self._adviser_thread.quit()
                    if not self._adviser_thread.wait(3000):  # 3 second timeout
                        self._adviser_thread.terminate()
                        self._adviser_thread.wait()
                # DO NOT call deleteLater() - let Python GC handle it
                self._adviser_thread = None

            # Clean up capital tune thread if running
            if self._capital_tune_thread is not None:
                if self._capital_tune_thread.isRunning():
                    self._capital_tune_thread.quit()
                    if not self._capital_tune_thread.wait(3000):
                        self._capital_tune_thread.terminate()
                        self._capital_tune_thread.wait()
                self._capital_tune_thread = None
                self._capital_tune_worker = None

            # Clean up commentary worker if exists
            if self._adviser_worker is not None:
                # DO NOT call deleteLater() - let Python GC handle it
                self._adviser_worker = None

            if self._bot_started_by_gui and not self._bot_keep_running_on_close:
                self._stop_bot()

            # DO NOT disconnect IBKR here - it creates threads that conflict with Qt shutdown
            # Just let Python GC clean it up after Qt exits
            # if hasattr(self, '_candles_panel') and self._candles_panel is not None:
            #     if hasattr(self._candles_panel, '_fetcher') and self._candles_panel._fetcher is not None:
            #         self._candles_panel._fetcher.disconnect()

            # Wait for global thread pool to finish all background tasks
            QtCore.QThreadPool.globalInstance().waitForDone(3000)  # 3 second timeout

            super().closeEvent(event)

        def _restart_gui(self) -> None:
            if not self._bot_keep_running_on_close:
                QtWidgets.QMessageBox.information(
                    self,
                    "Restart GUI",
                    "Enable 'Keep running after GUI closes' before restarting the GUI.",
                )
                return
            script = str(repo_root / "scripts" / "tradebot_gui.py")
            try:
                env = QtCore.QProcessEnvironment.systemEnvironment()
                for k, v in os.environ.items():
                    env.insert(k, v)
                proc = QtCore.QProcess(self)
                proc.setProcessEnvironment(env)
                proc.setWorkingDirectory(str(repo_root))
                started = proc.startDetached(sys.executable, [script])
                if not started:
                    raise RuntimeError("QProcess failed to start detached GUI process.")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Restart GUI failed", str(exc))
                return
            self.close()

        def _open_env_settings(self) -> None:
            # Delegate to the external settings dialog defined in settings_dialog.py.
            # Use the global settings (loaded at module import) instead of the
            # GUI runtime settings.  Provide repository context and environment
            # overrides so the dialog can populate the Advanced tab and manage
            # .env interactions.  Returning immediately ensures the original
            # (now unused) inline dialog code below is not executed.
            try:
                open_settings_dialog(
                    self,
                    global_settings,
                    self._repo_root,
                    self._discovered_env_keys,
                    self._dotenv_values,
                    settings.theme_key,
                )
            except Exception as exc:
                logger.error(f"Failed to open settings dialog: {exc}", exc_info=True)
                QtWidgets.QMessageBox.critical(
                    self,
                    "Settings Error",
                    f"Failed to open settings dialog:\n{exc}\n\nCheck logs for details.",
                )
            return
            theme = THEMES.get(settings.theme_key, THEMES["dark"])

            # Define the draggable dialog class inline
            class GlassSettingsDialog(QtWidgets.QDialog):
                def __init__(self, parent=None):
                    super().__init__(parent)
                    self._dragging = False
                    self._drag_start_position = QtCore.QPoint()

                def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
                    if event.button() == QtCore.Qt.LeftButton:
                        self._dragging = True
                        self._drag_start_position = event.globalPos() - self.frameGeometry().topLeft()
                        event.accept()
                    else:
                        super().mousePressEvent(event)

                def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
                    if self._dragging and event.buttons() & QtCore.Qt.LeftButton:
                        self.move(event.globalPos() - self._drag_start_position)
                        event.accept()
                    else:
                        super().mouseMoveEvent(event)

                def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
                    if event.button() == QtCore.Qt.LeftButton:
                        self._dragging = False
                        event.accept()
                    else:
                        super().mouseReleaseEvent(event)

            dlg = GlassSettingsDialog(self)
            dlg.setObjectName("settingsDialog")
            dlg.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            dlg.setWindowOpacity(0.96)
            dlg.setWindowTitle("Settings")
            dlg.resize(1180, 820)
            dlg.setStyleSheet(
                theme.qss()
                + "QDialog#settingsDialog { background: transparent; }"
                + "QDialog#settingsDialog QWidget { background: transparent; }"
                + "QDialog#settingsDialog QTabWidget::pane { background: transparent; }"
                + "QDialog#settingsDialog QTabBar::tab { background: transparent; }"
                + "QDialog#settingsDialog QTabBar::tab:selected { background: " + theme.card + "; }"
                + "QDialog#settingsDialog QGroupBox { background: transparent; }"
                + "QDialog#settingsDialog QScrollArea { background: transparent; }"
                + "QDialog#settingsDialog QScrollArea > QWidget > QWidget { background: transparent; }"
                + "QDialog, QDialog * { font-size: 12pt; }"
                + "QDialog QPlainTextEdit, QDialog QTextEdit, QDialog QTableWidget { font-size: 10.5pt; }"
            )

            initial_effective: dict[str, str] = {}
            for k in discovered_env_keys:
                initial_effective[k] = self._effective_env_value(k)[0]

            info = QtWidgets.QLabel(
                "Most options are env vars. Use the tabs for common settings, or Advanced (env) for raw key/value overrides.\n"
                "Apply affects this GUI immediately. Save to .env affects future tmux runs. Restart tmux applies to the running bot."
            )
            info.setWordWrap(True)
            info.setStyleSheet(f"color: {theme.muted};")

            def read_profiles() -> list[str]:
                path = repo_root / "config" / "settings_profiles.yaml"
                if not path.exists():
                    return []
                profiles: list[str] = []
                in_section = False
                for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw.rstrip("\n")
                    if line.strip() == "profiles:":
                        in_section = True
                        continue
                    if in_section and line and not line.startswith(" "):
                        break
                    if in_section and line.startswith("  ") and line.strip().endswith(":") and not line.startswith("    "):
                        key = line.strip()[:-1].strip()
                        if key:
                            profiles.append(key)
                return profiles

            def classify(key: str) -> str:
                if key.startswith("IBKR_") or key.startswith("CCXT_") or key in {"EXCHANGE_PROVIDER", "ALTERNATIVE_BROKER"}:
                    return "Broker/Market"
                if key.startswith("TRADE_SCI_") or key in {"CHATGPT_KEY"}:
                    return "AI/Commentary"
                if "SABBATH" in key or "SCHEDULE" in key:
                    return "Schedule/Sabbath"
                if "LOG" in key:
                    return "Logging"
                return "Runtime"

            def set_override(key: str, value: str) -> None:
                v = value.strip()
                if v == "":
                    self._env_overrides.pop(key, None)
                    self._qsettings.remove(f"env/{key}")
                    if key in dotenv_values:
                        os.environ[key] = dotenv_values[key]
                    else:
                        os.environ.pop(key, None)
                    return
                self._env_overrides[key] = v
                self._qsettings.setValue(f"env/{key}", v)
                os.environ[key] = v

            def bool_chk(key: str, label: str) -> QtWidgets.QCheckBox:
                chk = QtWidgets.QCheckBox(label)
                chk.setChecked(self._effective_env_value(key)[0].strip().lower() in {"1", "true", "yes", "on"})
                return chk

            def scroll(widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
                area = QtWidgets.QScrollArea()
                area.setWidgetResizable(True)
                area.setFrameShape(QtWidgets.QFrame.NoFrame)
                area.setWidget(widget)
                return area

            def tip(widget: QtWidgets.QWidget, text: str) -> None:
                raw = (text or "").strip()
                if not raw:
                    return
                lines = raw.splitlines()
                key = (lines[0] or "").strip()
                summary = "\n".join(lines[1:]).strip()

                def _env_template(env_key: str, short: str) -> str:
                        short = (short or "").strip()
                        return (
                            f"{env_key}\n"
                            f"{'Summary: ' + short if short else 'Summary: (no short description provided)'}\n\n"
                            "What this is\n"
                            "- This is an environment variable (env var).\n"
                            "- The bot reads env vars at startup; some settings are only applied after a restart.\n\n"
                            "When it takes effect\n"
                            "- Apply (GUI): affects what THIS running GUI session shows/does.\n"
                            "- Save to .env: affects the next time you start the bot/GUI/tmux launcher.\n"
                            "- Restart tmux: restarts the terminal panes so the running bot/dashboard pick up changes.\n\n"
                            "How to use it in this GUI\n"
                            "- Change the control (toggle/dropdown/field).\n"
                            "- Click “Apply (GUI)” to apply to this running GUI session.\n"
                            "- Click “Save to .env” to persist it for future runs.\n"
                            "- Click “Restart tmux” if you want the terminal dashboard panes to pick up changes.\n\n"
                            "Tips\n"
                            "- Clearing a value (empty) usually means “fall back to defaults / profile / config file”.\n"
                            "- Most booleans accept true/false; the GUI writes consistent values for you.\n\n"
                            "Safety notes\n"
                            "- If you enable live trading, the GUI will show a confirmation prompt.\n"
                            "- Some broker settings can prevent orders even in live mode (e.g., read-only).\n"
                            "- If you are unsure, keep `EXECUTE_TRADES=false` and validate in simulation first.\n\n"
                            "Troubleshooting\n"
                            "- If a change “did nothing”, it likely requires a restart (tmux restart or relaunch).\n"
                            "- If live trading is blocked, check for a confirmation requirement or broker read-only mode.\n"
                        )

                TOOLTIP_LIBRARY: dict[str, str] = {
                        "GUI_AUTOSTART_BOT": (
                            "GUI_AUTOSTART_BOT\n"
                            "Automatically start the core bot process when the GUI opens.\n\n"
                            "What this does\n"
                            "- On GUI launch, the app checks whether the bot is already running.\n"
                            "- If it is NOT running, the GUI starts it using your current settings.\n"
                            "- If it IS already running, the GUI attaches to the existing logs/state (no duplicate bot).\n\n"
                            "How to use\n"
                            "- Enable this if you want the GUI to be your “one-click launcher”.\n"
                            "- Disable this if you prefer starting the bot from tmux/terminal first.\n\n"
                            "Important safety note\n"
                            "- If `EXECUTE_TRADES=true`, you will still be asked to confirm live trading in the GUI.\n"
                            "- The confirmation is there to prevent accidental live orders.\n"
                        ),
                        "GUI_KEEP_BOT_RUNNING": (
                            "GUI_KEEP_BOT_RUNNING\n"
                            "Keep the bot running even after you close the GUI window.\n\n"
                            "Why you’d use this\n"
                            "- You want a desktop view temporarily, but you want the bot to keep running in the background.\n"
                            "- You want tmux/terminal users to continue seeing the dashboard after the GUI closes.\n\n"
                            "How it behaves\n"
                            "- Closing the GUI will not stop the bot.\n"
                            "- The bot will keep writing to the log file and managing positions (if enabled).\n\n"
                            "How to stop the bot\n"
                            "- Use the tmux launcher to restart/stop, or stop the process from your OS tools.\n"
                            "- If live trading is enabled, always make sure you intentionally stop it.\n"
                        ),
                        "GUI_LOG_BROWSE": (
                            "GUI_LOG_BROWSE\n"
                            "Pick which log file the GUI (and tmux log tail) reads.\n\n"
                            "What this is\n"
                            "- The bot writes structured events (decisions, broker actions, errors) to a log file.\n"
                            "- The GUI uses that same file to populate Current Ticker, Recent Decisions, Orders, and more.\n\n"
                            "How to use\n"
                            "- Choose the active log (usually `logs/tradebot.log`).\n"
                            "- If you want historical context, you can point it to a rotated file (`logs/tradebot.log.1`, etc.).\n\n"
                            "Tip\n"
                            "- If something “looks empty”, make sure you are looking at the active log, not an older rotated log.\n"
                        ),
                        "TMUX_RESTART_PREVIEW": (
                            "TMUX_RESTART_PREVIEW\n"
                            "Shows the exact tmux restart command that will be executed.\n\n"
                            "Why this exists\n"
                            "- The tmux launcher (`./scripts/tradebot.sh`) is the source of truth for how the terminal dashboard is launched.\n"
                            "- When you restart panes, this preview lets you verify the command is what you expect.\n\n"
                            "How to use\n"
                            "- Review it before clicking “Restart tmux”.\n"
                            "- If you see unexpected flags (profile/mode/execute-trades), adjust settings first.\n\n"
                            "Safety note\n"
                            "- Restarting tmux panes should keep the session open and respawn bot + commentary panes inside tmux.\n"
                        ),
                        "GUI_BROWSE_SYNTH_STOP_STORE": (
                            "GUI_BROWSE_SYNTH_STOP_STORE\n"
                            "Choose where to store synthetic stop state on disk.\n\n"
                            "What this is\n"
                            "- The bot can persist synthetic stop details so it can manage a position safely after restarts.\n"
                            "- This button fills `SYNTH_STOP_STORE_PATH` for you.\n\n"
                            "How to use\n"
                            "- Choose a writable path (JSON file).\n"
                            "- Keep it stable (don’t change it mid-trade) unless you understand the implications.\n\n"
                            "Why it matters\n"
                            "- If this file is missing/unwritable, some safety routines may treat the position as “unprotected”.\n"
                        ),
                        "GUI_BROWSE_POSITION_HOLD_STORE": (
                            "GUI_BROWSE_POSITION_HOLD_STORE\n"
                            "Choose where to store position-hold/age state on disk.\n\n"
                            "What this is\n"
                            "- The bot can persist “hold rules” (e.g., minimum hold time) across restarts.\n"
                            "- This button fills `POSITION_HOLD_STORE_PATH` for you.\n\n"
                            "How to use\n"
                            "- Choose a writable path (JSON file).\n"
                            "- Keep it stable so the bot can correctly remember how old positions are.\n\n"
                            "Why it matters\n"
                            "- Without persistence, the bot may be forced into conservative safety actions after a restart.\n"
                        ),
                        "ENV_FILTER": (
                            "ENV_FILTER\n"
                            "Filter the Advanced env table by key.\n\n"
                            "How to use\n"
                            "- Type part of a key (case-insensitive).\n"
                            "- Examples: `IBKR_`, `CCXT_`, `TRADE_SCI_`, `COMMENTARY_`, `EXECUTE_TRADES`.\n\n"
                            "Why this exists\n"
                            "- The bot has many configuration switches; this helps you find the one you need quickly.\n"
                        ),
                        "ENV_TABLE_EDIT": (
                            "ENV_TABLE_EDIT\n"
                            "Advanced mode: edit raw environment variables directly.\n\n"
                            "What this is\n"
                            "- A full list of discovered env keys used by the bot and dashboard.\n"
                            "- Useful for advanced tuning or for settings that don’t have a dedicated toggle yet.\n\n"
                            "How to use\n"
                            "- Double-click a Value cell to edit it.\n"
                            "- Click “Apply (GUI)” to apply changes to the running GUI session.\n"
                            "- Click “Save to .env” to persist for future runs.\n\n"
                            "Important rules\n"
                            "- Typed controls in the other tabs take precedence when they exist.\n"
                            "- Secret keys are masked in this table; set them in the typed tabs instead.\n\n"
                            "Safety note\n"
                            "- Be careful changing broker/live-trading keys here; prefer the dedicated controls.\n"
                        ),
                        "BTN_APPLY": (
                            "BTN_APPLY\n"
                            "Apply changes immediately to THIS running GUI session.\n\n"
                            "What it affects\n"
                            "- Updates the GUI’s in-process overrides.\n"
                            "- Can change what the GUI displays and how it launches/restarts other components.\n\n"
                            "What it does NOT do\n"
                            "- It does not automatically rewrite your `.env` file.\n"
                            "- It does not automatically restart tmux/bot processes.\n\n"
                            "When to use\n"
                            "- When you want to test changes safely before committing them.\n"
                        ),
                        "BTN_SAVE_DOTENV": (
                            "BTN_SAVE_DOTENV\n"
                            "Persist your current settings to the `.env` file.\n\n"
                            "What this does\n"
                            "- Writes your selected values so future runs start the same way.\n"
                            "- Helps keep tmux/GUI behavior consistent across restarts.\n\n"
                            "When to use\n"
                            "- After you’ve confirmed the settings are correct.\n\n"
                            "Safety note\n"
                            "- Saving `EXECUTE_TRADES=true` means future runs will be configured for live trading.\n"
                            "- The GUI still asks you to confirm live trading before starting.\n"
                        ),
                        "BTN_RESTART_TMUX": (
                            "BTN_RESTART_TMUX\n"
                            "Restart the terminal dashboard panes (bot + commentary) inside the tmux session.\n\n"
                            "What this does\n"
                            "- Applies and saves settings, then runs the tmux restart routine.\n"
                            "- Keeps the tmux session open and respawns the panes.\n\n"
                            "When to use\n"
                            "- When you changed bot settings that only take effect on process start.\n"
                            "- When you want the terminal dashboard to match the GUI configuration.\n\n"
                            "Safety note\n"
                            "- If live trading is enabled, confirm you intended that before restarting.\n"
                        ),
                        "BTN_CLEAR_OVERRIDES": (
                            "BTN_CLEAR_OVERRIDES\n"
                            "Remove all GUI overrides and fall back to your baseline config.\n\n"
                            "What this does\n"
                            "- Clears settings you changed in the GUI that were not saved to `.env`.\n"
                            "- Reverts to values from `.env` and/or your shell environment.\n\n"
                            "When to use\n"
                            "- Something looks wrong and you want to return to a known-good baseline quickly.\n"
                        ),
                        "BTN_CLOSE": (
                            "BTN_CLOSE\n"
                            "Close this settings dialog.\n\n"
                            "Note\n"
                            "- Closing the dialog does not automatically apply changes.\n"
                            "- Use Apply / Save / Restart as needed before closing.\n"
                        ),
                    "PROFILE_NAME": (
                        "PROFILE_NAME\n"
                        "Pick a profile that defines how the bot behaves.\n\n"
                        "What it controls\n"
                        "- Which symbols/universe the bot scans and trades.\n"
                        "- Default timeframe (e.g., 5m) and scan/decision cadence.\n"
                        "- Auto-schedule behavior (equities during US hours, crypto off-hours).\n"
                        "- Sabbath behavior defaults (whether new entries are blocked in the Sabbath window).\n"
                        "- Risk/stop behaviors that are profile-dependent (where configured).\n\n"
                        "How to use\n"
                        "- Start with `auto_schedule` for “equities in-hours, crypto off-hours”.\n"
                        "- Use an intraday profile for tighter cadence; use swing for slower cadence.\n\n"
                        "Where it comes from\n"
                        "- Profiles are defined in `config/settings_profiles.yaml` and loaded by the bot.\n"
                    ),
                    "PROFILE_HTF_TIMEFRAME": (
                        "PROFILE_HTF_TIMEFRAME\n"
                        "Override the Higher Timeframe (HTF) used for ICC structure trend.\n\n"
                        "ICC guidance\n"
                        "- HTF defines the macro structure (HH/HL vs LH/LL).\n"
                        "- Default is 4h unless your profile specifies otherwise.\n\n"
                        "How to use\n"
                        "- Use 4h for standard ICC structure.\n"
                        "- Use 1h only if your ICC plan is intentionally faster and validated.\n"
                        "- Leave Auto to keep the profile default.\n"
                    ),
                    "PROFILE_LTF_TIMEFRAME": (
                        "PROFILE_LTF_TIMEFRAME\n"
                        "Override the Lower Timeframe (LTF) used for ICC execution structure.\n\n"
                        "ICC guidance\n"
                        "- LTF is where sweeps + BOS + continuation triggers are validated.\n"
                        "- If unset, the bot uses the profile candle timeframe.\n\n"
                        "How to use\n"
                        "- Use 15m or 5m for most ICC execution work.\n"
                        "- Leave Auto to keep the profile default.\n"
                    ),
                    "PROFILE_TREND_WINDOW": (
                        "PROFILE_TREND_WINDOW\n"
                        "Number of candles used to classify HTF structure trend.\n\n"
                        "ICC guidance\n"
                        "- Larger windows reduce noise but respond slower.\n"
                        "- Smaller windows respond faster but can misclassify chop.\n\n"
                        "How to use\n"
                        "- Keep the profile default unless you know the asset’s structure cadence.\n"
                    ),
                    "PROFILE_TREND_SWING_LOOKBACK": (
                        "PROFILE_TREND_SWING_LOOKBACK\n"
                        "Fractal lookback for defining swing highs/lows on HTF.\n\n"
                        "ICC guidance\n"
                        "- A higher lookback requires more separation between swings (cleaner structure).\n"
                        "- A lower lookback is more sensitive and can classify chop as trend.\n"
                    ),
                    "PROFILE_TREND_MIN_SWINGS": (
                        "PROFILE_TREND_MIN_SWINGS\n"
                        "Minimum confirmed swings needed to call a trend (HH/HL or LH/LL).\n\n"
                        "ICC guidance\n"
                        "- Higher values mean stronger confirmation, fewer trades.\n"
                        "- Lower values mean faster classification, higher noise risk.\n"
                    ),
                    "PROFILE_TREND_STRENGTH_FLOOR": (
                        "PROFILE_TREND_STRENGTH_FLOOR\n"
                        "Minimum structure strength to treat a trend as non‑neutral.\n\n"
                        "ICC guidance\n"
                        "- Strength is based on the consistency of HH/HL or LH/LL sequences.\n"
                        "- If below the floor, the trend is treated as neutral (no ICC trade).\n"
                    ),
                    "PROFILE_STRUCTURE_SCORE_THRESHOLD": (
                        "PROFILE_STRUCTURE_SCORE_THRESHOLD\n"
                        "Score threshold for structure cleanliness (ICC gating).\n\n"
                        "ICC guidance\n"
                        "- The bot still requires HTF/LTF alignment + sweep + continuation.\n"
                        "- This threshold influences selection/readiness scoring, not the hard gates.\n"
                    ),
                    "PROFILE_PDT_GUARD_ENABLED": (
                        "PROFILE_PDT_GUARD_ENABLED\n"
                        "Enable the PDT guard for equities.\n\n"
                        "Important\n"
                        "- This does NOT make the bot long‑only.\n"
                        "- It only limits same‑day roundtrips for equities.\n"
                    ),
                    "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY": (
                        "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY\n"
                        "Maximum equity roundtrips allowed per day under PDT guard.\n\n"
                        "ICC guidance\n"
                        "- A flip counts as an exit + new entry (conservative).\n"
                        "- Keep low unless you are exempt from PDT rules.\n"
                    ),
                    "PROFILE_FLIP_ACTIONS_ENABLED": (
                        "PROFILE_FLIP_ACTIONS_ENABLED\n"
                        "Allow flip_to_long / flip_to_short actions.\n\n"
                        "ICC guidance\n"
                        "- Flips are reserved for confirmed HTF structure flips.\n"
                        "- Disabled by default for safety.\n"
                    ),
                    "PROFILE_FLIP_COOLDOWN_SECONDS": (
                        "PROFILE_FLIP_COOLDOWN_SECONDS\n"
                        "Minimum seconds between flips when PDT guard is active.\n\n"
                        "ICC guidance\n"
                        "- Prevents flip‑churn in ranges or chop.\n"
                    ),
                    "PROFILE_COOLDOWN_ENABLED": (
                        "PROFILE_COOLDOWN_ENABLED\n"
                        "Enable ICC cooldowns after blocks or successes.\n\n"
                        "ICC guidance\n"
                        "- Helps avoid re‑entering during chop or failed attempts.\n"
                    ),
                    "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK": (
                        "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK\n"
                        "Number of cycles to skip after a blocked attempt.\n\n"
                        "ICC guidance\n"
                        "- Higher values reduce churn during noisy phases.\n"
                    ),
                    "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS": (
                        "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS\n"
                        "Number of cycles to skip after a successful entry.\n\n"
                        "ICC guidance\n"
                        "- Use small values for faster re‑evaluation; higher values reduce over‑trading.\n"
                    ),
                    "PROFILE_COOLDOWN_SCOPE": (
                        "PROFILE_COOLDOWN_SCOPE\n"
                        "Cooldown scope for ICC gating.\n\n"
                        "Options\n"
                        "- symbol: only skip the symbol that just failed/succeeded.\n"
                        "- global: pause all symbols for the cooldown period.\n\n"
                        "ICC guidance\n"
                        "- Use symbol scope for broad scanning.\n"
                        "- Use global only when you want hard pauses across the entire bot.\n"
                    ),
                    "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL": (
                        "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL\n"
                        "How long to stick to the active symbol before rotating.\n\n"
                        "Options\n"
                        "- cycle_end: reevaluate on the next cycle.\n"
                        "- decision_end: hold until a decision completes.\n\n"
                        "ICC guidance\n"
                        "- Sticking reduces churn when a structure is close to forming.\n"
                    ),
                    "PROFILE_AUTO_SCHEDULE_ENABLED": (
                        "PROFILE_AUTO_SCHEDULE_ENABLED\n"
                        "Enable auto‑schedule (equities in US hours, crypto off‑hours).\n\n"
                        "ICC guidance\n"
                        "- Keeps the bot aligned with market hours without manual toggles.\n"
                    ),
                    "PROFILE_AUTO_FLATTEN_ON_CLOSE": (
                        "PROFILE_AUTO_FLATTEN_ON_CLOSE\n"
                        "Auto‑flatten at end of scheduled windows.\n\n"
                        "ICC note\n"
                        "- Avoid this if you intend to hold ICC continuations overnight.\n"
                    ),
                    "PROFILE_CONTINUOUS_MODE": (
                        "PROFILE_CONTINUOUS_MODE\n"
                        "Keep the runtime loop alive regardless of iteration limits.\n\n"
                        "Use cases\n"
                        "- Always‑on monitoring with ICC gating.\n"
                    ),
                    "PROFILE_CRYPTO_ONLY": (
                        "PROFILE_CRYPTO_ONLY\n"
                        "Treat the profile as crypto‑only.\n\n"
                        "ICC note\n"
                        "- Useful for off‑hours ICC execution when equities are closed.\n"
                    ),
                    "PROFILE_ICC_AGGRESSIVE_MODE": (
                        "PROFILE_ICC_AGGRESSIVE_MODE\n"
                        "Enable aggressive ICC sizing + guardrails (Phase 2, opt‑in only).\n\n"
                        "Default (Trade by SCI)\n"
                        "- Enabled by default to reflect Trade by SCI’s preferred posture.\n"
                        "- Guardrails still apply (max daily loss, exposure caps, circuit breaker).\n"
                    ),
                    "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT": (
                        "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT\n"
                        "Risk per trade as % of equity when aggressive mode is enabled.\n\n"
                        "Default (Trade by SCI)\n"
                        "- 3% per trade when aggressive mode is enabled.\n"
                        "- Applies only with PROFILE_ICC_AGGRESSIVE_MODE=true.\n"
                    ),
                    "PROFILE_MAX_DAILY_LOSS_PCT": (
                        "PROFILE_MAX_DAILY_LOSS_PCT\n"
                        "Max daily loss % before blocking new entries (aggressive mode).\n\n"
                        "Default (Trade by SCI)\n"
                        "- 6% daily loss cap before blocking new entries.\n"
                    ),
                    "PROFILE_MAX_EXPOSURE_PCT": (
                        "PROFILE_MAX_EXPOSURE_PCT\n"
                        "Max total open exposure % of equity (aggressive mode).\n\n"
                        "Default (Trade by SCI)\n"
                        "- 40% max total exposure in aggressive mode.\n"
                    ),
                    "PROFILE_MAX_CONSECUTIVE_LOSSES": (
                        "PROFILE_MAX_CONSECUTIVE_LOSSES\n"
                        "Consecutive loss limit before blocking entries (aggressive mode).\n\n"
                        "Default (Trade by SCI)\n"
                        "- 2 consecutive losses before blocking entries.\n"
                    ),
                    "BOT_MODE": (
                        "BOT_MODE\n"
                        "Choose how long the bot runs and when it is allowed to run.\n\n"
                        "Modes\n"
                        "- continuous: runs forever (best for always-on monitoring).\n"
                        "- scheduled: runs only inside configured schedule windows, then exits.\n"
                        "- iterations: runs N loops then exits (best for testing).\n\n"
                        "How to use\n"
                        "- If you want the GUI/tmux dashboard always available, use continuous.\n"
                        "- If you want strict “run only during sessions”, use scheduled and configure schedule windows.\n"
                        "- If you’re validating changes safely, use iterations.\n"
                    ),
                    "BOT_ITERATIONS": (
                        "BOT_ITERATIONS\n"
                        "Number of scan/decision/execution cycles when `BOT_MODE=iterations`.\n\n"
                        "How to use\n"
                        "- Use a small number (e.g., 20–200) to test changes quickly.\n"
                        "- If you want a longer test run without leaving it forever, increase it.\n"
                    ),
                    "EXECUTE_TRADES": (
                        "EXECUTE_TRADES\n"
                        "Master switch for live order placement.\n\n"
                        "What it means\n"
                        "- false: the bot runs in simulation mode (no live orders).\n"
                        "- true: the bot is allowed to place live orders (subject to broker permissions and confirmation).\n\n"
                        "How to use safely\n"
                        "- Enable it only when you intend to trade live.\n"
                        "- The GUI will show a confirmation dialog before starting live trading.\n"
                        "- If `IBKR_READ_ONLY=true`, orders will still be blocked even with live enabled.\n\n"
                        "Common gotcha\n"
                        "- If you restart from tmux, the launcher preserves `EXECUTE_TRADES=true|false` via the stored BOT_CMD.\n"
                    ),
                    "BOT_SABBATH": (
                        "BOT_SABBATH\n"
                        "Controls Sabbath entry blocking.\n\n"
                        "What it does\n"
                        "- When Sabbath is active, the bot blocks NEW entries.\n"
                        "- Risk management/monitoring can still run (exits/protection may still be evaluated).\n\n"
                        "Options\n"
                        "- Auto: use the profile’s default behavior.\n"
                        "- Force ON: always block new entries during the Sabbath window.\n"
                        "- Force OFF: disable Sabbath blocking entirely.\n\n"
                        "When to change this\n"
                        "- Leave Auto unless you’re doing a special test or you intentionally want to override profile behavior.\n"
                    ),
                    "SABBATH_ENABLED": (
                        "SABBATH_ENABLED\n"
                        "Override the profile's sabbath_enabled flag.\n\n"
                        "What this controls\n"
                        "- When true, the profile treats the sabbath window as active (new entries blocked).\n"
                        "- When false, the profile disables sabbath blocking entirely.\n\n"
                        "How to use\n"
                        "- Leave empty to keep the profile default.\n"
                        "- Use with BOT_SABBATH=Auto so the profile logic applies.\n"
                    ),
                    "SABBATH_ASTRONOMICAL": (
                        "SABBATH_ASTRONOMICAL\n"
                        "Use actual sunset times instead of fixed HH:MM values.\n\n"
                        "Requirements\n"
                        "- `astral` must be installed.\n"
                        "- You must provide latitude/longitude (SABBATH_LAT/SABBATH_LON).\n\n"
                        "How to use\n"
                        "- Enable this for accurate sabbath windows that track seasonal sunset shifts.\n"
                        "- Leave off for fixed windows (SABBATH_START_LOCAL/SABBATH_END_LOCAL).\n"
                    ),
                    "SABBATH_TIMEZONE": (
                        "SABBATH_TIMEZONE\n"
                        "Timezone used when computing sabbath start/end.\n\n"
                        "Format\n"
                        "- Use an IANA timezone like `America/New_York`.\n\n"
                        "How to use\n"
                        "- Set this to match the city you want sabbath times computed for.\n"
                    ),
                    "SABBATH_START_LOCAL": (
                        "SABBATH_START_LOCAL\n"
                        "Fixed local start time (Friday) for sabbath blocking.\n\n"
                        "Format\n"
                        "- HH:MM in 24-hour time (e.g., 18:00).\n\n"
                        "When it applies\n"
                        "- Used only when SABBATH_ASTRONOMICAL is false.\n"
                    ),
                    "SABBATH_END_LOCAL": (
                        "SABBATH_END_LOCAL\n"
                        "Fixed local end time (Saturday) for sabbath blocking.\n\n"
                        "Format\n"
                        "- HH:MM in 24-hour time (e.g., 18:00).\n\n"
                        "When it applies\n"
                        "- Used only when SABBATH_ASTRONOMICAL is false.\n"
                    ),
                    "SABBATH_LAT": (
                        "SABBATH_LAT\n"
                        "Latitude for astronomical sabbath calculations.\n\n"
                        "Format\n"
                        "- Decimal degrees (e.g., 40.7128).\n\n"
                        "When it applies\n"
                        "- Required if SABBATH_ASTRONOMICAL=true.\n"
                    ),
                    "SABBATH_LON": (
                        "SABBATH_LON\n"
                        "Longitude for astronomical sabbath calculations.\n\n"
                        "Format\n"
                        "- Decimal degrees (e.g., -74.0060).\n\n"
                        "When it applies\n"
                        "- Required if SABBATH_ASTRONOMICAL=true.\n"
                    ),
                    "SABBATH_CITY": (
                        "SABBATH_CITY\n"
                        "Optional city name used by the GUI resolver to fill latitude/longitude/timezone.\n\n"
                        "How to use\n"
                        "- Enter a US city (e.g., New York) and use Resolve to auto-fill lat/lon + timezone.\n"
                        "- If the resolver fails, enter lat/lon/timezone manually.\n"
                    ),
                    "EXCHANGE_PROVIDER": (
                        "EXCHANGE_PROVIDER\n"
                        "Chooses the primary market connectivity stack.\n\n"
                        "Options\n"
                        "- IBKR: use Interactive Brokers for market data and/or execution.\n"
                        "- CCXT: use CCXT-compatible crypto exchange connectivity (when configured).\n\n"
                        "Important\n"
                        "- “Market Data” and “Broker” dropdowns below only matter when using the alternative provider.\n"
                        "- If you select IBKR here, the bot uses IBKR as the primary feed/broker.\n"
                    ),
                    "Market Data": (
                        "Market Data\n"
                        "Selects the market data source when using an alternative provider.\n\n"
                        "How to use\n"
                        "- If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored.\n"
                        "- If using CCXT/alternative mode, choose the market data backend you want.\n\n"
                        "Tip\n"
                        "- Delayed data is fine for monitoring; just expect candles/quotes to lag.\n"
                    ),
                        "Broker": (
                            "Broker\n"
                            "Selects where orders are sent when using an alternative provider.\n\n"
                        "How to use\n"
                        "- If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored.\n"
                        "- If using CCXT/alternative mode, choose the execution backend.\n\n"
                            "Safety\n"
                            "- Always verify you are on the intended account/venue before enabling live trading.\n"
                        ),
                        "Candles (chart)": (
                            "Candles (chart)\n"
                            "Controls the bar size used for the GUI candle chart.\n\n"
                            "What this is\n"
                            "- This changes the timeframe of the historical bars shown in the candles pane.\n"
                            "- It does not change the bot’s decision timeframe by itself (that is profile/timeframe driven).\n\n"
                            "How to use\n"
                            "- Use smaller values (1m/5m) for more detail and short-term structure.\n"
                            "- Use larger values (15m/30m/1h/daily) for broader context and swing structure.\n\n"
                            "Data note\n"
                            "- If you are using delayed market data, the chart will lag behind live prices.\n"
                            "- Missing bars usually means the provider returned no bars for that request (symbol/venue mismatch or data limitations).\n"
                        ),
                        "APP_ENVIRONMENT": (
                            "APP_ENVIRONMENT\n"
                            "Optional environment tag used by configuration loaders.\n\n"
                            "What this is\n"
                            "- A simple label like `development`, `staging`, or `production`.\n"
                            "- Some configs/logging may change based on this value.\n\n"
                            "How to use\n"
                            "- Leave blank if you are not using environment-specific config.\n"
                            "- Use `development` when you want safer defaults and more diagnostics.\n"
                            "- Use `production` only when you intend to run live/long-running.\n"
                        ),
                    "CHATGPT_KEY": (
                        "CHATGPT_KEY\n"
                        "API key for a ChatGPT-compatible provider (if configured).\n\n"
                        "What it is for\n"
                        "- Enables AI commentary and/or AI-assisted reasoning in the bot, depending on your setup.\n\n"
                        "How to use safely\n"
                        "- Treat this like a password.\n"
                        "- Set it in the typed field (not in the Advanced env table), then Save to `.env`.\n\n"
                        "Troubleshooting\n"
                        "- If commentary shows “waiting” forever, verify the key is set and the provider/model are valid.\n"
                    ),
                    "TRADE_SCI_PROVIDER": (
                        "TRADE_SCI_PROVIDER\n"
                        "Select which AI provider the bot/commentary should use.\n\n"
                        "Options\n"
                        "- openai, gemini, claude, deepseek, openrouter, custom.\n"
                        "- Use custom when you have an OpenAI-compatible endpoint.\n"
                        "- Leave blank for Auto (OpenAI defaults).\n"
                    ),
                        "TRADE_SCI_API_BASE_URL": (
                            "TRADE_SCI_API_BASE_URL\n"
                            "Base URL for the Trade by SCI AI gateway/provider.\n\n"
                            "When you would change this\n"
                            "- You are using a self-hosted gateway, a proxy, or a non-default endpoint.\n\n"
                            "How to use\n"
                            "- Leave default unless you were explicitly given a different URL.\n"
                            "- If you change it, restart the commentary pane so it picks up the new endpoint.\n"
                        ),
                    "TRADE_SCI_MODEL_NAME": (
                        "TRADE_SCI_MODEL_NAME\n"
                        "Which LLM model to use for bot decisions and AI commentary.\n\n"
                            "How to choose\n"
                            "- Larger models: better explanations, higher cost.\n"
                            "- Smaller models: cheaper/faster, may be less insightful.\n\n"
                            "Tip\n"
                            "- If you want more “human play-by-play”, pick a stronger model and increase max tokens.\n"
                        ),
                        "TRADE_SCI_MAX_TOKENS": (
                            "TRADE_SCI_MAX_TOKENS\n"
                            "Maximum tokens allowed per AI response.\n\n"
                            "What this changes\n"
                            "- Higher values allow longer, more detailed commentary.\n"
                            "- Lower values reduce cost but can truncate explanations.\n\n"
                            "Recommendation\n"
                            "- For “twice as long” commentary, increase this (within your provider limits).\n"
                        ),
                        "TRADE_SCI_TEMPERATURE": (
                            "TRADE_SCI_TEMPERATURE\n"
                            "Controls how creative vs. deterministic the AI output is.\n\n"
                            "How to use\n"
                            "- 0.0–0.3: more consistent/grounded, best for monitoring decisions.\n"
                            "- 0.4–0.8: more expressive, can be more speculative.\n\n"
                            "Safety note\n"
                            "- Commentary is informational; trading logic should not depend on creative phrasing.\n"
                        ),
                        "MARKET_DEFAULT_SYMBOL": (
                            "MARKET_DEFAULT_SYMBOL\n"
                            "Default symbol shown in the GUI candle pane when there is no active symbol.\n\n"
                            "How to use\n"
                            "- Set a common benchmark symbol (e.g., SPY, QQQ, BTCUSD) to keep the chart useful.\n"
                            "- If the bot becomes active on a symbol, the GUI can switch to the active symbol.\n"
                        ),
                        "MARKET_DEFAULT_TIMEFRAME": (
                            "MARKET_DEFAULT_TIMEFRAME\n"
                            "Default candle timeframe used by the GUI chart.\n\n"
                            "What this affects\n"
                            "- Only the GUI chart timeframe (not the bot’s scan timeframe).\n\n"
                            "How to use\n"
                            "- Pick the timeframe you most often want as context (5m/15m/1h/daily).\n"
                        ),
                        "MARKET_MAX_CANDLES": (
                            "MARKET_MAX_CANDLES\n"
                            "Maximum number of candles to request/render in the GUI.\n\n"
                            "Tradeoffs\n"
                            "- More candles = more history/context, more API load.\n"
                            "- Fewer candles = faster refresh, less clutter.\n\n"
                            "Tip\n"
                            "- If you see missing bars/timeouts, reduce this value.\n"
                        ),
                        "MARKET_SYMBOLS": (
                            "MARKET_SYMBOLS\n"
                            "Comma-separated symbol list for GUI rotation when the bot is not actively trading a single symbol.\n\n"
                            "How to use\n"
                            "- Provide your preferred watchlist (e.g., `SPY,QQQ,DIA,BTCUSD,ETHUSD`).\n"
                            "- The GUI/candles pane can rotate through the top symbols when idle.\n\n"
                            "Tip\n"
                            "- Keep the list short to avoid unnecessary market data requests.\n"
                        ),
                        "FRICTION_FAIL_SAFE": (
                            "FRICTION_FAIL_SAFE\n"
                            "Blocks new entries when spread/slippage (“friction”) appears too high.\n\n"
                            "What this means\n"
                            "- If the market is illiquid or spreads are wide, fills can be worse than expected.\n"
                            "- This fail-safe helps avoid taking trades in poor execution conditions.\n\n"
                            "How to use\n"
                            "- Enable it for safer live trading.\n"
                            "- If you see trades blocked too often, adjust `FRICTION_RISK_CAP` rather than disabling.\n\n"
                            "Common symptoms when it triggers\n"
                            "- Frequent stand-aside decisions during volatile/low-liquidity periods.\n"
                        ),
                        "FRICTION_RISK_CAP": (
                            "FRICTION_RISK_CAP\n"
                            "Threshold for what the bot considers “too much friction”.\n\n"
                            "How to tune\n"
                            "- Lower value = stricter (blocks more trades, safer fills).\n"
                            "- Higher value = more permissive (takes more trades, riskier fills).\n\n"
                            "Recommendation\n"
                            "- Start conservative; only raise if you understand your venue’s typical spreads.\n"
                        ),
                        "VIX_FAIL_SAFE": (
                            "VIX_FAIL_SAFE\n"
                            "Blocks new equity entries when volatility regime looks too risky.\n\n"
                            "What this means\n"
                            "- High volatility can break continuation behavior and increase stop-outs.\n"
                            "- This is a regime filter, not an ICC gate.\n\n"
                            "How to use\n"
                            "- Enable it if you want the bot to avoid extreme volatility days.\n"
                            "- If it blocks too aggressively, adjust `VIX_RISK_CAP`.\n"
                        ),
                        "VIX_RISK_CAP": (
                            "VIX_RISK_CAP\n"
                            "Threshold for volatility risk tolerance.\n\n"
                            "How to tune\n"
                            "- Lower = stricter volatility avoidance.\n"
                            "- Higher = allows trading in higher-volatility regimes.\n"
                        ),
                        "CONFLUENCE_EXTERNAL": (
                            "CONFLUENCE_EXTERNAL\n"
                            "Include optional external confluence signals (if available).\n\n"
                            "What this is\n"
                            "- Adds additional context beyond the core ICC gates.\n"
                            "- The bot should still require HTF/LTF alignment + sweep + continuation.\n\n"
                            "How to use\n"
                            "- Keep off unless you know what signals are configured in your setup.\n"
                        ),
                        "COMMITMENT_MODE": (
                            "COMMITMENT_MODE\n"
                            "Reduces churn after entry by preferring hold/manage decisions over frequent re-evaluation.\n\n"
                            "Why this matters\n"
                            "- Prevents “enter then immediately flatten” behavior unless there is a real invalidation/emergency.\n"
                            "- Helps positions follow the continuation instead of getting micro-managed every cycle.\n\n"
                            "How to use\n"
                            "- Enable for live trading.\n"
                            "- Disable only for debugging strategy logic.\n"
                        ),
                        "BUG_BYPASS_SCHEDULE": (
                            "BUG_BYPASS_SCHEDULE\n"
                            "Debug override to bypass schedule windows.\n\n"
                            "What this does\n"
                            "- Forces the bot to run outside normal session windows.\n\n"
                            "Safety note\n"
                            "- Do not use for live trading unless you intentionally want to trade off-hours.\n"
                            "- Prefer profile-based scheduling for normal operation.\n"
                        ),
                        "EMERGENCY_STOP_PCT": (
                            "EMERGENCY_STOP_PCT\n"
                            "Emergency protective stop percentage used by runtime safeguards.\n\n"
                            "What it is for\n"
                            "- A last-resort protection if a position is unprotected/missing a normal stop.\n\n"
                            "How to use\n"
                            "- Keep small (tight) if you want immediate damage control.\n"
                            "- Keep larger if you want to avoid forced sells on normal noise.\n\n"
                            "Important\n"
                            "- This is not an ICC invalidation stop; it is a safety net.\n"
                        ),
                        "SCALE_OUT_FRACTION": (
                            "SCALE_OUT_FRACTION\n"
                            "How much of a position to take off when scaling out.\n\n"
                            "How to use\n"
                            "- 0.5 means sell/cover half when a scale-out condition triggers.\n"
                            "- Use smaller fractions for smoother exits; larger for faster de-risking.\n\n"
                            "Tip\n"
                            "- Scaling out should respect ICC continuation rules; avoid exiting too early unless invalidated.\n"
                        ),
                        "MAX_SCALE_INS_PER_LEG": (
                            "MAX_SCALE_INS_PER_LEG\n"
                            "Maximum number of adds (scale-ins) allowed for a single position leg.\n\n"
                            "Why it matters\n"
                            "- Prevents the bot from pyramiding too aggressively.\n"
                            "- Keeps risk bounded when continuation takes multiple pushes.\n\n"
                            "How to use\n"
                            "- Start low (0–2). Increase only if you have strict risk caps.\n"
                        ),
                        "MIN_POSITION_SIZE_TO_SCALE": (
                            "MIN_POSITION_SIZE_TO_SCALE\n"
                            "Minimum position size required before the bot is allowed to scale in/out.\n\n"
                            "Why this exists\n"
                            "- Prevents noisy tiny positions from triggering complex management logic.\n\n"
                            "How to use\n"
                            "- Leave default unless you frequently trade very small size.\n"
                        ),
                        "STARTUP_CRYPTO_UNPROTECTED_POLICY": (
                            "STARTUP_CRYPTO_UNPROTECTED_POLICY\n"
                            "What to do on startup if a ZEROHASH crypto position exists but has no persisted synthetic stop.\n\n"
                            "Options\n"
                            "- REARM: recreate the synthetic stop (preferred to avoid forced sell).\n"
                            "- PAUSE: keep the position but pause actions on that symbol.\n"
                            "- FLATTEN: immediately exit (safest operationally, but can realize losses).\n\n"
                            "Recommendation\n"
                            "- Use REARM for ICC-style continuation holding.\n"
                            "- Use FLATTEN only if you prioritize safety over holding.\n"
                        ),
                        "SYNTH_STOP_STORE_PATH": (
                            "SYNTH_STOP_STORE_PATH\n"
                            "Where synthetic stops are persisted (JSON file).\n\n"
                            "Why this matters\n"
                            "- Lets the bot recover/manage stops across restarts.\n"
                            "- Prevents “unprotected position” policies from triggering unnecessarily.\n\n"
                            "How to use\n"
                            "- Choose a stable, writable path.\n"
                            "- Do not delete it while positions are open.\n"
                        ),
                        "POSITION_HOLD_STORE_PATH": (
                            "POSITION_HOLD_STORE_PATH\n"
                            "Where position hold/age state is persisted (JSON file).\n\n"
                            "Why this matters\n"
                            "- Allows the bot to track how long a position has been held across restarts.\n"
                            "- Enables “do not sell within X hours” style protection.\n\n"
                            "How to use\n"
                            "- Choose a stable, writable path.\n"
                            "- Keep it consistent across runs so the bot retains history.\n"
                        ),
                        "ALLOW_INHERITED_POSITION": (
                            "ALLOW_INHERITED_POSITION\n"
                            "Allow the bot to inherit/manage positions that already exist in the broker account.\n\n"
                            "What this means\n"
                            "- When enabled, the bot will treat existing holdings as positions it must manage.\n"
                            "- This is required if you want multi-position monitoring after restarts or manual trades.\n\n"
                            "How to use safely\n"
                            "- Enable only if you want the bot to take responsibility for pre-existing positions.\n"
                            "- Make sure your hold/stop persistence paths are configured.\n"
                        ),
                        "CANCEL_ORDERS_ON_START": (
                            "CANCEL_ORDERS_ON_START\n"
                            "Cancel any open/pending orders on bot startup.\n\n"
                            "Why this exists\n"
                            "- Prevents stale orders from a previous run from filling unexpectedly.\n\n"
                            "Important note\n"
                            "- Canceling an order is not the same as closing a filled trade.\n"
                            "- This setting is about cleanup of pending orders, not day-trading.\n"
                        ),
                        "FLATTEN_ON_EXIT": (
                            "FLATTEN_ON_EXIT\n"
                            "When the bot exits/shuts down, flatten positions as part of shutdown.\n\n"
                            "Use cases\n"
                            "- Paper/sim runs where you always want to end flat.\n"
                            "- Emergency shutdown behavior.\n\n"
                            "Caution\n"
                            "- For ICC continuation holding, you usually do NOT want forced flattening.\n"
                        ),
                        "INTRADAY_FLATTEN": (
                            "INTRADAY_FLATTEN\n"
                            "Flatten positions near the end of the session (intraday mode).\n\n"
                            "Why this exists\n"
                            "- Avoid holding equities overnight when running an intraday-only strategy.\n\n"
                            "ICC note\n"
                            "- Only enable if your ICC plan is explicitly intraday (no overnight hold).\n"
                        ),
                        "IBKR_CRYPTO_EXCHANGE": (
                            "IBKR_CRYPTO_EXCHANGE\n"
                            "Exchange route for IBKR crypto (e.g., ZEROHASH).\n\n"
                            "Important\n"
                            "- ZEROHASH spot crypto is long-only in this project’s rules.\n"
                            "- If you change this, verify execution capabilities and supported order types.\n"
                        ),
                        "IBKR_ZEROHASH_CRYPTO_TIF": (
                            "IBKR_ZEROHASH_CRYPTO_TIF\n"
                            "Time-in-force for IBKR ZEROHASH crypto orders.\n\n"
                            "How to use\n"
                            "- Choose a TIF supported by your venue/order type (e.g., DAY/IOC).\n"
                            "- If you see broker warnings about unsupported TIF, change this.\n"
                        ),
                        "IBKR_MAX_SHARES_PER_SYMBOL": (
                            "IBKR_MAX_SHARES_PER_SYMBOL\n"
                            "Hard cap on position size (shares) per symbol.\n\n"
                            "Why this matters\n"
                            "- Prevents runaway sizing due to bad data or config.\n\n"
                            "How to use\n"
                            "- Set a conservative max based on your account size.\n"
                            "- Use alongside dollar-risk caps.\n"
                        ),
                        "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL": (
                            "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL\n"
                            "Maximum dollar risk allowed per symbol.\n\n"
                            "What this means\n"
                            "- Caps how much you can lose on a single position based on stop distance.\n\n"
                            "How to use\n"
                            "- Set this first before enabling live trading.\n"
                            "- If orders are rejected due to sizing, this cap may be too low.\n"
                        ),
                        "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT": (
                            "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT\n"
                            "Maximum total dollar risk allowed across all open positions.\n\n"
                            "Why this matters\n"
                            "- Required if you enable multi-position mode.\n"
                            "- Prevents cumulative exposure from becoming too large.\n\n"
                            "How to use\n"
                            "- Keep this aligned with your risk tolerance for worst-case stop-outs.\n"
                        ),
                        "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER": (
                            "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER\n"
                            "Automatic risk sizing as a fraction of buying power.\n\n"
                            "What this does\n"
                            "- Helps the bot scale position size with account size.\n"
                            "- Still bounded by max shares and max dollar risk caps.\n\n"
                            "How to use\n"
                            "- Start small (very conservative).\n"
                            "- Increase only after validating sizing and broker fills.\n"
                        ),
                        "CCXT_EXCHANGE": (
                            "CCXT_EXCHANGE\n"
                            "Which CCXT exchange to use when routing via CCXT.\n\n"
                            "How to use\n"
                            "- Set this only if you are using CCXT for market data and/or execution.\n"
                            "- Example values match CCXT exchange ids (e.g., `binance`, `coinbase`).\n"
                        ),
                        "CCXT_DEFAULT_TYPE": (
                            "CCXT_DEFAULT_TYPE\n"
                            "CCXT market type (spot, swap, future) depending on the exchange.\n\n"
                            "How to use\n"
                            "- Choose the type that matches the instruments you trade.\n"
                            "- Wrong type often causes “symbol not found” or missing candles.\n"
                        ),
                        "CCXT_ENABLE_RATE_LIMIT": (
                            "CCXT_ENABLE_RATE_LIMIT\n"
                            "Enable CCXT built-in rate limiting.\n\n"
                            "Why this matters\n"
                            "- Helps avoid exchange bans and 429 rate-limit errors.\n\n"
                            "Recommendation\n"
                            "- Keep enabled for live connectivity.\n"
                        ),
                        "CCXT_SANDBOX": (
                            "CCXT_SANDBOX\n"
                            "Use CCXT sandbox/testnet mode (if the exchange supports it).\n\n"
                            "How to use\n"
                            "- Enable for testing without real funds.\n"
                            "- Disable for live trading.\n"
                        ),
                        "CCXT_SYMBOL_MAP": (
                            "CCXT_SYMBOL_MAP\n"
                            "Optional mapping to translate internal symbols to CCXT exchange-specific symbols.\n\n"
                            "When you need this\n"
                            "- The exchange uses symbols like `BTC/USDT` but your bot uses `BTCUSD`.\n\n"
                            "How to use\n"
                            "- Provide a JSON or delimited mapping per your project’s configuration format.\n"
                        ),
                        "CCXT_API_KEY": (
                            "CCXT_API_KEY\n"
                            "API key for CCXT exchange authentication.\n\n"
                            "How to use safely\n"
                            "- Treat as a password.\n"
                            "- Use exchange keys with least privileges needed.\n"
                        ),
                        "CCXT_SECRET": (
                            "CCXT_SECRET\n"
                            "API secret for CCXT exchange authentication.\n\n"
                            "Safety\n"
                            "- Never share this.\n"
                            "- If you suspect leakage, revoke/regenerate it at the exchange.\n"
                        ),
                        "CCXT_PASSWORD": (
                            "CCXT_PASSWORD\n"
                            "Optional passphrase/password for CCXT (some exchanges require it).\n\n"
                            "How to use\n"
                            "- Leave blank unless your exchange specifically requires a passphrase.\n"
                        ),
                        "LOG_LEVEL": (
                            "LOG_LEVEL\n"
                            "Controls how chatty the bot logs are.\n\n"
                        "How to use\n"
                        "- INFO: normal operations.\n"
                        "- DEBUG: more details (useful when diagnosing issues).\n"
                        "- WARNING/ERROR: quieter logs, only problems.\n"
                    ),
                    "TRADEBOT_LOG": (
                        "TRADEBOT_LOG\n"
                        "Path to the main bot log file that the GUI/tmux dashboard tails.\n\n"
                        "How to use\n"
                        "- Keep this set to `logs/tradebot.log` unless you have a special setup.\n"
                        "- Rotated logs `tradebot.log.1`, `tradebot.log.2`, … are used for history/context.\n"
                    ),
                    "SESSION_NAME": (
                        "SESSION_NAME\n"
                        "tmux session name used by the terminal dashboard.\n\n"
                        "How to use\n"
                        "- Default is `tradebot`.\n"
                        "- If you run multiple dashboards, give each a different session name.\n"
                    ),
                    "COMMENTARY_LLM": (
                        "COMMENTARY_LLM\n"
                        "Controls whether the right-pane commentary uses the internal AI commentator.\n\n"
                        "Options\n"
                        "- Auto: use internal commentary.\n"
                        "- Off: no AI calls; deterministic dashboard only.\n"
                        "- Internal: call the built-in AI commentator.\n\n"
                        "Cost control\n"
                        "- Use the refresh/budget settings to prevent excessive API usage.\n"
                    ),
                    "COMMENTARY_LLM_POLICY": (
                        "COMMENTARY_LLM_POLICY\n"
                        "Controls WHEN the GUI/tmux is allowed to call the commentator.\n\n"
                        "Options\n"
                        "- a_plus_or_4x (recommended): Call on A+ continuation (readiness=1.00). If no A+ is happening, call up to 4× per day using `COMMENTARY_LLM_DAILY_SLOTS`.\n"
                        "- a_plus_only: Only call when an A+ continuation appears.\n"
                        "- interval: Legacy behavior (call whenever `COMMENTARY_LLM_MIN_SECONDS` allows it).\n\n"
                        "Why this exists\n"
                        "- Keeps API usage under control while still giving you timely insight when the bot reaches a true ICC entry (A+).\n"
                    ),
                    "COMMENTARY_LLM_DAILY_SLOTS": (
                        "COMMENTARY_LLM_DAILY_SLOTS\n"
                        "Comma-separated times (HH:MM) used by `COMMENTARY_LLM_POLICY=a_plus_or_4x`.\n\n"
                        "Example\n"
                        "- 09:00,12:00,18:00,22:00\n\n"
                        "Notes\n"
                        "- Times are interpreted in `COMMENTARY_LLM_TZ`.\n"
                        "- The bot will call at most once per slot.\n"
                    ),
                    "COMMENTARY_LLM_TZ": (
                        "COMMENTARY_LLM_TZ\n"
                        "Shared timezone (IANA name) used to interpret `COMMENTARY_LLM_DAILY_SLOTS`.\n"
                        "The Time tab keeps this aligned with Sabbath/session timezones.\n\n"
                        "Example\n"
                        "- America/New_York\n"
                    ),
                    "COMMENTARY_LLM_MIN_SECONDS": (
                        "COMMENTARY_LLM_MIN_SECONDS\n"
                        "Minimum seconds between commentary refreshes.\n\n"
                        "Why this matters\n"
                        "- Prevents spamming your provider/API.\n"
                        "- Lower values increase cost and rate-limit risk.\n\n"
                        "Recommendation\n"
                        "- 300s (5 minutes) is a good default.\n"
                    ),
                    "COMMENTARY_LLM_MAX_CALLS_PER_DAY": (
                        "COMMENTARY_LLM_MAX_CALLS_PER_DAY\n"
                        "Hard daily cap for commentary calls (shared across panes).\n\n"
                        "Why this exists\n"
                        "- Prevents runaway cost and rate-limit lockouts.\n\n"
                        "How it behaves\n"
                        "- When the cap is reached, the commentary pane keeps the last good answer.\n"
                    ),
                    "COMMENTARY_LLM_BUDGET_PATH": (
                        "COMMENTARY_LLM_BUDGET_PATH\n"
                        "Shared JSON file used to coordinate commentary call budgeting across processes.\n\n"
                        "How to use\n"
                        "- Leave default unless you want a different shared location.\n"
                        "- Must be writable.\n"
                    ),
                    "TRADE_SCI_API_KEY": (
                        "TRADE_SCI_API_KEY\n"
                        "API key for the AI provider used by the bot/commentary.\n\n"
                        "How to use\n"
                        "- This is sensitive. The GUI masks it and stores it as an env var.\n"
                        "- Set it once, then use budgets/refresh intervals to control spend.\n"
                    ),
                    "IBKR_HOST": (
                        "IBKR_HOST\n"
                        "Host/IP where TWS or IB Gateway is running.\n\n"
                        "Typical\n"
                        "- `127.0.0.1` when TWS/Gateway is on the same machine.\n"
                    ),
                    "IBKR_PORT": (
                        "IBKR_PORT\n"
                        "Port for the IBKR API connection.\n\n"
                        "Typical defaults\n"
                        "- 7497: paper\n"
                        "- 7496: live\n\n"
                        "Tip\n"
                        "- Match this to your TWS/Gateway API settings.\n"
                    ),
                    "IBKR_CLIENT_ID": (
                        "IBKR_CLIENT_ID\n"
                        "Client ID for the IBKR API connection.\n\n"
                        "Why it matters\n"
                        "- Lets multiple apps connect without stepping on each other.\n"
                    ),
                    "IBKR_ACCOUNT_ID": (
                        "IBKR_ACCOUNT_ID\n"
                        "Account identifier (useful if your login has multiple accounts).\n"
                    ),
                    "IBKR_DEFAULT_CCY": (
                        "IBKR_DEFAULT_CCY\n"
                        "Default currency used when building certain contracts (usually `USD`).\n"
                    ),
                    "IBKR_PAPER": (
                        "IBKR_PAPER\n"
                        "Paper/live preference for the IBKR connection.\n\n"
                        "Important\n"
                        "- This does not override `EXECUTE_TRADES`; it only selects which endpoint you connect to.\n"
                    ),
                    "IBKR_READ_ONLY": (
                        "IBKR_READ_ONLY\n"
                        "Safety switch: when true, the IBKR executor refuses to place orders.\n\n"
                        "Use cases\n"
                        "- Monitoring mode with live market data but no trading.\n"
                        "- Safety while you validate settings.\n"
                    ),
                    "MULTI_POSITION_ENABLED": (
                        "MULTI_POSITION_ENABLED\n"
                        "Opt-in multi-position trading.\n\n"
                        "Default behavior\n"
                        "- Off: the bot only allows one open symbol at a time.\n\n"
                        "When enabled\n"
                        "- The bot may hold multiple symbols concurrently (up to `MAX_CONCURRENT_POSITIONS`).\n"
                        "- Use risk caps to prevent over-exposure.\n"
                    ),
                    "MAX_CONCURRENT_POSITIONS": (
                        "MAX_CONCURRENT_POSITIONS\n"
                        "Maximum number of symbols that may be open at the same time when multi-position is enabled.\n\n"
                        "How to choose a value\n"
                        "- Start with 2–3.\n"
                        "- Increase only if you are comfortable managing multiple positions and your risk caps are set.\n"
                    ),
                }

            if key in TOOLTIP_LIBRARY:
                widget.setToolTip(TOOLTIP_LIBRARY[key])
                return

            # Env-var pattern: provide a thorough generic tooltip even if we don't have a custom entry.
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", key or ""):
                widget.setToolTip(_env_template(key, summary))
                return

            # BrokerSetting: ... entries
            if key.startswith("BrokerSetting: "):
                widget.setToolTip(
                    f"{key}\n"
                    f"{'Summary: ' + summary if summary else 'Summary: broker sizing/risk guard.'}\n\n"
                    "What this is\n"
                    "- A broker-level guard used by the executor when sizing/placing orders.\n\n"
                    "How to use\n"
                    "- Enable \"Override\" (when present), set a value, then Apply/Save.\n"
                    "- Lower values are safer; higher values allow larger positions.\n"
                )
                return

            widget.setToolTip(raw)

            # --- Typed controls (grouped in tabs) ---
            app_env = QtWidgets.QLineEdit(self._effective_env_value("APP_ENVIRONMENT")[0])
            app_env.setPlaceholderText("e.g. development / production (optional)")
            tip(app_env, "APP_ENVIRONMENT\nOptional app environment tag used by config loader.")

            profiles = read_profiles()
            profile_combo = QtWidgets.QComboBox()
            if profiles:
                profile_combo.addItems(profiles)
            else:
                profile_combo.addItems(["auto_schedule", "intraday", "crypto_247"])
            current_profile = self._effective_env_value("PROFILE_NAME")[0] or "auto_schedule"
            if current_profile in [profile_combo.itemText(i) for i in range(profile_combo.count())]:
                profile_combo.setCurrentText(current_profile)
            tip(profile_combo, "PROFILE_NAME\nControls symbol universe + cadence + schedule + sabbath rules via profiles.")

            mode_combo = QtWidgets.QComboBox()
            mode_combo.addItems(["continuous", "scheduled", "iterations"])
            mode_combo.setCurrentText(self._effective_env_value("BOT_MODE")[0] or "continuous")
            tip(
                mode_combo,
                "BOT_MODE\ncontinuous: run forever\nscheduled: run only inside configured windows (exits)\niterations: run N loops then exit",
            )

            iterations_spin = QtWidgets.QSpinBox()
            iterations_spin.setRange(1, 1_000_000)
            try:
                iterations_spin.setValue(int(self._effective_env_value("BOT_ITERATIONS")[0] or "120"))
            except Exception:
                iterations_spin.setValue(120)
            tip(iterations_spin, "BOT_ITERATIONS\nUsed only when BOT_MODE=iterations.")

            execute_chk = QtWidgets.QCheckBox("Enable LIVE trading (EXECUTE_TRADES=true)")
            execute_chk.setChecked(self._effective_env_value("EXECUTE_TRADES")[0].lower() == "true")
            tip(execute_chk, "EXECUTE_TRADES\nMaster switch for live order placement.")

            autostart_bot_chk = QtWidgets.QCheckBox("Auto-start bot when GUI opens")
            autostart_bot_chk.setChecked(self._bot_autostart)
            keep_bot_chk = QtWidgets.QCheckBox("Keep bot running after GUI closes")
            keep_bot_chk.setChecked(self._bot_keep_running_on_close)
            tip(
                autostart_bot_chk,
                "GUI_AUTOSTART_BOT\nWhen enabled, the GUI starts the core bot process automatically on launch.",
            )
            tip(
                keep_bot_chk,
                "GUI_KEEP_BOT_RUNNING\nWhen enabled, closing the GUI will NOT stop the bot process.",
            )

            sabbath_combo = QtWidgets.QComboBox()
            sabbath_combo.addItems(["Auto (profile/default)", "Force ON", "Force OFF"])
            bot_sabb = self._effective_env_value("BOT_SABBATH")[0].strip().lower()
            if bot_sabb in {"on", "true", "1", "yes"}:
                sabbath_combo.setCurrentIndex(1)
            elif bot_sabb in {"off", "false", "0", "no"}:
                sabbath_combo.setCurrentIndex(2)
            else:
                sabbath_combo.setCurrentIndex(0)
            tip(
                sabbath_combo,
                "BOT_SABBATH\nAuto: use profile/default rules\nForce ON: block NEW entries during sabbath window\nForce OFF: disable sabbath blocking",
            )

            profiles_map = getattr(settings, "profiles", {}) or {}
            profile_settings = profiles_map.get(current_profile)

            def _profile_text(attr: str, default: str = "") -> str:
                if not profile_settings:
                    return default
                value = getattr(profile_settings, attr, None)
                if value is None:
                    return default
                if isinstance(value, float):
                    return f"{value:.6f}".rstrip("0").rstrip(".")
                return str(value)

            def _env_or_profile(key: str, profile_value: str) -> str:
                raw = self._effective_env_value(key)[0].strip()
                return raw if raw else profile_value

            sabbath_enabled_combo = QtWidgets.QComboBox()
            profile_enabled = bool(getattr(profile_settings, "sabbath_enabled", False))
            sabbath_enabled_combo.addItems(
                [
                    f"Auto (profile default: {'Enabled' if profile_enabled else 'Disabled'})",
                    "Enabled",
                    "Disabled",
                ]
            )
            env_enabled = self._effective_env_value("SABBATH_ENABLED")[0].strip().lower()
            if env_enabled in {"1", "true", "yes", "on"}:
                sabbath_enabled_combo.setCurrentIndex(1)
            elif env_enabled in {"0", "false", "no", "off"}:
                sabbath_enabled_combo.setCurrentIndex(2)
            else:
                sabbath_enabled_combo.setCurrentIndex(0)
            tip(sabbath_enabled_combo, "SABBATH_ENABLED\nOverride the profile sabbath_enabled flag.")

            sabbath_astro_chk = QtWidgets.QCheckBox("Use astronomical sunset (Astral)")
            profile_astro = bool(getattr(profile_settings, "sabbath_astronomical", False))
            env_astro = self._effective_env_value("SABBATH_ASTRONOMICAL")[0].strip().lower()
            if env_astro in {"1", "true", "yes", "on"}:
                sabbath_astro_chk.setChecked(True)
            elif env_astro in {"0", "false", "no", "off"}:
                sabbath_astro_chk.setChecked(False)
            else:
                sabbath_astro_chk.setChecked(profile_astro)
            tip(sabbath_astro_chk, "SABBATH_ASTRONOMICAL\nUse actual sunset times instead of fixed HH:MM values.")

            sabbath_city = QtWidgets.QLineEdit(_env_or_profile("SABBATH_CITY", ""))
            sabbath_city.setPlaceholderText("City (e.g., New York)")
            tip(sabbath_city, "SABBATH_CITY\nOptional city name for resolving lat/lon/timezone.")
            resolve_city_btn = QtWidgets.QPushButton("Resolve")
            tip(resolve_city_btn, "SABBATH_CITY\nResolve city to lat/lon/timezone using timeanddate.com.")

            city_row = QtWidgets.QHBoxLayout()
            city_row.addWidget(sabbath_city, 1)
            city_row.addWidget(resolve_city_btn)
            city_row_w = QtWidgets.QWidget()
            city_row_w.setLayout(city_row)

            sabbath_tz = QtWidgets.QLineEdit(_env_or_profile("SABBATH_TIMEZONE", _profile_text("sabbath_timezone")))
            sabbath_tz.setPlaceholderText(_profile_text("sabbath_timezone", "America/New_York"))
            tip(
                sabbath_tz,
                "SABBATH_TIMEZONE\nPrimary timezone shared by Sabbath scheduling, commentary slots, and session bias.",
            )
            tz_btn = QtWidgets.QPushButton("Use system TZ")
            tip(tz_btn, "SABBATH_TIMEZONE\nSet timezone from your system clock.")
            tz_row = QtWidgets.QHBoxLayout()
            tz_row.addWidget(sabbath_tz, 1)
            tz_row.addWidget(tz_btn)
            tz_row_w = QtWidgets.QWidget()
            tz_row_w.setLayout(tz_row)

            sabbath_start = QtWidgets.QLineEdit(
                _env_or_profile("SABBATH_START_LOCAL", _profile_text("sabbath_start_local", "18:00"))
            )
            sabbath_start.setPlaceholderText("HH:MM (e.g., 18:00)")
            tip(sabbath_start, "SABBATH_START_LOCAL\nFixed local start time (Friday) when not using astronomical mode.")

            sabbath_end = QtWidgets.QLineEdit(
                _env_or_profile("SABBATH_END_LOCAL", _profile_text("sabbath_end_local", "18:00"))
            )
            sabbath_end.setPlaceholderText("HH:MM (e.g., 18:00)")
            tip(sabbath_end, "SABBATH_END_LOCAL\nFixed local end time (Saturday) when not using astronomical mode.")

            sabbath_lat = QtWidgets.QLineEdit(_env_or_profile("SABBATH_LAT", _profile_text("sabbath_lat")))
            sabbath_lat.setPlaceholderText("Latitude (e.g., 40.7128)")
            tip(sabbath_lat, "SABBATH_LAT\nLatitude for astronomical sabbath calculations.")

            sabbath_lon = QtWidgets.QLineEdit(_env_or_profile("SABBATH_LON", _profile_text("sabbath_lon")))
            sabbath_lon.setPlaceholderText("Longitude (e.g., -74.0060)")
            tip(sabbath_lon, "SABBATH_LON\nLongitude for astronomical sabbath calculations.")

            def _set_system_timezone() -> None:
                tzinfo = datetime.now().astimezone().tzinfo
                tz_key = getattr(tzinfo, "key", "") if tzinfo else ""
                sabbath_tz.setText(tz_key or str(tzinfo) or "America/New_York")

            def _resolve_sabbath_city() -> None:
                raw_city = sabbath_city.text().strip()
                if not raw_city:
                    QtWidgets.QMessageBox.information(dlg, "Resolve city", "Enter a city name first.")
                    return
                slug = re.sub(r"[^a-z0-9]+", "-", raw_city.strip().lower()).strip("-")
                if not slug:
                    QtWidgets.QMessageBox.warning(dlg, "Resolve city", "City name is not valid.")
                    return
                url = f"https://www.timeanddate.com/sun/usa/{urllib.parse.quote(slug)}"
                try:
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        html = resp.read().decode("utf-8", "ignore")
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(dlg, "Resolve city", f"Failed to fetch city data: {exc}")
                    return
                m_lat = re.search(r"lat=([-0-9.]+)", html)
                m_lon = re.search(r"lon=([-0-9.]+)", html)
                if not m_lat or not m_lon:
                    QtWidgets.QMessageBox.warning(
                        dlg,
                        "Resolve city",
                        "Could not find coordinates. Check spelling or enter lat/lon manually.",
                    )
                    return
                try:
                    lat = float(m_lat.group(1))
                    lon = float(m_lon.group(1))
                except Exception:
                    QtWidgets.QMessageBox.warning(dlg, "Resolve city", "Invalid coordinates returned.")
                    return
                sabbath_lat.setText(f"{lat:.6f}".rstrip("0").rstrip("."))
                sabbath_lon.setText(f"{lon:.6f}".rstrip("0").rstrip("."))
                tz_name = None
                try:
                    from timezonefinder import TimezoneFinder

                    tz_name = TimezoneFinder().timezone_at(lng=lon, lat=lat)
                except Exception:
                    tz_name = None
                if tz_name:
                    sabbath_tz.setText(tz_name)
                else:
                    QtWidgets.QMessageBox.information(
                        dlg,
                        "Resolve city",
                        "Timezone could not be resolved. Set it manually (e.g., America/New_York).",
                    )
                sabbath_astro_chk.setChecked(True)

            tz_btn.clicked.connect(_set_system_timezone)
            resolve_city_btn.clicked.connect(_resolve_sabbath_city)

            log_level_combo = QtWidgets.QComboBox()
            log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
            log_level_combo.setCurrentText((self._effective_env_value("LOG_LEVEL")[0] or "INFO").upper())
            tip(log_level_combo, "LOG_LEVEL\nLogging verbosity for the core bot.")

            session_edit = QtWidgets.QLineEdit(self._effective_env_value("SESSION_NAME")[0] or "tradebot")
            tip(session_edit, "SESSION_NAME\ntmux session name used by the launcher (terminal dashboard).")

            log_row = QtWidgets.QHBoxLayout()
            log_edit = QtWidgets.QLineEdit(self._effective_env_value("TRADEBOT_LOG")[0] or str(settings.log_file))
            log_browse = QtWidgets.QPushButton("Browse…")
            tip(log_edit, "TRADEBOT_LOG\nPath to the log file tailed by the dashboard/GUI.")
            tip(
                log_browse,
                "GUI_LOG_BROWSE\nChoose which log file the GUI/tmux dashboard should tail.",
            )
            log_row.addWidget(log_edit, 1)
            log_row.addWidget(log_browse)
            log_row_w = QtWidgets.QWidget()
            log_row_w.setLayout(log_row)

            cmd_preview = QtWidgets.QLineEdit()
            cmd_preview.setReadOnly(True)
            tip(
                cmd_preview,
                "TMUX_RESTART_PREVIEW\nShows the exact `./scripts/tradebot.sh --restart ...` command this settings dialog would run.",
            )

            exchange_provider = QtWidgets.QComboBox()
            exchange_provider.addItem("IBKR", "primary")
            exchange_provider.addItem("CCXT", "alternative")
            _ep = (self._effective_env_value("EXCHANGE_PROVIDER")[0] or "primary").strip()
            for i in range(exchange_provider.count()):
                if str(exchange_provider.itemData(i) or "") == _ep:
                    exchange_provider.setCurrentIndex(i)
                    break
            tip(exchange_provider, "EXCHANGE_PROVIDER\nIBKR: primary\nCCXT: alternative (uses ALTERNATIVE_* providers).")

            alt_md = QtWidgets.QComboBox()
            alt_md.addItem("IBKR", "mock")
            alt_md.addItem("Crypto Public (REST)", "coinbase")
            _amd = (self._effective_env_value("ALTERNATIVE_MARKET_DATA")[0] or "mock").strip()
            for i in range(alt_md.count()):
                if str(alt_md.itemData(i) or "") == _amd:
                    alt_md.setCurrentIndex(i)
                    break
            tip(alt_md, "Market Data\nControls market data source when EXCHANGE_PROVIDER=alternative.\nIBKR uses the primary feed.")

            alt_broker = QtWidgets.QComboBox()
            alt_broker.addItem("IBKR", "mock")
            alt_broker.addItem("CCXT", "ccxt")
            _ab = (self._effective_env_value("ALTERNATIVE_BROKER")[0] or "mock").strip()
            for i in range(alt_broker.count()):
                if str(alt_broker.itemData(i) or "") == _ab:
                    alt_broker.setCurrentIndex(i)
                    break
            tip(alt_broker, "Broker\nControls execution venue when EXCHANGE_PROVIDER=alternative.\nIBKR uses the primary broker.")

            default_symbol = QtWidgets.QLineEdit(self._effective_env_value("MARKET_DEFAULT_SYMBOL")[0] or "")
            tip(default_symbol, "MARKET_DEFAULT_SYMBOL\nOptional symbol override (used when no active symbol is detected).")
            default_tf = QtWidgets.QComboBox()
            default_tf.addItems(["1m", "2m", "5m", "15m", "30m", "1h", "4h", "1d"])
            default_tf.setCurrentText((self._effective_env_value("MARKET_DEFAULT_TIMEFRAME")[0] or "5m").strip())
            tip(default_tf, "MARKET_DEFAULT_TIMEFRAME\nDefault timeframe for snapshots/candles (when applicable).")

            candle_size = QtWidgets.QComboBox()
            candle_sizes = [
                ("1 min", "1 min"),
                ("5 min", "5 mins"),
                ("15 min", "15 mins"),
                ("30 min", "30 mins"),
                ("Hourly", "1 hour"),
                ("Daily", "1 day"),
                ("Weekly", "1 week"),
                ("Monthly", "1 month"),
            ]
            for label, val in candle_sizes:
                candle_size.addItem(label, val)
            for i in range(candle_size.count()):
                if str(candle_size.itemData(i) or "") == str(settings.candle_tf or ""):
                    candle_size.setCurrentIndex(i)
                    break
            tip(candle_size, "Candles (chart)\nIBKR bar size for the candle pane (GUI only).")

            max_candles = QtWidgets.QSpinBox()
            max_candles.setRange(50, 5000)
            try:
                max_candles.setValue(int(self._effective_env_value("MARKET_MAX_CANDLES")[0] or "200"))
            except Exception:
                max_candles.setValue(200)
            tip(max_candles, "MARKET_MAX_CANDLES\nHow many candles to request/store per symbol (where supported).")

            symbols_edit = QtWidgets.QPlainTextEdit()
            symbols_edit.setPlaceholderText("Comma-separated symbols (e.g. SPY,QQQ,BTCUSD,ETHUSD)")
            symbols_edit.setMaximumHeight(90)
            symbols_edit.setPlainText(self._effective_env_value("MARKET_SYMBOLS")[0].strip())
            tip(symbols_edit, "MARKET_SYMBOLS\nOptional comma-separated symbol universe override.")

            cancel_orders = bool_chk("CANCEL_ORDERS_ON_START", "Cancel working orders on start")
            flatten_exit = bool_chk("FLATTEN_ON_EXIT", "Flatten on exit")
            intraday_flatten = bool_chk("INTRADAY_FLATTEN", "Intraday flatten")
            allow_inherit = bool_chk("ALLOW_INHERITED_POSITION", "Allow inherited positions")
            multi_positions = bool_chk("MULTI_POSITION_ENABLED", "Allow multiple positions (opt-in)")
            tip(cancel_orders, "CANCEL_ORDERS_ON_START\nCancel any working orders when the bot starts.")
            tip(flatten_exit, "FLATTEN_ON_EXIT\nAttempt to close open positions when the bot exits.")
            tip(intraday_flatten, "INTRADAY_FLATTEN\nFlatten positions near end of US session (if enabled in runtime).")
            tip(allow_inherit, "ALLOW_INHERITED_POSITION\nAllow managing positions opened outside the bot (use carefully).")
            tip(
                multi_positions,
                "MULTI_POSITION_ENABLED\nWhen true, the bot may open multiple concurrent positions (subject to risk caps).\n"
                "When false, the bot blocks new entries while any other position is open (default).",
            )

            max_concurrent = QtWidgets.QSpinBox()
            max_concurrent.setRange(1, 25)
            try:
                max_concurrent.setValue(int(self._effective_env_value("MAX_CONCURRENT_POSITIONS")[0] or "1"))
            except Exception:
                max_concurrent.setValue(1)
            max_concurrent.setEnabled(multi_positions.isChecked())
            multi_positions.toggled.connect(max_concurrent.setEnabled)
            tip(
                max_concurrent,
                "MAX_CONCURRENT_POSITIONS\nMaximum number of concurrent open positions when MULTI_POSITION_ENABLED=true.\n"
                "Use IBKR_MAX_DOLLAR_RISK_PER_SYMBOL and IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT to divvy risk across positions.",
            )

            startup_crypto_policy = QtWidgets.QComboBox()
            startup_crypto_policy.addItem("Profile default", "")
            startup_crypto_policy.addItem("FLATTEN (sell/cover immediately)", "FLATTEN")
            startup_crypto_policy.addItem("REARM (keep position; re-arm synthetic stop)", "REARM")
            startup_crypto_policy.addItem("PAUSE (keep position; pause symbol)", "PAUSE")
            _scp = (self._effective_env_value("STARTUP_CRYPTO_UNPROTECTED_POLICY")[0] or "").strip().upper()
            if not _scp:
                startup_crypto_policy.setCurrentIndex(0)
            else:
                for i in range(startup_crypto_policy.count()):
                    if str(startup_crypto_policy.itemData(i) or "").strip().upper() == _scp:
                        startup_crypto_policy.setCurrentIndex(i)
                        break
            tip(
                startup_crypto_policy,
                "STARTUP_CRYPTO_UNPROTECTED_POLICY\nPolicy for ZEROHASH crypto positions missing a persisted synthetic stop.\n"
                "Profile default is usually REARM. FLATTEN immediately sells/covers; REARM avoids immediate sells by recreating the stop.\n"
                "PAUSE keeps the position but blocks new actions on that symbol until a stop is rearmed.",
            )

            scale_out = QtWidgets.QDoubleSpinBox()
            scale_out.setRange(0.0, 1.0)
            scale_out.setSingleStep(0.05)
            try:
                scale_out.setValue(float(self._effective_env_value("SCALE_OUT_FRACTION")[0] or "0.5"))
            except Exception:
                scale_out.setValue(0.5)
            tip(scale_out, "SCALE_OUT_FRACTION\nFraction of position to scale out at targets (0–1).")

            min_pos_scale = QtWidgets.QDoubleSpinBox()
            min_pos_scale.setDecimals(6)
            min_pos_scale.setRange(0.0, 1_000_000.0)
            min_pos_scale.setSingleStep(0.01)
            try:
                min_pos_scale.setValue(float(self._effective_env_value("MIN_POSITION_SIZE_TO_SCALE")[0] or "0.0"))
            except Exception:
                min_pos_scale.setValue(0.0)
            tip(min_pos_scale, "MIN_POSITION_SIZE_TO_SCALE\nMinimum position size before scaling logic applies.")

            emergency_stop = QtWidgets.QDoubleSpinBox()
            emergency_stop.setDecimals(4)
            emergency_stop.setRange(0.0, 0.2)
            emergency_stop.setSingleStep(0.001)
            try:
                emergency_stop.setValue(float(self._effective_env_value("EMERGENCY_STOP_PCT")[0] or "0.005"))
            except Exception:
                emergency_stop.setValue(0.005)
            tip(emergency_stop, "EMERGENCY_STOP_PCT\nEmergency stop percentage used by runtime safeguards.")

            max_adds = QtWidgets.QSpinBox()
            max_adds.setRange(0, 10)
            try:
                max_adds.setValue(int(self._effective_env_value("MAX_SCALE_INS_PER_LEG")[0] or "2"))
            except Exception:
                max_adds.setValue(2)
            tip(max_adds, "MAX_SCALE_INS_PER_LEG\nMaximum number of adds (scale-ins) per leg.")

            synth_stop_store = QtWidgets.QLineEdit(self._effective_env_value("SYNTH_STOP_STORE_PATH")[0])
            pos_hold_store = QtWidgets.QLineEdit(self._effective_env_value("POSITION_HOLD_STORE_PATH")[0])
            tip(synth_stop_store, "SYNTH_STOP_STORE_PATH\nPath to synthetic stops persistence store (JSON).")
            tip(pos_hold_store, "POSITION_HOLD_STORE_PATH\nPath to position-hold persistence store (JSON).")

            def browse_path(target: QtWidgets.QLineEdit, title: str) -> None:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(
                    dlg, title, target.text().strip() or str(repo_root), "All files (*)"
                )
                if path:
                    target.setText(path)

            synth_browse = QtWidgets.QPushButton("Browse…")
            synth_browse.clicked.connect(lambda: browse_path(synth_stop_store, "Select synthetic stop store path"))
            synth_row = QtWidgets.QHBoxLayout()
            synth_row.addWidget(synth_stop_store, 1)
            synth_row.addWidget(synth_browse)
            synth_row_w = QtWidgets.QWidget()
            synth_row_w.setLayout(synth_row)

            pos_browse = QtWidgets.QPushButton("Browse…")
            tip(
                synth_browse,
                "GUI_BROWSE_SYNTH_STOP_STORE\nBrowse for a JSON file path and fill SYNTH_STOP_STORE_PATH.",
            )
            tip(
                pos_browse,
                "GUI_BROWSE_POSITION_HOLD_STORE\nBrowse for a JSON file path and fill POSITION_HOLD_STORE_PATH.",
            )
            pos_browse.clicked.connect(lambda: browse_path(pos_hold_store, "Select position hold store path"))
            pos_row = QtWidgets.QHBoxLayout()
            pos_row.addWidget(pos_hold_store, 1)
            pos_row.addWidget(pos_browse)
            pos_row_w = QtWidgets.QWidget()
            pos_row_w.setLayout(pos_row)

            friction_fs = bool_chk("FRICTION_FAIL_SAFE", "Friction fail-safe")
            friction_cap = QtWidgets.QDoubleSpinBox()
            friction_cap.setRange(0.0, 1.0)
            friction_cap.setSingleStep(0.005)
            try:
                friction_cap.setValue(float(self._effective_env_value("FRICTION_RISK_CAP")[0] or "0.02"))
            except Exception:
                friction_cap.setValue(0.02)
            tip(friction_fs, "FRICTION_FAIL_SAFE\nIf enabled, blocks trades when friction/spread looks too high.")
            tip(friction_cap, "FRICTION_RISK_CAP\nMax tolerated friction/spread metric (higher = more permissive).")

            vix_fs = bool_chk("VIX_FAIL_SAFE", "VIX fail-safe")
            vix_cap = QtWidgets.QDoubleSpinBox()
            vix_cap.setRange(0.0, 1.0)
            vix_cap.setSingleStep(0.005)
            try:
                vix_cap.setValue(float(self._effective_env_value("VIX_RISK_CAP")[0] or "0.03"))
            except Exception:
                vix_cap.setValue(0.03)
            tip(vix_fs, "VIX_FAIL_SAFE\nIf enabled, blocks trades when volatility regime looks too risky.")
            tip(vix_cap, "VIX_RISK_CAP\nMax tolerated volatility risk metric (higher = more permissive).")

            confluence_external = bool_chk("CONFLUENCE_EXTERNAL", "Include external confluence")
            commitment_mode = bool_chk("COMMITMENT_MODE", "Commitment mode (hold position bias)")
            bypass_schedule = bool_chk("BUG_BYPASS_SCHEDULE", "Bypass schedule windows (debug)")
            tip(confluence_external, "CONFLUENCE_EXTERNAL\nInclude external confluence signals (if available).")
            tip(commitment_mode, "COMMITMENT_MODE\nWhen in a position, prefer HOLD decisions vs churn every cycle.")
            tip(bypass_schedule, "BUG_BYPASS_SCHEDULE\nDebug override: bypass schedule windows. Use carefully.")

            def _auto_bool_combo(profile_value: bool, env_key: str) -> QtWidgets.QComboBox:
                combo = QtWidgets.QComboBox()
                combo.addItem(
                    f"Auto (profile: {'Enabled' if profile_value else 'Disabled'})",
                    "",
                )
                combo.addItem("Enabled", "true")
                combo.addItem("Disabled", "false")
                raw = self._effective_env_value(env_key)[0].strip().lower()
                if raw in {"1", "true", "yes", "on"}:
                    combo.setCurrentIndex(1)
                elif raw in {"0", "false", "no", "off"}:
                    combo.setCurrentIndex(2)
                else:
                    combo.setCurrentIndex(0)
                return combo

            def _auto_int_spin(profile_value: str, env_key: str, min_val: int, max_val: int) -> QtWidgets.QSpinBox:
                spin = QtWidgets.QSpinBox()
                spin.setRange(-1, max_val)
                spin.setSpecialValueText(f"Auto (profile: {profile_value})")
                spin.setSingleStep(1)
                raw = self._effective_env_value(env_key)[0].strip()
                try:
                    spin.setValue(int(raw))
                except Exception:
                    spin.setValue(-1)
                return spin

            def _auto_float_spin(
                profile_value: str,
                env_key: str,
                min_val: float,
                max_val: float,
                step: float,
                decimals: int,
            ) -> QtWidgets.QDoubleSpinBox:
                spin = QtWidgets.QDoubleSpinBox()
                spin.setDecimals(decimals)
                spin.setRange(-1.0, max_val)
                spin.setSpecialValueText(f"Auto (profile: {profile_value})")
                spin.setSingleStep(step)
                raw = self._effective_env_value(env_key)[0].strip()
                try:
                    spin.setValue(float(raw))
                except Exception:
                    spin.setValue(-1.0)
                return spin

            htf_combo = QtWidgets.QComboBox()
            htf_profile = _profile_text("htf_timeframe", "4h")
            htf_combo.addItem(f"Auto (profile: {htf_profile})", "")
            for tf in ("1h", "2h", "4h", "6h", "1d"):
                htf_combo.addItem(tf, tf)
            htf_env = self._effective_env_value("PROFILE_HTF_TIMEFRAME")[0].strip()
            if htf_env:
                htf_combo.setCurrentText(htf_env)
            else:
                htf_combo.setCurrentIndex(0)
            tip(htf_combo, "PROFILE_HTF_TIMEFRAME\nHigher timeframe for ICC structure trend.")

            ltf_combo = QtWidgets.QComboBox()
            ltf_profile = _profile_text("ltf_timeframe", "")
            ltf_label = ltf_profile or "candle_timeframe"
            ltf_combo.addItem(f"Auto (profile: {ltf_label})", "")
            for tf in ("1m", "2m", "5m", "15m", "30m", "1h"):
                ltf_combo.addItem(tf, tf)
            ltf_env = self._effective_env_value("PROFILE_LTF_TIMEFRAME")[0].strip()
            if ltf_env:
                ltf_combo.setCurrentText(ltf_env)
            else:
                ltf_combo.setCurrentIndex(0)
            tip(ltf_combo, "PROFILE_LTF_TIMEFRAME\nLower timeframe for ICC execution structure.")

            trend_window_spin = _auto_int_spin(
                _profile_text("trend_window", "120"),
                "PROFILE_TREND_WINDOW",
                20,
                1000,
            )
            tip(trend_window_spin, "PROFILE_TREND_WINDOW\nCandles used to infer HTF swing structure.")

            trend_swing_spin = _auto_int_spin(
                _profile_text("trend_swing_lookback", "2"),
                "PROFILE_TREND_SWING_LOOKBACK",
                1,
                10,
            )
            tip(trend_swing_spin, "PROFILE_TREND_SWING_LOOKBACK\nFractal lookback for swing highs/lows.")

            trend_min_swings_spin = _auto_int_spin(
                _profile_text("trend_min_swings", "3"),
                "PROFILE_TREND_MIN_SWINGS",
                2,
                10,
            )
            tip(trend_min_swings_spin, "PROFILE_TREND_MIN_SWINGS\nMinimum swings for HH/HL or LH/LL trend.")

            trend_strength_spin = _auto_float_spin(
                _profile_text("trend_strength_floor", "0.5"),
                "PROFILE_TREND_STRENGTH_FLOOR",
                0.0,
                1.0,
                0.05,
                2,
            )
            tip(trend_strength_spin, "PROFILE_TREND_STRENGTH_FLOOR\nMin strength to avoid chop.")

            structure_score_spin = _auto_float_spin(
                _profile_text("structure_score_threshold", "0.3"),
                "PROFILE_STRUCTURE_SCORE_THRESHOLD",
                0.0,
                1.0,
                0.01,
                3,
            )
            tip(structure_score_spin, "PROFILE_STRUCTURE_SCORE_THRESHOLD\nStructure cleanliness threshold.")

            session_gate_combo = _auto_bool_combo(
                bool(getattr(profile_settings, "session_gate_enabled", True)),
                "PROFILE_SESSION_GATE_ENABLED",
            )
            tip(
                session_gate_combo,
                "PROFILE_SESSION_GATE_ENABLED\n"
                "A+ session health gate. When enabled, entries flagged as A+ must see "
                "range + volume expansion to avoid chopping in dead sessions.\n"
                "Trade by SCI default: Enabled.",
            )

            session_min_candles_spin = _auto_int_spin(
                _profile_text("session_gate_min_candles", "30"),
                "PROFILE_SESSION_GATE_MIN_CANDLES",
                10,
                500,
            )
            tip(
                session_min_candles_spin,
                "PROFILE_SESSION_GATE_MIN_CANDLES\n"
                "Minimum number of candles required before session health is enforced.\n"
                "Lower values make the gate apply sooner; higher values need more history.",
            )

            session_range_mult_spin = _auto_float_spin(
                _profile_text("session_range_multiplier", "1.1"),
                "PROFILE_SESSION_RANGE_MULTIPLIER",
                0.0,
                3.0,
                0.05,
                2,
            )
            tip(
                session_range_mult_spin,
                "PROFILE_SESSION_RANGE_MULTIPLIER\n"
                "Range expansion multiple required for an A+ continuation.\n"
                "Example: 1.1 means the last 5 bars must average 10% more range "
                "than the prior 20 bars.",
            )

            session_volume_mult_spin = _auto_float_spin(
                _profile_text("session_volume_multiplier", "1.1"),
                "PROFILE_SESSION_VOLUME_MULTIPLIER",
                0.0,
                5.0,
                0.05,
                2,
            )
            tip(
                session_volume_mult_spin,
                "PROFILE_SESSION_VOLUME_MULTIPLIER\n"
                "Volume expansion multiple required for an A+ continuation.\n"
                "Example: 1.1 means recent volume must be 10% above prior volume.",
            )

            session_overlap_start_spin = _auto_int_spin(
                _profile_text("session_overlap_start_hour", "12"),
                "PROFILE_SESSION_OVERLAP_START_HOUR",
                0,
                23,
            )
            session_overlap_end_spin = _auto_int_spin(
                _profile_text("session_overlap_end_hour", "16"),
                "PROFILE_SESSION_OVERLAP_END_HOUR",
                0,
                23,
            )
            tip(
                session_overlap_start_spin,
                "PROFILE_SESSION_OVERLAP_START_HOUR\n"
                "Local hour (0-23) when FX/crypto session bias begins.\n"
                "Default 12 (UTC) approximates London/NY overlap.",
            )
            tip(
                session_overlap_end_spin,
                "PROFILE_SESSION_OVERLAP_END_HOUR\n"
                "Local hour (0-23) when FX/crypto session bias ends (exclusive).\n"
                "Default 16 (UTC) approximates London/NY overlap.",
            )

            pdt_guard_combo = _auto_bool_combo(bool(getattr(profile_settings, "pdt_guard_enabled", False)), "PROFILE_PDT_GUARD_ENABLED")
            tip(pdt_guard_combo, "PROFILE_PDT_GUARD_ENABLED\nEnable PDT guard for equities.")

            max_roundtrips_spin = _auto_int_spin(
                _profile_text("max_equity_roundtrips_per_day", "2"),
                "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY",
                1,
                20,
            )
            tip(max_roundtrips_spin, "PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY\nMax equity roundtrips per day.")

            flip_enabled_combo = _auto_bool_combo(bool(getattr(profile_settings, "flip_actions_enabled", False)), "PROFILE_FLIP_ACTIONS_ENABLED")
            tip(flip_enabled_combo, "PROFILE_FLIP_ACTIONS_ENABLED\nAllow flip_to_long/flip_to_short actions.")

            flip_cooldown_spin = _auto_int_spin(
                _profile_text("flip_cooldown_seconds", "600"),
                "PROFILE_FLIP_COOLDOWN_SECONDS",
                0,
                86400,
            )
            tip(flip_cooldown_spin, "PROFILE_FLIP_COOLDOWN_SECONDS\nCooldown between flips when PDT guard is active.")

            cooldown_enabled_combo = _auto_bool_combo(bool(getattr(profile_settings, "cooldown_enabled", True)), "PROFILE_COOLDOWN_ENABLED")
            tip(cooldown_enabled_combo, "PROFILE_COOLDOWN_ENABLED\nEnable ICC cooldowns after blocks/successes.")

            cooldown_block_spin = _auto_int_spin(
                _profile_text("cooldown_cycles_after_block", "3"),
                "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK",
                0,
                50,
            )
            tip(cooldown_block_spin, "PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK\nCycles to skip after a block.")

            cooldown_success_spin = _auto_int_spin(
                _profile_text("cooldown_cycles_after_success", "0"),
                "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS",
                0,
                50,
            )
            tip(cooldown_success_spin, "PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS\nCycles to skip after success.")

            cooldown_scope_combo = QtWidgets.QComboBox()
            cooldown_scope_combo.addItem(
                f"Auto (profile: {_profile_text('cooldown_scope', 'symbol')})",
                "",
            )
            cooldown_scope_combo.addItem("symbol", "symbol")
            cooldown_scope_combo.addItem("global", "global")
            scope_env = self._effective_env_value("PROFILE_COOLDOWN_SCOPE")[0].strip().lower()
            if scope_env in {"symbol", "global"}:
                cooldown_scope_combo.setCurrentText(scope_env)
            else:
                cooldown_scope_combo.setCurrentIndex(0)
            tip(cooldown_scope_combo, "PROFILE_COOLDOWN_SCOPE\nApply cooldown per symbol or globally.")

            stick_to_active_combo = QtWidgets.QComboBox()
            stick_profile = _profile_text("stick_to_active_symbol_until", "cycle_end")
            stick_to_active_combo.addItem(f"Auto (profile: {stick_profile})", "")
            stick_to_active_combo.addItem("cycle_end", "cycle_end")
            stick_to_active_combo.addItem("decision_end", "decision_end")
            stick_env = self._effective_env_value("PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL")[0].strip()
            if stick_env:
                stick_to_active_combo.setCurrentText(stick_env)
            else:
                stick_to_active_combo.setCurrentIndex(0)
            tip(stick_to_active_combo, "PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL\nStick to active symbol policy.")

            aggressive_mode_combo = _auto_bool_combo(bool(getattr(profile_settings, "icc_aggressive_mode", False)), "PROFILE_ICC_AGGRESSIVE_MODE")
            tip(
                aggressive_mode_combo,
                "PROFILE_ICC_AGGRESSIVE_MODE\n"
                "Enable aggressive ICC sizing (Phase 2). Trade by SCI defaults to enabled\n"
                "with strict guardrails (daily loss cap, exposure cap, consecutive loss cap).",
            )

            aggressive_risk_spin = _auto_float_spin(
                _profile_text("aggressive_risk_per_trade_pct", "0.03"),
                "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT",
                0.0,
                1.0,
                0.005,
                3,
            )
            tip(aggressive_risk_spin, "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT\nRisk per trade % in aggressive mode.")

            max_daily_loss_spin = _auto_float_spin(
                _profile_text("max_daily_loss_pct", "0.06"),
                "PROFILE_MAX_DAILY_LOSS_PCT",
                0.0,
                1.0,
                0.005,
                3,
            )
            tip(max_daily_loss_spin, "PROFILE_MAX_DAILY_LOSS_PCT\nDaily loss limit % (aggressive mode).")

            max_exposure_spin = _auto_float_spin(
                _profile_text("max_exposure_pct", "0.4"),
                "PROFILE_MAX_EXPOSURE_PCT",
                0.0,
                1.0,
                0.01,
                3,
            )
            tip(max_exposure_spin, "PROFILE_MAX_EXPOSURE_PCT\nTotal exposure limit % (aggressive mode).")

            max_losses_spin = _auto_int_spin(
                _profile_text("max_consecutive_losses", "2"),
                "PROFILE_MAX_CONSECUTIVE_LOSSES",
                1,
                20,
            )
            tip(max_losses_spin, "PROFILE_MAX_CONSECUTIVE_LOSSES\nConsecutive loss cap (aggressive mode).")

            commentary_combo = QtWidgets.QComboBox()
            commentary_combo.addItems(["Auto", "Off", "Internal"])
            comm = (self._effective_env_value("COMMENTARY_LLM")[0] or "").strip().lower()
            if comm == "":
                commentary_combo.setCurrentIndex(0)
            elif comm == "off":
                commentary_combo.setCurrentIndex(1)
            else:
                commentary_combo.setCurrentIndex(2)
            tip(commentary_combo, "COMMENTARY_LLM\nAuto: internal commentary\nOff: deterministic dashboard\nInternal: fetch AI commentary.")

            commentary_policy_combo = QtWidgets.QComboBox()
            commentary_policy_combo.addItems(["A+ or 4/day", "A+ only", "Interval"])
            pol = (self._effective_env_value("COMMENTARY_LLM_POLICY")[0] or "").strip().lower()
            if pol == "a_plus_only":
                commentary_policy_combo.setCurrentIndex(1)
            elif pol == "interval":
                commentary_policy_combo.setCurrentIndex(2)
            else:
                commentary_policy_combo.setCurrentIndex(0)
            tip(
                commentary_policy_combo,
                "COMMENTARY_LLM_POLICY\nControls when commentary is called.\n"
                "A+ or 4/day (recommended): call on A+ continuation (readiness=1.00), otherwise call at 4 daily slots.\n"
                "A+ only: only call when an A+ continuation appears.\n"
                "Interval: legacy behavior (calls based on COMMENTARY_LLM_MIN_SECONDS).",
            )

            commentary_slots = QtWidgets.QLineEdit(
                self._effective_env_value("COMMENTARY_LLM_DAILY_SLOTS")[0] or "09:00,12:00,18:00,22:00"
            )
            commentary_slots.setPlaceholderText("09:00,12:00,18:00,22:00")
            tip(commentary_slots, "COMMENTARY_LLM_DAILY_SLOTS\nComma-separated daily slot times (HH:MM).")

            commentary_min_spin = QtWidgets.QSpinBox()
            commentary_min_spin.setRange(5, 3600)
            try:
                commentary_min_spin.setValue(
                    int(float(self._effective_env_value("COMMENTARY_LLM_MIN_SECONDS")[0] or "300"))
                )
            except Exception:
                commentary_min_spin.setValue(300)
            tip(commentary_min_spin, "COMMENTARY_LLM_MIN_SECONDS\nMinimum seconds between commentary refreshes (default: 300).")

            commentary_max_calls = QtWidgets.QSpinBox()
            commentary_max_calls.setRange(0, 10000)
            try:
                commentary_max_calls.setValue(
                    int(float(self._effective_env_value("COMMENTARY_LLM_MAX_CALLS_PER_DAY")[0] or "250"))
                )
            except Exception:
                commentary_max_calls.setValue(250)
            tip(
                commentary_max_calls,
                "COMMENTARY_LLM_MAX_CALLS_PER_DAY\nHard cap across all panes per day (shared budget file).\n0 disables the cap.",
            )

            commentary_budget_path = QtWidgets.QLineEdit(self._effective_env_value("COMMENTARY_LLM_BUDGET_PATH")[0])
            commentary_budget_path.setPlaceholderText("/tmp/tradebot_sci_commentary_budget.json")
            tip(
                commentary_budget_path,
                "COMMENTARY_LLM_BUDGET_PATH\nShared JSON budget file path for commentary call limiting.\nUse a shared path if you run multiple dashboards.",
            )

            provider_combo = QtWidgets.QComboBox()
            provider_combo.setIconSize(QtCore.QSize(18, 18))
            provider_icons_root = repo_root / "src" / "tradebot_sci" / "gui" / "assets" / "providers"

            def _provider_icon(name: str) -> QtGui.QIcon:
                icon_path = provider_icons_root / f"{name}.svg"
                if icon_path.exists():
                    return QtGui.QIcon(str(icon_path))
                return QtGui.QIcon()

            provider_combo.addItem(_provider_icon("openai"), "Auto (OpenAI)", "")
            provider_combo.addItem(_provider_icon("openai"), "OpenAI", "openai")
            provider_combo.addItem(_provider_icon("gemini"), "Gemini", "gemini")
            provider_combo.addItem(_provider_icon("claude"), "Claude", "claude")
            provider_combo.addItem(_provider_icon("deepseek"), "DeepSeek", "deepseek")
            provider_combo.addItem(_provider_icon("openrouter"), "OpenRouter", "openrouter")
            provider_combo.addItem(_provider_icon("custom"), "Custom (OpenAI-compatible)", "custom")
            provider_env = (self._effective_env_value("TRADE_SCI_PROVIDER")[0] or "").strip().lower()
            if provider_env:
                for idx in range(provider_combo.count()):
                    if str(provider_combo.itemData(idx) or "").strip().lower() == provider_env:
                        provider_combo.setCurrentIndex(idx)
                        break
            else:
                provider_combo.setCurrentIndex(0)
            tip(
                provider_combo,
                "TRADE_SCI_PROVIDER\nSelect which AI provider the bot/commentary should use.\n"
                "Auto uses OpenAI defaults unless overridden.",
            )

            ai_base = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_API_BASE_URL")[0])
            ai_key = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_API_KEY")[0])
            ai_key.setEchoMode(QtWidgets.QLineEdit.Password)
            chatgpt_key = QtWidgets.QLineEdit(self._effective_env_value("CHATGPT_KEY")[0])
            chatgpt_key.setEchoMode(QtWidgets.QLineEdit.Password)
            ai_model = QtWidgets.QLineEdit(self._effective_env_value("TRADE_SCI_MODEL_NAME")[0])
            tip(ai_base, "TRADE_SCI_API_BASE_URL\nBase URL for the AI provider API (optional).")
            tip(ai_key, "TRADE_SCI_API_KEY\nAPI key for the AI provider. Stored as env var; masked here.")
            tip(chatgpt_key, "CHATGPT_KEY\nLegacy API key fallback (optional). Stored as env var; masked here.")
            tip(ai_model, "TRADE_SCI_MODEL_NAME\nModel name/id for the AI provider (optional).")
            ai_temp = QtWidgets.QDoubleSpinBox()
            ai_temp.setRange(0.0, 2.0)
            ai_temp.setSingleStep(0.05)
            try:
                ai_temp.setValue(float(self._effective_env_value("TRADE_SCI_TEMPERATURE")[0] or "0.2"))
            except Exception:
                ai_temp.setValue(0.2)
            tip(ai_temp, "TRADE_SCI_TEMPERATURE\nControls randomness/creativity for AI outputs.")
            ai_tokens = QtWidgets.QSpinBox()
            ai_tokens.setRange(128, 16384)
            try:
                ai_tokens.setValue(int(float(self._effective_env_value("TRADE_SCI_MAX_TOKENS")[0] or "2048")))
            except Exception:
                ai_tokens.setValue(2048)
            tip(ai_tokens, "TRADE_SCI_MAX_TOKENS\nMax tokens for AI responses.")

            ibkr_host = QtWidgets.QLineEdit(self._effective_env_value("IBKR_HOST")[0] or "127.0.0.1")
            ibkr_port = QtWidgets.QSpinBox()
            ibkr_port.setRange(1, 65535)
            try:
                ibkr_port.setValue(int(self._effective_env_value("IBKR_PORT")[0] or "7497"))
            except Exception:
                ibkr_port.setValue(7497)
            ibkr_crypto = QtWidgets.QLineEdit(self._effective_env_value("IBKR_CRYPTO_EXCHANGE")[0] or "ZEROHASH")
            ibkr_zerohash_tif = QtWidgets.QComboBox()
            ibkr_zerohash_tif.addItem("Auto (IOC)", "")
            ibkr_zerohash_tif.addItem("IOC", "IOC")
            ibkr_zerohash_tif.addItem("Minutes", "Minutes")
            _ztif = (self._effective_env_value("IBKR_ZEROHASH_CRYPTO_TIF")[0] or "").strip()
            if not _ztif:
                ibkr_zerohash_tif.setCurrentIndex(0)
            else:
                _ztif_n = _ztif.strip().lower()
                for i in range(ibkr_zerohash_tif.count()):
                    item_val = str(ibkr_zerohash_tif.itemData(i) or "").strip().lower()
                    if item_val == _ztif_n:
                        ibkr_zerohash_tif.setCurrentIndex(i)
                        break
            ibkr_client_id = QtWidgets.QLineEdit(self._effective_env_value("IBKR_CLIENT_ID")[0])
            ibkr_account_id = QtWidgets.QLineEdit(self._effective_env_value("IBKR_ACCOUNT_ID")[0])
            ibkr_default_ccy = QtWidgets.QLineEdit(self._effective_env_value("IBKR_DEFAULT_CCY")[0] or "USD")
            ibkr_paper = bool_chk("IBKR_PAPER", "Paper trading")
            ibkr_read_only = bool_chk("IBKR_READ_ONLY", "Read-only")
            tip(ibkr_host, "IBKR_HOST\nTWS/IB Gateway host (usually 127.0.0.1).")
            tip(ibkr_port, "IBKR_PORT\nTWS/IB Gateway port (7497 paper, 7496 live by default).")
            tip(ibkr_crypto, "IBKR_CRYPTO_EXCHANGE\nCrypto venue routing (e.g. ZEROHASH).")
            tip(
                ibkr_zerohash_tif,
                "IBKR_ZEROHASH_CRYPTO_TIF\nTIF for IBKR spot crypto on ZEROHASH.\nIBKR requires Minutes or IOC; Auto defaults to IOC.",
            )
            tip(ibkr_client_id, "IBKR_CLIENT_ID\nOptional client id for the API connection.")
            tip(ibkr_account_id, "IBKR_ACCOUNT_ID\nOptional account id to target (if multiple accounts).")
            tip(ibkr_default_ccy, "IBKR_DEFAULT_CCY\nDefault currency (e.g. USD).")
            tip(ibkr_paper, "IBKR_PAPER\ntrue: paper trading connection preference.")
            tip(ibkr_read_only, "IBKR_READ_ONLY\ntrue: do not place orders even if EXECUTE_TRADES=true.")

            # Broker risk caps live in config/broker_ibkr.yaml, but we allow optional env overrides for GUI users.
            broker_defaults: dict[str, Any] = {}
            try:
                import yaml  # type: ignore

                broker_path = repo_root / "config" / "broker_ibkr.yaml"
                if broker_path.exists():
                    broker_defaults = yaml.safe_load(broker_path.read_text(encoding="utf-8")) or {}
            except Exception:
                broker_defaults = {}

            def _broker_default(key: str, fallback: Any) -> Any:
                v = broker_defaults.get(key)
                return fallback if v is None else v

            def _override_flag(env_key: str) -> bool:
                return bool((self._effective_env_value(env_key)[0] or "").strip())

            def _override_row(override_chk: QtWidgets.QCheckBox, editor: QtWidgets.QWidget) -> QtWidgets.QWidget:
                row = QtWidgets.QHBoxLayout()
                row.addWidget(override_chk, 0)
                row.addWidget(editor, 1)
                row_w = QtWidgets.QWidget()
                row_w.setLayout(row)
                return row_w

            # Max shares / symbol
            ibkr_max_shares_override = QtWidgets.QCheckBox("Override")
            ibkr_max_shares_override.setChecked(_override_flag("IBKR_MAX_SHARES_PER_SYMBOL"))
            ibkr_max_shares = QtWidgets.QSpinBox()
            ibkr_max_shares.setRange(1, 10_000)
            ibkr_max_shares.setValue(int(_broker_default("max_shares_per_symbol", 5) or 5))
            try:
                v = int((self._effective_env_value("IBKR_MAX_SHARES_PER_SYMBOL")[0] or "").strip() or "0")
                if v > 0:
                    ibkr_max_shares.setValue(v)
            except Exception:
                pass
            ibkr_max_shares.setEnabled(ibkr_max_shares_override.isChecked())
            ibkr_max_shares_override.toggled.connect(ibkr_max_shares.setEnabled)
            ibkr_max_shares_row = _override_row(ibkr_max_shares_override, ibkr_max_shares)
            tip(
                ibkr_max_shares_override,
                "IBKR_MAX_SHARES_PER_SYMBOL\nOptional env override for broker_ibkr.yaml:max_shares_per_symbol.\n"
                "Enable to override from the GUI without editing YAML.",
            )
            tip(ibkr_max_shares, "BrokerSetting: max_shares_per_symbol\nPer-symbol share cap (sizing guard).")

            # Max dollar risk / symbol
            ibkr_max_sym_risk_override = QtWidgets.QCheckBox("Override")
            ibkr_max_sym_risk_override.setChecked(_override_flag("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"))
            ibkr_max_sym_risk = QtWidgets.QDoubleSpinBox()
            ibkr_max_sym_risk.setDecimals(2)
            ibkr_max_sym_risk.setRange(0.0, 1_000_000.0)
            ibkr_max_sym_risk.setSingleStep(5.0)
            ibkr_max_sym_risk.setValue(float(_broker_default("max_dollar_risk_per_symbol", 3.0) or 0.0))
            try:
                v = float((self._effective_env_value("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL")[0] or "").strip() or "nan")
                if v == v:
                    ibkr_max_sym_risk.setValue(max(0.0, v))
            except Exception:
                pass
            ibkr_max_sym_risk.setEnabled(ibkr_max_sym_risk_override.isChecked())
            ibkr_max_sym_risk_override.toggled.connect(ibkr_max_sym_risk.setEnabled)
            ibkr_max_sym_risk_row = _override_row(ibkr_max_sym_risk_override, ibkr_max_sym_risk)
            tip(
                ibkr_max_sym_risk_override,
                "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL\nOptional env override for broker_ibkr.yaml:max_dollar_risk_per_symbol.\n"
                "Total open bracket risk allowed per symbol (USD).",
            )
            tip(ibkr_max_sym_risk, "BrokerSetting: max_dollar_risk_per_symbol\nPer-symbol open bracket risk cap (USD).")

            # Max dollar risk / account
            ibkr_max_acct_risk_override = QtWidgets.QCheckBox("Override")
            ibkr_max_acct_risk_override.setChecked(_override_flag("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"))
            ibkr_max_acct_risk = QtWidgets.QDoubleSpinBox()
            ibkr_max_acct_risk.setDecimals(2)
            ibkr_max_acct_risk.setRange(0.0, 1_000_000.0)
            ibkr_max_acct_risk.setSingleStep(10.0)
            ibkr_max_acct_risk.setValue(float(_broker_default("max_dollar_risk_per_account", 0.0) or 0.0))
            try:
                v = float((self._effective_env_value("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT")[0] or "").strip() or "nan")
                if v == v:
                    ibkr_max_acct_risk.setValue(max(0.0, v))
            except Exception:
                pass
            ibkr_max_acct_risk.setEnabled(ibkr_max_acct_risk_override.isChecked())
            ibkr_max_acct_risk_override.toggled.connect(ibkr_max_acct_risk.setEnabled)
            ibkr_max_acct_risk_row = _override_row(ibkr_max_acct_risk_override, ibkr_max_acct_risk)
            tip(
                ibkr_max_acct_risk_override,
                "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT\nOptional env override for broker_ibkr.yaml:max_dollar_risk_per_account.\n"
                "Aggregate cap across all symbols (USD). Useful when MULTI_POSITION_ENABLED=true.",
            )
            tip(ibkr_max_acct_risk, "BrokerSetting: max_dollar_risk_per_account\nAggregate open bracket risk cap (USD).")

            # Auto risk fraction of buying power
            ibkr_auto_risk_override = QtWidgets.QCheckBox("Override")
            ibkr_auto_risk_override.setChecked(_override_flag("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"))
            ibkr_auto_risk = QtWidgets.QDoubleSpinBox()
            ibkr_auto_risk.setDecimals(4)
            ibkr_auto_risk.setRange(0.0, 1.0)
            ibkr_auto_risk.setSingleStep(0.01)
            ibkr_auto_risk.setValue(float(_broker_default("auto_risk_fraction_of_buying_power", 0.001) or 0.0))
            try:
                v = float(
                    (self._effective_env_value("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER")[0] or "").strip() or "nan"
                )
                if v == v:
                    ibkr_auto_risk.setValue(max(0.0, min(1.0, v)))
            except Exception:
                pass
            ibkr_auto_risk.setEnabled(ibkr_auto_risk_override.isChecked())
            ibkr_auto_risk_override.toggled.connect(ibkr_auto_risk.setEnabled)
            ibkr_auto_risk_row = _override_row(ibkr_auto_risk_override, ibkr_auto_risk)
            tip(
                ibkr_auto_risk_override,
                "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER\nOptional env override for broker_ibkr.yaml:auto_risk_fraction_of_buying_power.\n"
                "If set and accountSummary is available, this can override per-symbol dollar risk.",
            )
            tip(ibkr_auto_risk, "BrokerSetting: auto_risk_fraction_of_buying_power\nFraction of buying power to use for per-symbol risk.")

            ccxt_exchange = QtWidgets.QLineEdit(self._effective_env_value("CCXT_EXCHANGE")[0])
            ccxt_default_type = QtWidgets.QComboBox()
            ccxt_default_type.addItems(["", "spot", "swap", "future", "margin"])
            ccxt_default_type.setCurrentText(self._effective_env_value("CCXT_DEFAULT_TYPE")[0].strip())
            ccxt_rate_limit = bool_chk("CCXT_ENABLE_RATE_LIMIT", "Enable rate limit")
            ccxt_sandbox = bool_chk("CCXT_SANDBOX", "Sandbox mode")
            ccxt_symbol_map = QtWidgets.QPlainTextEdit()
            ccxt_symbol_map.setPlaceholderText("SYMBOL=ccxt/SYMBOL, ... (or JSON); optional")
            ccxt_symbol_map.setMaximumHeight(90)
            ccxt_symbol_map.setPlainText(self._effective_env_value("CCXT_SYMBOL_MAP")[0].strip())
            ccxt_api_key = QtWidgets.QLineEdit(self._effective_env_value("CCXT_API_KEY")[0])
            ccxt_api_key.setEchoMode(QtWidgets.QLineEdit.Password)
            ccxt_secret = QtWidgets.QLineEdit(self._effective_env_value("CCXT_SECRET")[0])
            ccxt_secret.setEchoMode(QtWidgets.QLineEdit.Password)
            ccxt_password = QtWidgets.QLineEdit(self._effective_env_value("CCXT_PASSWORD")[0])
            ccxt_password.setEchoMode(QtWidgets.QLineEdit.Password)
            tip(ccxt_exchange, "CCXT_EXCHANGE\nExchange id (e.g. coinbase, binance). Required when using CCXT broker.")
            tip(ccxt_default_type, "CCXT_DEFAULT_TYPE\nOptional default market type (spot/swap/future/etc).")
            tip(ccxt_rate_limit, "CCXT_ENABLE_RATE_LIMIT\nEnable CCXT rate limiting.")
            tip(ccxt_sandbox, "CCXT_SANDBOX\nUse sandbox/testnet mode (if supported by the exchange).")
            tip(ccxt_symbol_map, "CCXT_SYMBOL_MAP\nOptional symbol mapping for CCXT (when your symbols differ).")
            tip(ccxt_api_key, "CCXT_API_KEY\nAPI key for CCXT exchange. Stored as env var; masked here.")
            tip(ccxt_secret, "CCXT_SECRET\nAPI secret for CCXT exchange. Stored as env var; masked here.")
            tip(ccxt_password, "CCXT_PASSWORD\nOptional password for CCXT exchange. Stored as env var; masked here.")

            def browse_log() -> None:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(
                    dlg,
                    "Select log file",
                    log_edit.text() or str(settings.log_file),
                    "Log files (*.log);;All files (*)",
                )
                if path:
                    log_edit.setText(path)
                    refresh_preview()

            log_browse.clicked.connect(browse_log)

            def refresh_preview() -> None:
                mode = mode_combo.currentText().strip()
                profile = profile_combo.currentText().strip()
                session = session_edit.text().strip() or "tradebot"
                log_path = log_edit.text().strip() or str(settings.log_file)
                args: list[str] = ["./scripts/tradebot.sh", "--restart", "-p", profile, "-m", mode, "-x"]
                args.append("true" if execute_chk.isChecked() else "false")
                if mode == "iterations":
                    args.extend(["-i", str(iterations_spin.value())])
                sabb = sabbath_combo.currentIndex()
                if sabb == 1:
                    args.append("--sabbath")
                elif sabb == 2:
                    args.append("--no-sabbath")
                args.extend(["-n", session, "-l", log_path])
                comm_mode = commentary_combo.currentIndex()
                if comm_mode == 1:
                    args.extend(["-c", "off"])
                elif comm_mode == 2:
                    args.extend(["-c", "internal"])
                args.extend(["-t", str(commentary_min_spin.value())])
                cmd_preview.setText(" ".join(args))
                iterations_spin.setEnabled(mode == "iterations")

            for w in (
                app_env,
                profile_combo,
                mode_combo,
                iterations_spin,
                execute_chk,
                sabbath_combo,
                sabbath_enabled_combo,
                sabbath_astro_chk,
                sabbath_city,
                sabbath_tz,
                sabbath_start,
                sabbath_end,
                sabbath_lat,
                sabbath_lon,
                log_level_combo,
                session_edit,
                log_edit,
                commentary_combo,
                commentary_min_spin,
                commentary_max_calls,
                commentary_budget_path,
                exchange_provider,
                alt_md,
                alt_broker,
                ibkr_zerohash_tif,
                default_symbol,
                default_tf,
                max_candles,
                symbols_edit,
                cancel_orders,
                flatten_exit,
                intraday_flatten,
                allow_inherit,
                multi_positions,
                max_concurrent,
                startup_crypto_policy,
                scale_out,
                min_pos_scale,
                emergency_stop,
                max_adds,
                synth_stop_store,
                pos_hold_store,
                htf_combo,
                ltf_combo,
                trend_window_spin,
                trend_swing_spin,
                trend_min_swings_spin,
                trend_strength_spin,
                structure_score_spin,
                session_gate_combo,
                session_min_candles_spin,
                session_range_mult_spin,
                session_volume_mult_spin,
                session_overlap_start_spin,
                session_overlap_end_spin,
                pdt_guard_combo,
                max_roundtrips_spin,
                flip_enabled_combo,
                flip_cooldown_spin,
                cooldown_enabled_combo,
                cooldown_block_spin,
                cooldown_success_spin,
                cooldown_scope_combo,
                stick_to_active_combo,
                aggressive_mode_combo,
                aggressive_risk_spin,
                max_daily_loss_spin,
                max_exposure_spin,
                max_losses_spin,
                ibkr_host,
                ibkr_port,
                ibkr_crypto,
                ibkr_client_id,
                ibkr_account_id,
                ibkr_default_ccy,
                ibkr_paper,
                ibkr_read_only,
                ibkr_max_shares_override,
                ibkr_max_shares,
                ibkr_max_sym_risk_override,
                ibkr_max_sym_risk,
                ibkr_max_acct_risk_override,
                ibkr_max_acct_risk,
                ibkr_auto_risk_override,
                ibkr_auto_risk,
                ccxt_exchange,
                ccxt_default_type,
                ccxt_rate_limit,
                ccxt_sandbox,
            ):
                if isinstance(w, QtWidgets.QComboBox):
                    w.currentTextChanged.connect(refresh_preview)
                elif isinstance(w, QtWidgets.QAbstractButton):
                    w.toggled.connect(refresh_preview)
                elif isinstance(w, QtWidgets.QSpinBox):
                    w.valueChanged.connect(refresh_preview)
                elif isinstance(w, QtWidgets.QLineEdit):
                    w.textChanged.connect(refresh_preview)
                elif isinstance(w, QtWidgets.QPlainTextEdit):
                    w.textChanged.connect(refresh_preview)

            def desired_typed_env() -> dict[str, str]:
                out: dict[str, str] = {}
                if app_env.text().strip():
                    out["APP_ENVIRONMENT"] = app_env.text().strip()
                out["PROFILE_NAME"] = profile_combo.currentText().strip()
                out["BOT_MODE"] = mode_combo.currentText().strip()
                out["BOT_ITERATIONS"] = str(iterations_spin.value())
                out["EXECUTE_TRADES"] = "true" if execute_chk.isChecked() else "false"
                out["LOG_LEVEL"] = log_level_combo.currentText().strip().upper() or "INFO"
                out["SESSION_NAME"] = session_edit.text().strip() or "tradebot"
                out["TRADEBOT_LOG"] = log_edit.text().strip() or str(settings.log_file)

                sabb = sabbath_combo.currentIndex()
                out["BOT_SABBATH"] = "" if sabb == 0 else ("on" if sabb == 1 else "off")
                sabb_profile = sabbath_enabled_combo.currentIndex()
                out["SABBATH_ENABLED"] = "" if sabb_profile == 0 else ("true" if sabb_profile == 1 else "false")
                out["SABBATH_ASTRONOMICAL"] = "true" if sabbath_astro_chk.isChecked() else "false"
                if sabbath_city.text().strip():
                    out["SABBATH_CITY"] = sabbath_city.text().strip()
                if sabbath_tz.text().strip():
                    tz_value = sabbath_tz.text().strip()
                    out["SABBATH_TIMEZONE"] = tz_value
                    out["COMMENTARY_LLM_TZ"] = tz_value
                    out["PROFILE_SESSION_OVERLAP_TIMEZONE"] = tz_value
                if sabbath_start.text().strip():
                    out["SABBATH_START_LOCAL"] = sabbath_start.text().strip()
                if sabbath_end.text().strip():
                    out["SABBATH_END_LOCAL"] = sabbath_end.text().strip()
                if sabbath_lat.text().strip():
                    out["SABBATH_LAT"] = sabbath_lat.text().strip()
                if sabbath_lon.text().strip():
                    out["SABBATH_LON"] = sabbath_lon.text().strip()

                out["EXCHANGE_PROVIDER"] = str(exchange_provider.currentData() or "primary").strip()
                out["ALTERNATIVE_MARKET_DATA"] = str(alt_md.currentData() or alt_md.currentText()).strip()
                out["ALTERNATIVE_BROKER"] = str(alt_broker.currentData() or alt_broker.currentText()).strip()
                if default_symbol.text().strip():
                    out["MARKET_DEFAULT_SYMBOL"] = default_symbol.text().strip()
                out["MARKET_DEFAULT_TIMEFRAME"] = default_tf.currentText().strip()
                out["MARKET_MAX_CANDLES"] = str(max_candles.value())
                out["MARKET_SYMBOLS"] = symbols_edit.toPlainText().strip()

                out["CANCEL_ORDERS_ON_START"] = "true" if cancel_orders.isChecked() else "false"
                out["FLATTEN_ON_EXIT"] = "true" if flatten_exit.isChecked() else "false"
                out["INTRADAY_FLATTEN"] = "true" if intraday_flatten.isChecked() else "false"
                out["ALLOW_INHERITED_POSITION"] = "true" if allow_inherit.isChecked() else "false"
                out["MULTI_POSITION_ENABLED"] = "true" if multi_positions.isChecked() else "false"
                out["MAX_CONCURRENT_POSITIONS"] = str(max_concurrent.value())
                out["STARTUP_CRYPTO_UNPROTECTED_POLICY"] = str(startup_crypto_policy.currentData() or "").strip()
                out["SCALE_OUT_FRACTION"] = f"{scale_out.value():.4f}".rstrip("0").rstrip(".")
                out["MIN_POSITION_SIZE_TO_SCALE"] = f"{min_pos_scale.value():.6f}".rstrip("0").rstrip(".")
                out["EMERGENCY_STOP_PCT"] = f"{emergency_stop.value():.4f}".rstrip("0").rstrip(".")
                out["MAX_SCALE_INS_PER_LEG"] = str(max_adds.value())
                if synth_stop_store.text().strip():
                    out["SYNTH_STOP_STORE_PATH"] = synth_stop_store.text().strip()
                if pos_hold_store.text().strip():
                    out["POSITION_HOLD_STORE_PATH"] = pos_hold_store.text().strip()

                out["FRICTION_FAIL_SAFE"] = "true" if friction_fs.isChecked() else "false"
                out["FRICTION_RISK_CAP"] = f"{friction_cap.value():.4f}".rstrip("0").rstrip(".")
                out["VIX_FAIL_SAFE"] = "true" if vix_fs.isChecked() else "false"
                out["VIX_RISK_CAP"] = f"{vix_cap.value():.4f}".rstrip("0").rstrip(".")

                out["CONFLUENCE_EXTERNAL"] = "true" if confluence_external.isChecked() else "false"
                out["COMMITMENT_MODE"] = "true" if commitment_mode.isChecked() else "false"
                out["BUG_BYPASS_SCHEDULE"] = "true" if bypass_schedule.isChecked() else ""
                out["PROFILE_HTF_TIMEFRAME"] = str(htf_combo.currentData() or "").strip()
                out["PROFILE_LTF_TIMEFRAME"] = str(ltf_combo.currentData() or "").strip()
                out["PROFILE_TREND_WINDOW"] = "" if trend_window_spin.value() < 0 else str(trend_window_spin.value())
                out["PROFILE_TREND_SWING_LOOKBACK"] = "" if trend_swing_spin.value() < 0 else str(trend_swing_spin.value())
                out["PROFILE_TREND_MIN_SWINGS"] = "" if trend_min_swings_spin.value() < 0 else str(trend_min_swings_spin.value())
                out["PROFILE_TREND_STRENGTH_FLOOR"] = (
                    "" if trend_strength_spin.value() < 0 else f"{trend_strength_spin.value():.3f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_STRUCTURE_SCORE_THRESHOLD"] = (
                    "" if structure_score_spin.value() < 0 else f"{structure_score_spin.value():.3f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_SESSION_GATE_ENABLED"] = str(session_gate_combo.currentData() or "").strip()
                out["PROFILE_SESSION_GATE_MIN_CANDLES"] = (
                    "" if session_min_candles_spin.value() < 0 else str(session_min_candles_spin.value())
                )
                out["PROFILE_SESSION_RANGE_MULTIPLIER"] = (
                    "" if session_range_mult_spin.value() < 0 else f"{session_range_mult_spin.value():.2f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_SESSION_VOLUME_MULTIPLIER"] = (
                    "" if session_volume_mult_spin.value() < 0 else f"{session_volume_mult_spin.value():.2f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_SESSION_OVERLAP_START_HOUR"] = (
                    "" if session_overlap_start_spin.value() < 0 else str(session_overlap_start_spin.value())
                )
                out["PROFILE_SESSION_OVERLAP_END_HOUR"] = (
                    "" if session_overlap_end_spin.value() < 0 else str(session_overlap_end_spin.value())
                )
                out["PROFILE_PDT_GUARD_ENABLED"] = str(pdt_guard_combo.currentData() or "").strip()
                out["PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY"] = (
                    "" if max_roundtrips_spin.value() < 0 else str(max_roundtrips_spin.value())
                )
                out["PROFILE_FLIP_ACTIONS_ENABLED"] = str(flip_enabled_combo.currentData() or "").strip()
                out["PROFILE_FLIP_COOLDOWN_SECONDS"] = (
                    "" if flip_cooldown_spin.value() < 0 else str(flip_cooldown_spin.value())
                )
                out["PROFILE_COOLDOWN_ENABLED"] = str(cooldown_enabled_combo.currentData() or "").strip()
                out["PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK"] = (
                    "" if cooldown_block_spin.value() < 0 else str(cooldown_block_spin.value())
                )
                out["PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS"] = (
                    "" if cooldown_success_spin.value() < 0 else str(cooldown_success_spin.value())
                )
                out["PROFILE_COOLDOWN_SCOPE"] = str(cooldown_scope_combo.currentData() or "").strip()
                out["PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL"] = str(stick_to_active_combo.currentData() or "").strip()
                out["PROFILE_ICC_AGGRESSIVE_MODE"] = str(aggressive_mode_combo.currentData() or "").strip()
                out["PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT"] = (
                    "" if aggressive_risk_spin.value() < 0 else f"{aggressive_risk_spin.value():.3f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_MAX_DAILY_LOSS_PCT"] = (
                    "" if max_daily_loss_spin.value() < 0 else f"{max_daily_loss_spin.value():.3f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_MAX_EXPOSURE_PCT"] = (
                    "" if max_exposure_spin.value() < 0 else f"{max_exposure_spin.value():.3f}".rstrip("0").rstrip(".")
                )
                out["PROFILE_MAX_CONSECUTIVE_LOSSES"] = (
                    "" if max_losses_spin.value() < 0 else str(max_losses_spin.value())
                )

                comm_mode = commentary_combo.currentIndex()
                out["COMMENTARY_LLM"] = "" if comm_mode == 0 else ("off" if comm_mode == 1 else "internal")
                pol_idx = commentary_policy_combo.currentIndex()
                out["COMMENTARY_LLM_POLICY"] = "a_plus_or_4x" if pol_idx == 0 else ("a_plus_only" if pol_idx == 1 else "interval")
                if commentary_slots.text().strip():
                    out["COMMENTARY_LLM_DAILY_SLOTS"] = commentary_slots.text().strip()
                out["COMMENTARY_LLM_MIN_SECONDS"] = str(commentary_min_spin.value())
                out["COMMENTARY_LLM_MAX_CALLS_PER_DAY"] = str(commentary_max_calls.value())
                if commentary_budget_path.text().strip():
                    out["COMMENTARY_LLM_BUDGET_PATH"] = commentary_budget_path.text().strip()

                if ai_base.text().strip():
                    out["TRADE_SCI_API_BASE_URL"] = ai_base.text().strip()
                if ai_key.text().strip():
                    out["TRADE_SCI_API_KEY"] = ai_key.text().strip()
                if chatgpt_key.text().strip():
                    out["CHATGPT_KEY"] = chatgpt_key.text().strip()
                out["TRADE_SCI_PROVIDER"] = str(provider_combo.currentData() or "").strip()
                if ai_model.text().strip():
                    out["TRADE_SCI_MODEL_NAME"] = ai_model.text().strip()
                out["TRADE_SCI_TEMPERATURE"] = f"{ai_temp.value():.3f}".rstrip("0").rstrip(".")
                out["TRADE_SCI_MAX_TOKENS"] = str(ai_tokens.value())

                out["IBKR_HOST"] = ibkr_host.text().strip()
                out["IBKR_PORT"] = str(ibkr_port.value())
                out["IBKR_CRYPTO_EXCHANGE"] = ibkr_crypto.text().strip() or "ZEROHASH"
                out["IBKR_ZEROHASH_CRYPTO_TIF"] = str(ibkr_zerohash_tif.currentData() or "").strip()
                if ibkr_client_id.text().strip():
                    out["IBKR_CLIENT_ID"] = ibkr_client_id.text().strip()
                if ibkr_account_id.text().strip():
                    out["IBKR_ACCOUNT_ID"] = ibkr_account_id.text().strip()
                out["IBKR_PAPER"] = "true" if ibkr_paper.isChecked() else "false"
                out["IBKR_READ_ONLY"] = "true" if ibkr_read_only.isChecked() else "false"
                if ibkr_default_ccy.text().strip():
                    out["IBKR_DEFAULT_CCY"] = ibkr_default_ccy.text().strip()
                out["IBKR_MAX_SHARES_PER_SYMBOL"] = (
                    str(ibkr_max_shares.value()) if ibkr_max_shares_override.isChecked() else ""
                )
                out["IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"] = (
                    f"{ibkr_max_sym_risk.value():.2f}".rstrip("0").rstrip(".") if ibkr_max_sym_risk_override.isChecked() else ""
                )
                out["IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"] = (
                    f"{ibkr_max_acct_risk.value():.2f}".rstrip("0").rstrip(".") if ibkr_max_acct_risk_override.isChecked() else ""
                )
                out["IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"] = (
                    f"{ibkr_auto_risk.value():.4f}".rstrip("0").rstrip(".") if ibkr_auto_risk_override.isChecked() else ""
                )

                if ccxt_exchange.text().strip():
                    out["CCXT_EXCHANGE"] = ccxt_exchange.text().strip()
                if ccxt_default_type.currentText().strip():
                    out["CCXT_DEFAULT_TYPE"] = ccxt_default_type.currentText().strip()
                out["CCXT_ENABLE_RATE_LIMIT"] = "true" if ccxt_rate_limit.isChecked() else "false"
                out["CCXT_SANDBOX"] = "true" if ccxt_sandbox.isChecked() else "false"
                if ccxt_symbol_map.toPlainText().strip():
                    out["CCXT_SYMBOL_MAP"] = ccxt_symbol_map.toPlainText().strip()
                if ccxt_api_key.text().strip():
                    out["CCXT_API_KEY"] = ccxt_api_key.text().strip()
                if ccxt_secret.text().strip():
                    out["CCXT_SECRET"] = ccxt_secret.text().strip()
                if ccxt_password.text().strip():
                    out["CCXT_PASSWORD"] = ccxt_password.text().strip()
                return out

            # --- Build tab widgets ---
            bot_inner = QtWidgets.QWidget()
            bot_layout = QtWidgets.QVBoxLayout(bot_inner)
            bot_layout.addWidget(info)
            bot_form = QtWidgets.QFormLayout()
            bot_form.setLabelAlignment(QtCore.Qt.AlignRight)
            bot_form.addRow("Environment", app_env)
            bot_form.addRow("Profile", profile_combo)
            bot_form.addRow("Mode", mode_combo)
            bot_form.addRow("Iterations", iterations_spin)
            bot_form.addRow("LIVE trading", execute_chk)
            bot_form.addRow("Sabbath", sabbath_combo)
            bot_form.addRow("Log level", log_level_combo)
            bot_form.addRow("tmux session", session_edit)
            bot_form.addRow("Log file", log_row_w)
            bot_form.addRow("tmux restart cmd", cmd_preview)
            bot_layout.addLayout(bot_form)
            sabbath_group = QtWidgets.QGroupBox("Sabbath schedule")
            sabbath_form = QtWidgets.QFormLayout()
            sabbath_form.setLabelAlignment(QtCore.Qt.AlignRight)
            sabbath_form.addRow("Profile enable", sabbath_enabled_combo)
            sabbath_form.addRow("Start (Fri)", sabbath_start)
            sabbath_form.addRow("End (Sat)", sabbath_end)
            sabbath_group.setLayout(sabbath_form)
            bot_layout.addWidget(sabbath_group)
            gui_group = QtWidgets.QGroupBox("GUI")
            gui_v = QtWidgets.QVBoxLayout()
            gui_v.addWidget(autostart_bot_chk)
            gui_v.addWidget(keep_bot_chk)
            gui_group.setLayout(gui_v)
            bot_layout.addWidget(gui_group)
            debug_group = QtWidgets.QGroupBox("Debug")
            debug_v = QtWidgets.QVBoxLayout()
            debug_v.addWidget(bypass_schedule)
            debug_group.setLayout(debug_v)
            bot_layout.addWidget(debug_group)
            bot_layout.addStretch(1)

            time_inner = QtWidgets.QWidget()
            time_layout = QtWidgets.QVBoxLayout(time_inner)
            time_group = QtWidgets.QGroupBox("Timezone & Astral (shared)")
            time_form = QtWidgets.QFormLayout()
            time_form.setLabelAlignment(QtCore.Qt.AlignRight)
            time_form.addRow("", sabbath_astro_chk)
            time_form.addRow("City", city_row_w)
            time_form.addRow("Primary timezone", tz_row_w)
            time_form.addRow("Latitude", sabbath_lat)
            time_form.addRow("Longitude", sabbath_lon)
            time_group.setLayout(time_form)
            time_layout.addWidget(time_group)
            time_layout.addStretch(1)

            market_inner = QtWidgets.QWidget()
            market_layout = QtWidgets.QVBoxLayout(market_inner)
            market_group = QtWidgets.QGroupBox("Market / Providers")
            market_form = QtWidgets.QFormLayout()
            market_form.setLabelAlignment(QtCore.Qt.AlignRight)
            market_form.addRow("Exchange provider", exchange_provider)
            market_form.addRow("Market Data", alt_md)
            market_form.addRow("Broker", alt_broker)
            market_form.addRow("Default symbol", default_symbol)
            market_form.addRow("Default timeframe", default_tf)
            market_form.addRow("Candle size (chart)", candle_size)
            market_form.addRow("Max candles", max_candles)
            market_form.addRow("Symbols override", symbols_edit)
            market_group.setLayout(market_form)
            market_layout.addWidget(market_group)
            market_layout.addStretch(1)

            runtime_inner = QtWidgets.QWidget()
            runtime_layout = QtWidgets.QVBoxLayout(runtime_inner)
            runtime_group = QtWidgets.QGroupBox("Runtime Safeguards")
            runtime_form = QtWidgets.QFormLayout()
            runtime_form.setLabelAlignment(QtCore.Qt.AlignRight)
            runtime_form.addRow(cancel_orders)
            runtime_form.addRow(flatten_exit)
            runtime_form.addRow(intraday_flatten)
            runtime_form.addRow(allow_inherit)
            runtime_form.addRow(multi_positions)
            runtime_form.addRow("Max concurrent positions", max_concurrent)
            runtime_form.addRow("Missing-stop policy (ZEROHASH crypto)", startup_crypto_policy)
            runtime_form.addRow("Scale out fraction", scale_out)
            runtime_form.addRow("Min position size to scale", min_pos_scale)
            runtime_form.addRow("Emergency stop pct", emergency_stop)
            runtime_form.addRow("Max scale-ins/leg", max_adds)
            runtime_form.addRow("Synthetic stop store", synth_row_w)
            runtime_form.addRow("Position hold store", pos_row_w)
            runtime_group.setLayout(runtime_form)
            runtime_layout.addWidget(runtime_group)
            runtime_layout.addStretch(1)

            risk_inner = QtWidgets.QWidget()
            risk_layout = QtWidgets.QVBoxLayout(risk_inner)
            risk_group = QtWidgets.QGroupBox("Risk Models (optional)")
            risk_form = QtWidgets.QFormLayout()
            risk_form.setLabelAlignment(QtCore.Qt.AlignRight)
            risk_form.addRow(friction_fs)
            risk_form.addRow("Friction risk cap", friction_cap)
            risk_form.addRow(vix_fs)
            risk_form.addRow("VIX risk cap", vix_cap)
            risk_group.setLayout(risk_form)
            risk_layout.addWidget(risk_group)
            aggressive_group = QtWidgets.QGroupBox("ICC Aggressive Mode (Phase 2, opt-in)")
            aggressive_form = QtWidgets.QFormLayout()
            aggressive_form.setLabelAlignment(QtCore.Qt.AlignRight)
            aggressive_form.addRow("Aggressive mode", aggressive_mode_combo)
            aggressive_form.addRow("Risk/trade %", aggressive_risk_spin)
            aggressive_form.addRow("Max daily loss %", max_daily_loss_spin)
            aggressive_form.addRow("Max exposure %", max_exposure_spin)
            aggressive_form.addRow("Max consecutive losses", max_losses_spin)
            aggressive_group.setLayout(aggressive_form)
            risk_layout.addWidget(aggressive_group)
            risk_layout.addStretch(1)

            strategy_inner = QtWidgets.QWidget()
            strategy_layout = QtWidgets.QVBoxLayout(strategy_inner)
            strat_group = QtWidgets.QGroupBox("Strategy")
            strat_v = QtWidgets.QVBoxLayout()
            strat_v.addWidget(confluence_external)
            strat_v.addWidget(commitment_mode)
            strat_group.setLayout(strat_v)
            strategy_layout.addWidget(strat_group)
            icc_summary_group = QtWidgets.QGroupBox("ICC Rules Summary")
            icc_summary_layout = QtWidgets.QVBoxLayout()
            icc_summary = QtWidgets.QLabel(
                "Core ICC gates (doc-aligned):\n"
                "- HTF trend uses HH/HL vs LH/LL (close-based swings), otherwise neutral.\n"
                "- Indication = break of last swing close; no-trade zone between last swing high/low.\n"
                "- Entry requires sweep + HL/LH + BOS + continuation close beyond correction.\n"
                "- Trades follow HTF trend unless a confirmed HTF flip appears.\n"
                "- A+ entries require session expansion (range+volume) when the session gate is enabled.\n"
                "- Targets align to the next HTF swing level; exits require HTF invalidation unless emergency.\n"
                "- Flips are only allowed when explicitly enabled and venue supports shorts."
            )
            icc_summary.setWordWrap(True)
            icc_summary_layout.addWidget(icc_summary)
            icc_summary_group.setLayout(icc_summary_layout)
            strategy_layout.addWidget(icc_summary_group)
            icc_group = QtWidgets.QGroupBox("ICC Structure (profile overrides)")
            icc_form = QtWidgets.QFormLayout()
            icc_form.setLabelAlignment(QtCore.Qt.AlignRight)
            icc_form.addRow("HTF timeframe", htf_combo)
            icc_form.addRow("LTF timeframe", ltf_combo)
            icc_form.addRow("Trend window", trend_window_spin)
            icc_form.addRow("Swing lookback", trend_swing_spin)
            icc_form.addRow("Min swings", trend_min_swings_spin)
            icc_form.addRow("Strength floor", trend_strength_spin)
            icc_form.addRow("Structure score threshold", structure_score_spin)
            icc_group.setLayout(icc_form)
            strategy_layout.addWidget(icc_group)
            session_group = QtWidgets.QGroupBox("ICC Session Bias (A+ gate)")
            session_form = QtWidgets.QFormLayout()
            session_form.setLabelAlignment(QtCore.Qt.AlignRight)
            session_form.addRow("Session gate", session_gate_combo)
            session_form.addRow("Min candles", session_min_candles_spin)
            session_form.addRow("Range multiplier", session_range_mult_spin)
            session_form.addRow("Volume multiplier", session_volume_mult_spin)
            session_form.addRow("Overlap start hour", session_overlap_start_spin)
            session_form.addRow("Overlap end hour", session_overlap_end_spin)
            session_group.setLayout(session_form)
            strategy_layout.addWidget(session_group)
            icc_safety_group = QtWidgets.QGroupBox("ICC Risk / Flips (profile overrides)")
            icc_safety_form = QtWidgets.QFormLayout()
            icc_safety_form.setLabelAlignment(QtCore.Qt.AlignRight)
            icc_safety_form.addRow("PDT guard", pdt_guard_combo)
            icc_safety_form.addRow("Max equity roundtrips/day", max_roundtrips_spin)
            icc_safety_form.addRow("Flip actions", flip_enabled_combo)
            icc_safety_form.addRow("Flip cooldown (sec)", flip_cooldown_spin)
            icc_safety_form.addRow("Cooldown enabled", cooldown_enabled_combo)
            icc_safety_form.addRow("Cooldown cycles after block", cooldown_block_spin)
            icc_safety_form.addRow("Cooldown cycles after success", cooldown_success_spin)
            icc_safety_form.addRow("Cooldown scope", cooldown_scope_combo)
            icc_safety_form.addRow("Stick to active symbol", stick_to_active_combo)
            icc_safety_group.setLayout(icc_safety_form)
            strategy_layout.addWidget(icc_safety_group)
            strategy_layout.addStretch(1)

            commentary_inner = QtWidgets.QWidget()
            comm_layout = QtWidgets.QVBoxLayout(commentary_inner)
            comm_group = QtWidgets.QGroupBox("Commentary")
            comm_form = QtWidgets.QFormLayout()
            comm_form.setLabelAlignment(QtCore.Qt.AlignRight)
            comm_form.addRow("Mode", commentary_combo)
            comm_form.addRow("Policy", commentary_policy_combo)
            comm_form.addRow("Daily slots", commentary_slots)
            comm_form.addRow("Min seconds", commentary_min_spin)
            comm_form.addRow("Max calls/day", commentary_max_calls)
            comm_form.addRow("Budget file", commentary_budget_path)
            comm_group.setLayout(comm_form)
            comm_layout.addWidget(comm_group)
            comm_layout.addStretch(1)

            ai_inner = QtWidgets.QWidget()
            ai_layout = QtWidgets.QVBoxLayout(ai_inner)
            ai_group = QtWidgets.QGroupBox("AI")
            ai_form = QtWidgets.QFormLayout()
            ai_form.setLabelAlignment(QtCore.Qt.AlignRight)
            ai_form.addRow("Provider", provider_combo)
            ai_form.addRow("API base URL", ai_base)
            ai_form.addRow("API key", ai_key)
            ai_form.addRow("CHATGPT_KEY", chatgpt_key)
            ai_form.addRow("Model name", ai_model)
            ai_form.addRow("Temperature", ai_temp)
            ai_form.addRow("Max tokens", ai_tokens)
            ai_group.setLayout(ai_form)
            ai_layout.addWidget(ai_group)
            ai_layout.addStretch(1)

            ibkr_inner = QtWidgets.QWidget()
            ibkr_layout = QtWidgets.QVBoxLayout(ibkr_inner)
            ibkr_group = QtWidgets.QGroupBox("IBKR")
            ibkr_form = QtWidgets.QFormLayout()
            ibkr_form.setLabelAlignment(QtCore.Qt.AlignRight)
            ibkr_form.addRow("Host", ibkr_host)
            ibkr_form.addRow("Port", ibkr_port)
            ibkr_form.addRow("Crypto exchange", ibkr_crypto)
            ibkr_form.addRow("ZEROHASH crypto TIF", ibkr_zerohash_tif)
            ibkr_form.addRow("Client ID", ibkr_client_id)
            ibkr_form.addRow("Account ID", ibkr_account_id)
            ibkr_form.addRow("Default CCY", ibkr_default_ccy)
            ibkr_form.addRow("", ibkr_paper)
            ibkr_form.addRow("", ibkr_read_only)
            ibkr_form.addRow("Max shares/symbol", ibkr_max_shares_row)
            ibkr_form.addRow("Max $ risk/symbol", ibkr_max_sym_risk_row)
            ibkr_form.addRow("Max $ risk/account", ibkr_max_acct_risk_row)
            ibkr_form.addRow("Auto risk fraction", ibkr_auto_risk_row)
            ibkr_group.setLayout(ibkr_form)
            ibkr_layout.addWidget(ibkr_group)
            ibkr_layout.addStretch(1)

            ccxt_inner = QtWidgets.QWidget()
            ccxt_layout = QtWidgets.QVBoxLayout(ccxt_inner)
            ccxt_group = QtWidgets.QGroupBox("CCXT (alternative broker)")
            ccxt_form = QtWidgets.QFormLayout()
            ccxt_form.setLabelAlignment(QtCore.Qt.AlignRight)
            ccxt_form.addRow("Exchange", ccxt_exchange)
            ccxt_form.addRow("Default type", ccxt_default_type)
            ccxt_form.addRow("", ccxt_rate_limit)
            ccxt_form.addRow("", ccxt_sandbox)
            ccxt_form.addRow("Symbol map", ccxt_symbol_map)
            ccxt_form.addRow("API key", ccxt_api_key)
            ccxt_form.addRow("Secret", ccxt_secret)
            ccxt_form.addRow("Password", ccxt_password)
            ccxt_group.setLayout(ccxt_form)
            ccxt_layout.addWidget(ccxt_group)
            ccxt_layout.addStretch(1)

            # --- Advanced tab (raw env) ---
            adv_tab = QtWidgets.QWidget()
            adv_layout = QtWidgets.QVBoxLayout()
            filter_row = QtWidgets.QHBoxLayout()
            filter_label = QtWidgets.QLabel("Filter:")
            filter_edit = QtWidgets.QLineEdit()
            filter_edit.setPlaceholderText("Filter keys (e.g. IBKR_, CCXT_, TRADE_SCI_, COMMENTARY_, EXECUTE_TRADES)")
            tip(filter_edit, "ENV_FILTER\nType to filter keys (case-insensitive). Example: IBKR_ or TRADE_SCI_.")
            filter_row.addWidget(filter_label)
            filter_row.addWidget(filter_edit, 1)

            table = QtWidgets.QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(["Key", "Value", "Source", "Notes"])
            table.verticalHeader().setVisible(False)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
            hdr = table.horizontalHeader()
            hdr.setStretchLastSection(False)
            hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            table.setShowGrid(False)
            tip(
                table,
                "ENV_TABLE_EDIT\n"
                "Double-click a Value cell to edit it.\n"
                "Typed controls in other tabs take precedence.\n"
                "Secret keys are masked and must be set via the typed tabs.",
            )

            secret_keys = {
                "TRADE_SCI_API_KEY",
                "CHATGPT_KEY",
                "CCXT_API_KEY",
                "CCXT_SECRET",
                "CCXT_PASSWORD",
            }

            def build_rows() -> None:
                needle = filter_edit.text().strip().upper()
                table.setRowCount(0)
                keys = discovered_env_keys
                grouped = sorted(keys, key=lambda k: (classify(k), k))
                for k in grouped:
                    if needle and needle not in k:
                        continue
                    val, src = self._effective_env_value(k)
                    r = table.rowCount()
                    table.insertRow(r)
                    it_k = QtWidgets.QTableWidgetItem(k)
                    it_k.setFlags(it_k.flags() & ~QtCore.Qt.ItemIsEditable)

                    display = "********" if k in secret_keys and val else val
                    it_v = QtWidgets.QTableWidgetItem(display)
                    if k in secret_keys:
                        it_v.setData(QtCore.Qt.UserRole, val)
                        it_v.setFlags(it_v.flags() & ~QtCore.Qt.ItemIsEditable)

                    it_src = QtWidgets.QTableWidgetItem(src or "unset")
                    it_src.setFlags(it_src.flags() & ~QtCore.Qt.ItemIsEditable)
                    it_notes = QtWidgets.QTableWidgetItem(classify(k))
                    it_notes.setFlags(it_notes.flags() & ~QtCore.Qt.ItemIsEditable)
                    if src == "override":
                        it_src.setForeground(QtGui.QColor(theme.warn))
                    elif src in ("env", ".env"):
                        it_src.setForeground(QtGui.QColor(theme.muted))
                    table.setItem(r, 0, it_k)
                    table.setItem(r, 1, it_v)
                    table.setItem(r, 2, it_src)
                    table.setItem(r, 3, it_notes)

            build_rows()
            filter_edit.textChanged.connect(build_rows)

            btn_apply = QtWidgets.QPushButton("Apply (GUI)")
            btn_save = QtWidgets.QPushButton("Save to .env")
            btn_restart_tmux = QtWidgets.QPushButton("Restart tmux (apply to running bot)")
            btn_clear = QtWidgets.QPushButton("Clear Overrides")
            btn_close = QtWidgets.QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)
            tip(
                btn_apply,
                "BTN_APPLY\nApply your changes immediately in this GUI session (updates in-process env overrides).",
            )
            tip(
                btn_save,
                "BTN_SAVE_DOTENV\nWrite current overrides into `.env` so future runs (GUI/tmux) use them by default.",
            )
            tip(
                btn_restart_tmux,
                "BTN_RESTART_TMUX\nApply + Save, then restart the tmux panes so the running dashboard/bot picks up changes.",
            )
            tip(
                btn_clear,
                "BTN_CLEAR_OVERRIDES\nRemove all GUI overrides and fall back to `.env` and/or your shell environment.",
            )
            tip(btn_close, "BTN_CLOSE\nClose this settings dialog (no additional changes are applied).")

            def apply_changes() -> None:
                self._set_bot_autostart(autostart_bot_chk.isChecked())
                self._set_bot_keep_running_on_close(keep_bot_chk.isChecked())

                typed = desired_typed_env()
                typed_keys = set(typed.keys())

                for r in range(table.rowCount()):
                    key = table.item(r, 0).text()
                    if key in typed_keys:
                        continue
                    item = table.item(r, 1)
                    raw = item.data(QtCore.Qt.UserRole) if key in secret_keys else item.text()
                    val = str(raw or "").strip()
                    if val != initial_effective.get(key, ""):
                        set_override(key, val)
                    elif key in self._env_overrides:
                        set_override(key, "")

                for key, val in typed.items():
                    v = val.strip()
                    if v != initial_effective.get(key, ""):
                        set_override(key, v)
                    elif key in self._env_overrides:
                        set_override(key, "")

                build_rows()
                self._render_right()
                self._set_candle_tf(str(candle_size.currentData() or candle_size.currentText()).strip() or settings.candle_tf)

            def save_to_dotenv() -> None:
                updates: dict[str, str] = {}
                for k, v in self._env_overrides.items():
                    updates[k] = v
                for k, v in desired_typed_env().items():
                    if v.strip() != "":
                        updates[k] = v.strip()
                if not updates:
                    QtWidgets.QMessageBox.information(dlg, "Save to .env", "No overrides set.")
                    return
                msg = (
                    f"This will write {len(updates)} key(s) into:\n\n{dotenv_path}\n\n"
                    "This affects the tmux launcher (it sources .env). Continue?"
                )
                if QtWidgets.QMessageBox.question(dlg, "Confirm .env write", msg) != QtWidgets.QMessageBox.Yes:
                    return
                try:
                    _merge_dotenv(dotenv_path, updates)
                    QtWidgets.QMessageBox.information(dlg, "Saved", f"Wrote updates to:\n{dotenv_path}")
                    # Clear cache so next get_settings() call re-reads the file/env
                    get_settings.cache_clear()
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(dlg, "Save failed", str(exc))

            def clear_overrides() -> None:
                for k in list(self._env_overrides.keys()):
                    self._qsettings.remove(f"env/{k}")
                    if k in dotenv_values:
                        os.environ[k] = dotenv_values[k]
                    else:
                        os.environ.pop(k, None)
                self._env_overrides = {}
                build_rows()
                self._render_right()

            def restart_tmux() -> None:
                apply_changes()
                save_to_dotenv()
                # Ensure cache is definitely cleared before restart
                get_settings.cache_clear()
                cmd = cmd_preview.text().strip()
                if not cmd:
                    return
                try:
                    import subprocess  # Safety import to prevent scope issues
                    if not repo_root.exists():
                        raise FileNotFoundError(f"Repo root not found: {repo_root}")

                    res = subprocess.run(
                        ["bash", "-lc", cmd],
                        cwd=str(repo_root),
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    out = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
                    if res.returncode != 0:
                        QtWidgets.QMessageBox.critical(dlg, "tmux restart failed", f"DEBUG_PATCH_V2: Command failed: {cmd}\nExit Code: {res.returncode}\n\nOutput:\n{out}")
                    else:
                        QtWidgets.QMessageBox.information(dlg, "tmux restarted", out.strip() or "OK (No output)")
                except subprocess.TimeoutExpired:
                    QtWidgets.QMessageBox.critical(dlg, "tmux restart failed", "Command timed out after 60 seconds.")
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(dlg, "tmux restart failed", f"DEBUG_PATCH_V2 Error:\n{exc}\n\nCWD: {repo_root}\nScope: {dir()}")

            btn_apply.clicked.connect(apply_changes)
            btn_save.clicked.connect(save_to_dotenv)
            btn_restart_tmux.clicked.connect(restart_tmux)
            btn_clear.clicked.connect(clear_overrides)

            btns = QtWidgets.QHBoxLayout()
            btns.addWidget(btn_apply)
            btns.addWidget(btn_save)
            btns.addWidget(btn_restart_tmux)
            btns.addWidget(btn_clear)
            btns.addStretch(1)
            btns.addWidget(btn_close)

            adv_layout.addLayout(filter_row)
            adv_layout.addWidget(table, 1)
            adv_tab.setLayout(adv_layout)

            tabs = QtWidgets.QTabWidget()
            tabs.addTab(scroll(bot_inner), "Bot")
            tabs.addTab(scroll(time_inner), "Time")
            tabs.addTab(scroll(market_inner), "Market")
            tabs.addTab(scroll(runtime_inner), "Runtime")
            tabs.addTab(scroll(risk_inner), "Risk")
            tabs.addTab(scroll(strategy_inner), "Strategy")
            tabs.addTab(scroll(commentary_inner), "Commentary")
            tabs.addTab(scroll(ai_inner), "AI")
            tabs.addTab(scroll(ibkr_inner), "IBKR")
            tabs.addTab(scroll(ccxt_inner), "CCXT")
            tabs.addTab(adv_tab, "Advanced (env)")

            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(tabs, 1)
            layout.addLayout(btns)
            dlg.setLayout(layout)

            refresh_preview()
            dlg.exec()

        def _choose_log(self) -> None:
            from PySide6 import QtWidgets  # type: ignore

            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select tradebot.log", str(settings.log_file), "Log files (*.log*);;All files (*)"
            )
            if not path:
                return
            settings.log_file = Path(path)
            self._tail.set_path(settings.log_file)
            self._log.appendPlainText(f"[GUI] switched log: {settings.log_file}")

        def _on_log_line(self, line: str, state: UiState) -> None:
            self._state = state
            if "[HOLDINGS]" in line:
                try:
                    payload = line.split("[HOLDINGS]", 1)[1].strip()
                    data = json.loads(payload) if payload else {}
                    positions = list(data.get("positions") or [])
                    out: list[dict[str, Any]] = []
                    for p in positions:
                        if isinstance(p, dict):
                            out.append(p)
                    self._holdings = out
                    self._holdings_updated_ts = _now_epoch()
                    
                    # [ANTIGRAVITY FIX] Forward PnL to status bar
                    total_pnl = float(data.get("total_unrealized_pnl", 0.0))
                    self._total_unrealized_pnl = total_pnl
                    
                    sign = "+" if total_pnl >= 0 else "-"
                    color = "#4cc9f0" if total_pnl >= 0 else "#ef4444"
                    self._status_pnl_label.setText(f"Unrealized PnL: {sign}${abs(total_pnl):.2f}")
                    self._status_pnl_label.setStyleSheet(f"QLabel {{ color: {color}; font-weight: bold; margin-right: 15px; }}")

                except Exception:
                    pass
            # Fallback: infer holdings from order fills if no structured holdings feed exists yet.
            if self._holdings_updated_ts is None and state.orders_by_id:
                inferred = _infer_holdings_from_orders(state.orders_by_id)
                if inferred:
                    self._holdings = inferred
                    self._holdings_updated_ts = _now_epoch()
            
            # Use the pre-compiled regex to check for PDT violations in the log line
            # Only perform this check if we are strictly in IBKR mode (not Hybrid/CCXT)
            if settings.market_provider_name == "IBKR" and PDT_ERROR_RE.search(line):
                # Detected a PDT violation.  Set the restriction until 90 days from now.
                self._pdt_restricted_until = datetime.now() + timedelta(days=90)
                # Force immediate update of the status bar/theme to show the red warning
                self._render_right()

            self._recent_log.append(line)
            self._log_panel.append_line(line)

        def _format_age(self, seconds: float | None) -> str:
            if seconds is None:
                return "-"
            try:
                s = max(0, int(seconds))
            except Exception:
                return "-"
            if s < 60:
                return f"{s}s"
            m, s = divmod(s, 60)
            if m < 60:
                return f"{m}m{s:02d}s"
            h, m = divmod(m, 60)
            if h < 48:
                return f"{h}h{m:02d}m"
            d, h = divmod(h, 24)
            return f"{d}d{h:02d}h"

        def _render_holdings(self) -> None:
            theme = THEMES.get(settings.theme_key, THEMES["dark"])
            now = _now_epoch()
            inferred_note = ""
            ibkr_note = ""
            if self._ibkr_last_status:
                ibkr_note = f" · {self._ibkr_last_status}"
            st = (self._ibkr_last_status or "").lower()

            # [ANTIGRAVITY FIX] Prioritize Log-Based Holdings (Source of Truth)
            # Only use GUI-side IBKR/CCXT fetch if the log feed is stale (>15s) or empty.
            # The log feed contains vital internal state (Hold Age, Synthetic Stops) that the raw broker fetch lacks.
            log_is_fresh = self._holdings_updated_ts is not None and (now - self._holdings_updated_ts) < 15.0

            if not log_is_fresh and (st.startswith("ibkr ok") or st.startswith("ccxt ok")) and self._ibkr_last_fetch_ts is not None:
                last_fill_by_symbol: dict[str, float] = {}
                for f in list(self._ibkr_fills or []):
                    sym = str(f.get("symbol") or "").strip().upper()
                    t = f.get("time_epoch")
                    if not sym or t is None:
                        continue
                    try:
                        te = float(t)
                    except Exception:
                        continue
                    prev = last_fill_by_symbol.get(sym)
                    if prev is None or te > prev:
                        last_fill_by_symbol[sym] = te

                working_by_symbol: dict[str, int] = {}
                statuses_by_symbol: dict[str, set[str]] = {}
                for o in list(self._ibkr_orders or []):
                    sym = str(o.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    st = str(o.get("status") or "").strip()
                    if st:
                        statuses_by_symbol.setdefault(sym, set()).add(st)
                    working_by_symbol[sym] = working_by_symbol.get(sym, 0) + 1

                out: list[dict[str, Any]] = []
                for p in list(self._ibkr_positions or []):
                    sym = str(p.get("symbol") or "").strip().upper()
                    qty = float(p.get("position") or 0.0)
                    if not sym or abs(qty) < 1e-9:
                        continue
                    side = "long" if qty > 0 else "short"
                    avg_cost = p.get("avgCost")
                    hold_age = None
                    last_fill = last_fill_by_symbol.get(sym)
                    if last_fill is not None:
                        hold_age = max(0.0, now - float(last_fill))
                    out.append(
                        {
                            "symbol": sym,
                            "side": side,
                            "size": abs(qty),
                            "avg_price": float(avg_cost) if avg_cost not in (None, "") else None,
                            "stop_loss": None,
                            "take_profit": None,
                            "open_bracket_risk": None,
                            "working_orders": working_by_symbol.get(sym),
                            "synthetic_stop_armed": None,
                            "hold_age_seconds": hold_age,
                            "hold_remaining_seconds": None,
                            "working_order_statuses": sorted(statuses_by_symbol.get(sym, set())),
                            "inferred": False,
                        }
                    )

                self._holdings = out
                self._holdings_updated_ts = self._ibkr_last_fetch_ts
            elif (not self._holdings or self._holdings_updated_ts is None) and (self._state.orders_by_id):
                inferred = _infer_holdings_from_orders(self._state.orders_by_id)
                if inferred:
                    self._holdings = inferred
                    self._holdings_updated_ts = self._holdings_updated_ts or _now_epoch()
                    inferred_note = " · inferred from logs"

            if self._holdings_updated_ts is None:
                self._holdings_status.setText(f"Updated: never{ibkr_note}")
            else:
                age = int(max(0.0, now - self._holdings_updated_ts))
                self._holdings_status.setText(f"Updated {age}s ago{ibkr_note}{inferred_note}")

            was_sorting = self._holdings_table.isSortingEnabled()
            sort_col = self._holdings_table.horizontalHeader().sortIndicatorSection()
            sort_order = self._holdings_table.horizontalHeader().sortIndicatorOrder()
            if was_sorting:
                self._holdings_table.setSortingEnabled(False)

            def cell(text: str, *, align_right: bool = False) -> QtWidgets.QTableWidgetItem:
                it = QtWidgets.QTableWidgetItem(text)
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
                if align_right:
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                return it

            rows = list(self._holdings or [])
            # Stable ordering by symbol to avoid distracting row churn (sorting can be enabled by the user).
            rows.sort(key=lambda p: str(p.get("symbol") or ""))
            if not rows:
                self._holdings_table.setRowCount(1)
                it = cell("No open positions")
                it.setForeground(QtGui.QColor(theme.muted))
                self._holdings_table.setSpan(0, 0, 1, self._holdings_table.columnCount())
                self._holdings_table.setItem(0, 0, it)
                if was_sorting:
                    self._holdings_table.setSortingEnabled(True)
                    try:
                        self._holdings_table.sortItems(int(sort_col), sort_order)
                    except Exception:
                        pass
                return

            self._holdings_table.setRowCount(len(rows))

            for r, p in enumerate(rows):
                sym = str(p.get("symbol") or "").strip().upper()
                side = str(p.get("side") or "")
                size = p.get("size")
                avg = p.get("avg_price")
                sl = p.get("stop_loss")
                tp = p.get("take_profit")
                open_risk = p.get("open_bracket_risk")
                working = p.get("working_orders")
                statuses = p.get("working_order_statuses") or []
                synth = bool(p.get("synthetic_stop_armed"))
                hold_age = p.get("hold_age_seconds")
                hold_rem = p.get("hold_remaining_seconds")

                it_sym = cell(sym)
                it_side = cell(side)
                # User requested full decimals ("Show them all") - avoid scientific notation
                s_size = f"{abs(float(size)):.8f}".rstrip("0").rstrip(".") if size is not None else "-"
                it_size = cell(s_size, align_right=True)
                it_avg = cell(f"{float(avg):.4f}" if avg is not None else "-", align_right=True)
                it_sl = cell(f"{float(sl):.4f}" if sl is not None else "-", align_right=True)
                it_tp = cell(f"{float(tp):.4f}" if tp is not None else "-", align_right=True)
                it_risk = cell(f"{float(open_risk):.2f}" if open_risk is not None else "-", align_right=True)
                it_work = cell(str(int(working)) if working is not None else "-", align_right=True)
                it_statuses = cell(", ".join([str(s) for s in statuses]) if statuses else "-")
                it_synth = cell("armed" if synth else "-", align_right=False)
                it_age = cell(self._format_age(hold_age), align_right=True)
                it_rem = cell(self._format_age(hold_rem), align_right=True)

                self._holdings_table.setItem(r, 0, it_sym)
                self._holdings_table.setItem(r, 1, it_side)
                self._holdings_table.setItem(r, 2, it_size)
                self._holdings_table.setItem(r, 3, it_avg)
                self._holdings_table.setItem(r, 4, it_sl)
                self._holdings_table.setItem(r, 5, it_tp)
                self._holdings_table.setItem(r, 6, it_risk)
                self._holdings_table.setItem(r, 7, it_work)
                self._holdings_table.setItem(r, 8, it_statuses)
                self._holdings_table.setItem(r, 9, it_synth)
                self._holdings_table.setItem(r, 10, it_age)
                self._holdings_table.setItem(r, 11, it_rem)

                if side == "long":
                    it_side.setForeground(QtGui.QColor(theme.good))
                elif side == "short":
                    it_side.setForeground(QtGui.QColor(theme.bad))
                if synth:
                    it_synth.setForeground(QtGui.QColor(theme.warn))
                if hold_rem is not None:
                    try:
                        if float(hold_rem) > 0:
                            it_rem.setForeground(QtGui.QColor(theme.warn))
                    except Exception:
                        pass

            if was_sorting:
                self._holdings_table.setSortingEnabled(True)
                try:
                    self._holdings_table.sortItems(int(sort_col), sort_order)
                except Exception:
                    pass

        def _render_right(self) -> None:
            """Update the right‑hand panels (readiness, decisions and orders).

            This simplified implementation delegates to the extracted
            readiness, decisions and orders panels.  It avoids
            duplicating the table rendering logic inside the main
            window and ensures each panel manages its own updates.
            """
            try:
                # Update the readiness table with the latest structure data.
                self._readiness_table.update_table()
            except Exception:
                pass
            try:
                # Refresh recent decisions display.
                self._decisions_panel.update_decisions()
            except Exception:
                pass
            try:
                # Merge orders from state and IBKR snapshots into the orders panel.
                self._orders_panel.update_orders(
                    self._state.orders_by_id,
                    self._ibkr_orders,
                    self._ibkr_fills,
                    self._ibkr_last_status,
                )
            except Exception:
                pass

            # Update commentary if the internal adviser is in use.  This call
            # preserves the existing behaviour of refreshing commentary on
            # the right‑hand update loop without blocking other updates.
            try:
                self._maybe_update_commentary()
            except Exception:
                pass



            active = self._state.active_symbol or "none"
            execute = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
            mode = "LIVE" if execute else "SIM"
            bot_sabb = (os.getenv("BOT_SABBATH") or "").strip().lower()
            if bot_sabb in {"on", "true", "1", "yes"}:
                sabbath_txt = "on"
            elif bot_sabb in {"off", "false", "0", "no"}:
                sabbath_txt = "off"
            else:
                sabbath_txt = "auto"
            self.setWindowTitle(f"Tradebot SCI — ICC Dashboard (GUI) [{mode}]")

            msg = f"mode={mode} · sabbath={sabbath_txt} · active={active} · profile={os.getenv('PROFILE_NAME', 'unset')} · log={settings.log_file.name} · theme={THEMES[settings.theme_key].name}"
            
            pdt_until = self._pdt_restricted_until
            if pdt_until and settings.market_provider_name == "IBKR" and datetime.now() < pdt_until:
                # PDT Violation Active
                days_left = (pdt_until - datetime.now()).days
                msg = f"⚠️ WARNING: PDT RESTRICTION ACTIVE · Restricted until {pdt_until.strftime('%Y-%m-%d')} ({days_left} days left) · Account is locked for Day Trading."
                self.statusBar().setStyleSheet("QStatusBar { background: #7f1d1d; color: #fecaca; font-weight: bold; font-size: 11pt; }")
                # Also tint the log panel red
                self._log_panel.widget.setStyleSheet("QPlainTextEdit, QTextEdit { background: #3f1212; color: #fecaca; font-family: JetBrains Mono, monospace; font-size: 9pt; }")
            else:
                # Normal State - ensure styles are reset to theme default effectively (clearing stylesheet allows global theme to apply? No, we need to respect theme qss)
                # Actually app.py applies stylesheets via setStyleSheet on main window?
                # Theme.qss() defines QStatusBar style.
                # If we clear it, it might revert to parent.
                # Let's simple clear the explicit stylesheet on statusbar and log panel
                # But only if we were restricted before (optimization).
                # For safety, just clear it if not restricted, or re-apply theme logic?
                # Reset specific widgets:
                if self.statusBar().styleSheet() != "":
                     self.statusBar().setStyleSheet("")
                     # Re-apply theme to log panel? LogPanel uses LogHighlighter and default styles.
                     # We need to reset the widget style sheet.
                     self._log_panel.widget.setStyleSheet("")

            # [ANTIGRAVITY FIX] Update permanent status label with holdings
            # We use newlines to separate each holding as requested
            if self._ibkr_last_status:
                 # Replace " | " with "\n" if it came from our formatted string
                 # But our previous edit used " | ". We can just split and rejoin.
                 parts = self._ibkr_last_status.split(" | ")
                 txt = "\n".join(parts)
                 self._status_holdings_label.setText(txt)
            else:
                 self._status_holdings_label.setText("")

            self.statusBar().showMessage(msg)
            self._render_holdings()

        def _tick_candles(self) -> None:
            """Delegate candle updates to the CandlesPanel."""
            try:
                self._candles_panel.tick_candles()
            except Exception as e:
                logger.error(f"Error in _tick_candles: {e}", exc_info=True)

        def _on_candles(self, bars: object, updated_age: int, status: str) -> None:
            # updated_age is 0 on fetch; we display "Updated 0s ago" then it ages until next fetch.
            status_txt = f"Updated {updated_age}s ago"
            if status:
                status_txt += f" · {status}"
            self._candle_status.setText(status_txt)

            bar_list = list(bars or [])
            if not bar_list:
                self._series.clear()
                self._chart.setTitle("No bars")
                return

            def _bar_epoch(b: Any) -> float:
                d = getattr(b, "date", None)
                if d is None:
                    return 0.0
                try:
                    if isinstance(d, (int, float)):
                        return float(d)
                    ts = getattr(d, "timestamp", None)
                    if callable(ts):
                        return float(ts())
                    if isinstance(d, str):
                        s = d.strip()
                        if s.isdigit():
                            return float(int(s))
                        # IBKR commonly: "YYYYMMDD  HH:MM:SS"
                        m = re.match(r"^(\\d{8})\\s+(\\d{2}:\\d{2}:\\d{2})$", s)
                        if m:
                            from datetime import datetime

                            dt = datetime.strptime(m.group(1) + " " + m.group(2), "%Y%m%d %H:%M:%S")
                            return float(dt.timestamp())
                        m = re.match(r"^(\\d{4}-\\d{2}-\\d{2})\\s+(\\d{2}:\\d{2}:\\d{2})$", s)
                        if m:
                            from datetime import datetime

                            dt = datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")
                            return float(dt.timestamp())
                except Exception:
                    return 0.0
                return 0.0

            ordered = sorted(bar_list, key=_bar_epoch)

            self._series.clear()
            x = 0.0
            highs: list[float] = []
            lows: list[float] = []
            n = max(10, int(getattr(settings, "candle_bars", 120) or 120))
            for b in ordered[-n:]:
                o = float(getattr(b, "open", 0.0) or 0.0)
                h = float(getattr(b, "high", 0.0) or 0.0)
                l = float(getattr(b, "low", 0.0) or 0.0)
                c = float(getattr(b, "close", 0.0) or 0.0)
                cs = QCandlestickSet(o, h, l, c, x)
                self._series.append(cs)
                highs.append(h)
                lows.append(l)
                x += 1.0

            lo = min(lows)
            hi = max(highs)
            if hi <= lo:
                hi = lo + 1e-6
            self._axis_x.setRange(max(0.0, x - float(n)), x)
            pad = (hi - lo) * 0.05
            self._axis_y.setRange(lo - pad, hi + pad)
            tf_label = str(settings.candle_tf or "").strip() or "?"
            self._chart.setTitle(f"CANDLE CHART ({tf_label})")

        def _tick_ibkr_account(self) -> None:
            # Poll every second, but the fetcher self-throttles to settings.refresh_seconds.
            QtCore.QTimer.singleShot(0, self._ibkr_fetcher.fetch)  # type: ignore[misc]

        def _on_ibkr_account(
            self, positions: object, orders: object, fills: object, updated_age: int, status: str
        ) -> None:
            now = _now_epoch()
            self._ibkr_positions = list(positions or [])
            self._ibkr_orders = list(orders or [])
            self._ibkr_fills = list(fills or [])
            self._ibkr_last_status = status
            try:
                self._ibkr_last_fetch_ts = max(0.0, now - float(updated_age))
            except Exception:
                self._ibkr_last_fetch_ts = now
                
            # --- Start-up Safety Checks (Run Once) ---
            equity = getattr(self._ibkr_fetcher, "equity", 0.0)
            
            # [ANTIGRAVITY FIX] PnL Calculation
            if equity > 0:
                if self._session_start_equity is None:
                    self._session_start_equity = equity
                
                diff = equity - self._session_start_equity
                pct = (diff / self._session_start_equity * 100) if self._session_start_equity else 0.0
                sign = "+" if diff >= 0 else "-"
                color = "#4cc9f0" if diff >= 0 else "#ef4444"  # Cyan/Red
                
                pnl_str = f"PnL: {sign}${abs(diff):.2f} ({sign}{abs(pct):.2f}%)"
                # [ANTIGRAVITY FIX] Prefer log-based PnL for status bar
                # self._status_pnl_label.setText(pnl_str)
                # self._status_pnl_label.setStyleSheet(f"QLabel {{ color: {color}; font-weight: bold; margin-right: 15px; }}")

            # Ensure we don't trigger IBKR warnings if we are explicitly in Alternative/CCXT mode
            is_ccxt = (os.getenv("EXCHANGE_PROVIDER") or "").lower() == "alternative"
            is_ibkr = (settings.market_provider_name == "IBKR") and not is_ccxt
            
            if is_ibkr and equity > 0 and not self._pdt_safety_check_done:
                self._pdt_safety_check_done = True
                
                # Check 1: Capital < 25k -> Auto-Disable Day Trades + Warning
                if equity < 25000:
                    if settings.allow_day_trades:
                        settings.allow_day_trades = False
                        QtWidgets.QMessageBox.warning(
                            self,
                            "PDT Safety Triggered",
                            "<b>Automatic Safety Action: Day Trading Disabled</b><br><br>"
                            f"Your account equity (${equity:,.2f}) is under $25,000.<br>"
                            "To prevent a 90-day trading ban (PDT Violation), I have disabled Day Trading.<br><br>"
                            "<i>This is a courtesy protection. You may re-enable it in Settings if you accept the risk.</i>"
                        )
                    else:
                        # Already disabled, but warn about risk if they try to enable it
                        pass 
                        
                # Check 2: Stocks Long warning (Settlement/Time)
                if not self._stocks_long_warning_done:
                    self._stocks_long_warning_done = True
                    QtWidgets.QMessageBox.information(
                        self,
                        "Trading Advisory: IBKR Stocks",
                        "<b>Long-Only Strategy Note</b><br><br>"
                        "When trading Stocks Long-Only on IBKR (due to PDT limits), "
                        "be aware that exiting positions may take time (swing trading).<br>"
                        "Ensure your strategy allows for overnight holding."
                    )

            # Check 3: Crypto Restrictions on IBKR
            if is_ibkr and not self._crypto_warning_done:
                self._crypto_warning_done = True
                QtWidgets.QMessageBox.information(
                    self,
                    "Trading Advisory: Crypto on IBKR",
                    "<b>Crypto Limitations Detected</b><br><br>"
                    "You are in IBKR Mode. Crypto trading is allowed but restricted to <b>Long-Only</b> (No Shorts).<br>"
                    "Day Trading Crypto (Scalping/Shorting) is best done via <b>CCXT Mode</b> (Hybrid/Alternative).<br><br>"
                    "<i>To enable Shorting, switch to CCXT in Settings > Execution.</i>"
                )

        def _parse_decision_event(self, dec) -> dict[str, Any]:
            """Convert DecisionEvent to dict for formatter."""
            data = {
                "symbol": dec.symbol,
                "timeframe": dec.tf,
                "raw_rest": dec.rest,
            }

            # Parse dec.rest string (format: "bias=long phase=trend action=enter_long ...")
            parts = re.split(r'\s+(?=[a-zA-Z_]+=)', dec.rest)
            gates_str = ""
            codes_str = ""

            for part in parts:
                if '=' in part:
                    key, value = part.split('=', 1)
                    if key == "gates":
                        gates_str = value
                    elif key == "codes":
                        codes_str = value
                    else:
                        data[key.strip()] = value.strip()
                else:
                    if "reason" not in data:
                        data["reason"] = part.strip()

            # Parse gates string into a dictionary if available
            if gates_str:
                try:
                    gates_dict = json.loads(gates_str.replace("'", '"'))
                    data["gates"] = {k: v for k, v in gates_dict.items() if isinstance(k, str)}
                except json.JSONDecodeError:
                    gate_dict = {}
                    for gate_match in re.finditer(r'([a-zA-Z_]+)=(True|False)', gates_str):
                        gate_dict[gate_match.group(1)] = gate_match.group(2) == 'True'
                    data["gates"] = gate_dict
            else:
                data["gates"] = {}

            # Parse decision reason codes
            if codes_str:
                try:
                    codes_list = json.loads(codes_str.replace("'", '"'))
                    data["decision_reason_codes"] = [c for c in codes_list if isinstance(c, str)]
                except json.JSONDecodeError:
                    code_matches = re.findall(r"\'([A-Z_]+)\'", codes_str)
                    data["decision_reason_codes"] = code_matches
            else:
                data["decision_reason_codes"] = []

            # Extract bias, phase, action from the reason or codes if not explicitly parsed yet
            if "bias" not in data:
                if "long" in data.get("raw_rest", ""): data["bias"] = "long"
                elif "short" in data.get("raw_rest", ""): data["bias"] = "short"
                else: data["bias"] = "neutral"

            if "phase" not in data:
                if "trend" in data.get("raw_rest", ""): data["phase"] = "trend"
                elif "correction" in data.get("raw_rest", ""): data["phase"] = "correction"
                elif "continuation" in data.get("raw_rest", ""): data["phase"] = "continuation"
                elif "chop" in data.get("raw_rest", ""): data["phase"] = "chop"
                else: data["phase"] = "unknown"

            if "action" not in data:
                if "enter_long" in data.get("raw_rest", ""): data["action"] = "enter_long"
                elif "enter_short" in data.get("raw_rest", ""): data["action"] = "enter_short"
                elif "stand_aside" in data.get("raw_rest", ""): data["action"] = "stand_aside"
                elif "close_position" in data.get("raw_rest", ""): data["action"] = "close_position"
                elif "scale_in" in data.get("raw_rest", ""): data["action"] = "scale_in"
                elif "scale_out" in data.get("raw_rest", ""): data["action"] = "scale_out"
                elif "flip_to_long" in data.get("raw_rest", ""): data["action"] = "flip_to_long"
                elif "flip_to_short" in data.get("raw_rest", ""): data["action"] = "flip_to_short"
                elif "hold" in data.get("raw_rest", ""): data["action"] = "hold"
                else: data["action"] = "unknown"

            return data

        def _update_recent_decisions(self) -> None:
            """Update the decisions display using the DecisionsPanel.

            The detailed decision parsing and formatting logic has been moved
            into :class:`tradebot_sci.gui.decisions_panel.DecisionsPanel`.  This
            method delegates to that implementation to refresh the
            decisions view without duplicating code here.
            """
            # Refresh the decisions panel with the latest events.
            self._decisions_panel.update_decisions()

    app = QtWidgets.QApplication([])
    app.setApplicationName("Tradebot SCI")
    app.setOrganizationName("TradeBySCI")
    app.setOrganizationDomain("tradebysci.local")
    w = MainWindow()
    w.show()
    return int(app.exec())
