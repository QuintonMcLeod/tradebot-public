from __future__ import annotations

import argparse
import logging
import os
import re
import json
import sys
import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo
import threading
import shutil
import textwrap
import atexit
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.commentary_prompts import build_commentary_messages
from tradebot_sci.config.loader import load_settings


@dataclass
class BotState:
    profile: str | None = None
    mode: str | None = None
    sabbath_active: bool | None = None
    active_symbol: str | None = None
    last_decision_by_symbol: dict[str, str] | None = None
    last_structure_by_symbol: dict[str, dict] | None = None
    last_selected_candidates: str | None = None
    last_pair_selector: str | None = None
    adviser_commentary: str | None = None
    adviser_last_update_ts: float | None = None
    adviser_last_attempt_ts: float | None = None
    adviser_last_signature: str | None = None
    adviser_in_flight: bool = False
    adviser_enabled: bool = False
    adviser_last_error: str | None = None
    adviser_last_exit_code: int | None = None
    adviser_last_start_ts: float | None = None
    adviser_last_finish_ts: float | None = None
    adviser_backoff_seconds: float = 0.0
    adviser_budget_note: str | None = None
    auto_mode: str | None = None
    prev_readiness_by_symbol: dict[str, float] | None = None
    last_a_plus_event_ts: float | None = None
    last_a_plus_event_symbol: str | None = None
    adviser_last_daily_slot_key: str | None = None
    adviser_last_a_plus_ts: float | None = None


STRUCTURE_RE = re.compile(
    r"\[STRUCTURE\]\s+(?P<symbol>[A-Z0-9]+)\s+selection_score=(?P<score>[-0-9.]+)\s+readiness=(?P<readiness>[-0-9.]+)"
    r"(?:\s+last_gate=(?P<last_gate>[^\\s]+)\s+since_sweep=(?P<since_sweep>[^\\s]+)\s+since_cont=(?P<since_cont>[^\\s]+))?"
    r"\s+\((?P<reason>.*)\)$"
)
SELECT_RE = re.compile(r"\[SELECT\]\s+Active symbol:\s+(?P<symbol>[A-Z0-9]+)\b")
DECISION_RE = re.compile(r"Decision:\s+(?P<symbol>[A-Z0-9]+)\s+(?P<tf>[^|]+)\|\s+(?P<rest>.*)$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

CSI = "\x1b["


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    term = os.getenv("TERM", "")
    if term in ("dumb", ""):
        return False
    return True


def _style(
    text: str,
    *,
    fg: int | None = None,
    bg: int | None = None,
    bold: bool = False,
    dim: bool = False,
    enable: bool = True,
) -> str:
    if not enable:
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if fg is not None:
        codes.append(f"38;5;{fg}")
    if bg is not None:
        codes.append(f"48;5;{bg}")
    if not codes:
        return text
    return f"{CSI}{';'.join(codes)}m{text}{CSI}0m"


def _term_width(default: int = 100) -> int:
    try:
        return max(80, shutil.get_terminal_size((default, 24)).columns)
    except Exception:
        return default


def _box(title: str, body_lines: list[str], *, width: int, color_on: bool) -> str:
    inner = max(10, width - 2)
    t = f" {title} "
    t = t[: max(0, inner - 2)]
    top = "╭" + "─" * ((inner - len(t)) // 2) + t + "─" * (inner - ((inner - len(t)) // 2) - len(t)) + "╮"
    mid: list[str] = []
    for line in body_lines:
        visible = ANSI_RE.sub("", line)
        if len(visible) > inner:
            line = visible[:inner]
            visible = line
        pad = max(0, inner - len(visible))
        mid.append(f"│{line}{' ' * pad}│")
    bot = "╰" + "─" * inner + "╯"
    if not color_on:
        return "\n".join([top, *mid, bot])
    return "\n".join(
        [
            _style(top, fg=39, dim=True, enable=True),
            *[_style(l, fg=250, enable=True) for l in mid],
            _style(bot, fg=39, dim=True, enable=True),
        ]
    )


def _bar(value: float, *, width: int = 18) -> str:
    v = max(0.0, min(1.2, float(value)))
    fill = int(round((v / 1.2) * width))
    fill = max(0, min(width, fill))
    return "█" * fill + "░" * (width - fill)


def _wrap_lines(text: str, *, width: int) -> list[str]:
    if not text.strip():
        return [""]
    out: list[str] = []
    for raw in text.splitlines():
        raw = raw.rstrip()
        if not raw:
            out.append("")
            continue
        out.extend(textwrap.wrap(raw, width=width, replace_whitespace=False, drop_whitespace=False))
    return out or [""]


class _SmoothScreen:
    def __init__(self) -> None:
        self._last_lines: list[str] = []
        self._cursor_hidden = False

    def _hide_cursor(self) -> None:
        if self._cursor_hidden:
            return
        sys.stdout.write(f"{CSI}?25l")
        self._cursor_hidden = True

    def _show_cursor(self) -> None:
        if not self._cursor_hidden:
            return
        sys.stdout.write(f"{CSI}?25h")
        self._cursor_hidden = False

    def close(self) -> None:
        self._show_cursor()
        sys.stdout.flush()

    def draw(self, frame: str) -> None:
        self._hide_cursor()
        lines = frame.splitlines()
        max_lines = max(len(lines), len(self._last_lines))
        for i in range(max_lines):
            new = lines[i] if i < len(lines) else ""
            old = self._last_lines[i] if i < len(self._last_lines) else None
            if old is not None and new == old:
                continue
            # Move cursor and rewrite only changed lines.
            sys.stdout.write(f"{CSI}{i+1};1H{CSI}2K{new}")
        self._last_lines = lines
        sys.stdout.flush()


def _setup_commentary_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger("tradebot_commentary")
    if logger.handlers:
        return logger
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _log_event(logger: logging.Logger, event: str, payload: dict) -> None:
    try:
        data = {"ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", "event": event, **payload}
        logger.info(json.dumps(data, ensure_ascii=True))
    except Exception:
        return


def _log_payloads(logger: logging.Logger, request: dict | None, response: dict | None) -> None:
    if (os.getenv("COMMENTARY_LOG_PAYLOADS") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    def _safe_dump(data: dict | None) -> str:
        if data is None:
            return ""
        try:
            return json.dumps(data, ensure_ascii=True, sort_keys=True)
        except Exception:
            return ""

    def _truncate(value: str, limit: int = 20000) -> str:
        if len(value) <= limit:
            return value
        return value[:limit] + f"...(truncated,{len(value)} bytes)"

    req_text = _truncate(_safe_dump(request))
    resp_text = _truncate(_safe_dump(response))
    if req_text:
        _log_event(logger, "commentary_request", {"payload": req_text})
    if resp_text:
        _log_event(logger, "commentary_response", {"payload": resp_text})


def main() -> int:
    parser = argparse.ArgumentParser(description="Human-friendly commentary view for tradebot logs.")
    parser.add_argument("--log", default=os.getenv("TRADEBOT_LOG", "logs/tradebot.log"))
    parser.add_argument("--follow", action="store_true", help="Follow the log (tail -F style).")
    parser.add_argument("--interval", type=float, default=5.0, help="Refresh interval (seconds).")
    parser.add_argument(
        "--llm",
        default=os.getenv("COMMENTARY_LLM", "internal"),
        choices=["off", "internal", "adviser"],
        help="Optional LLM commentary source (off|internal).",
    )
    parser.add_argument(
        "--llm-min-seconds",
        type=float,
        default=float(os.getenv("COMMENTARY_LLM_MIN_SECONDS", "300")),
        help="Minimum seconds between LLM commentary refreshes.",
    )
    parser.add_argument(
        "--llm-policy",
        default=os.getenv("COMMENTARY_LLM_POLICY", "a_plus_or_4x"),
        choices=["interval", "a_plus_only", "a_plus_or_4x"],
        help="When to call commentary: interval (min-seconds), a_plus_only, or a_plus_or_4x (A+ plus 4/day fallback).",
    )
    parser.add_argument(
        "--llm-tz",
        default=os.getenv("COMMENTARY_LLM_TZ", "America/New_York"),
        help="Timezone for daily slots (IANA name, e.g. America/New_York).",
    )
    parser.add_argument(
        "--llm-daily-slots",
        default=os.getenv("COMMENTARY_LLM_DAILY_SLOTS", "09:00,12:00,18:00,22:00"),
        help="Comma-separated daily slot times (HH:MM) used when policy is a_plus_or_4x.",
    )
    parser.add_argument(
        "--llm-max-calls-per-day",
        type=int,
        default=int(os.getenv("COMMENTARY_LLM_MAX_CALLS_PER_DAY", "250")),
        help="Hard cap on commentary calls per day across all commentary panes (0 = unlimited).",
    )
    parser.add_argument(
        "--llm-budget-path",
        default=os.getenv("COMMENTARY_LLM_BUDGET_PATH", "/tmp/tradebot_sci_commentary_budget.json"),
        help="Path to shared JSON budget file for cross-process commentary call limiting.",
    )
    parser.add_argument(
        "--commentary-log",
        default=os.getenv("COMMENTARY_LOG", "logs/commentary.log"),
        help="Path to commentary troubleshooting log.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=float(os.getenv("COMMENTARY_LLM_TIMEOUT_SECONDS", "90")),
        help="Timeout for a single commentary call (seconds).",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color rendering.")
    args = parser.parse_args()

    path = Path(args.log)
    commentary_log = _setup_commentary_logger(Path(args.commentary_log))
    state = BotState(last_decision_by_symbol={}, last_structure_by_symbol={}, prev_readiness_by_symbol={})
    llm_mode = (args.llm or "").strip().lower()
    if llm_mode == "adviser":
        llm_mode = "internal"
    state.adviser_enabled = llm_mode == "internal"
    color_on = _supports_color() and not args.no_color
    screen = _SmoothScreen()
    atexit.register(screen.close)

    if not path.exists():
        print(f"[COMMENTARY] waiting: log not found at {path}", file=sys.stderr)
        if not args.follow:
            return 2

    _log_event(
        commentary_log,
        "startup",
        {
            "log_path": str(path),
            "llm_mode": llm_mode,
            "policy": args.llm_policy,
            "min_seconds": args.llm_min_seconds,
            "daily_slots": args.llm_daily_slots,
            "max_calls_per_day": args.llm_max_calls_per_day,
            "budget_path": str(args.llm_budget_path),
            "tz": args.llm_tz,
        },
    )

    last_inode = None
    last_size = 0
    buffer: deque[str] = deque(maxlen=200)

    while True:
        try:
            if path.exists():
                stat = path.stat()
                if last_inode is None or stat.st_ino != last_inode or stat.st_size < last_size:
                    last_inode = stat.st_ino
                    last_size = 0
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    if last_size:
                        f.seek(last_size)
                    chunk = f.read()
                    last_size = f.tell()
                if chunk:
                    for line in chunk.splitlines():
                        buffer.append(line)
                        _ingest_line(state, line)
            if llm_mode == "internal":
                _maybe_update_adviser_commentary(
                    state,
                    min_seconds=args.llm_min_seconds,
                    max_calls_per_day=args.llm_max_calls_per_day,
                    budget_path=Path(args.llm_budget_path),
                    timeout_seconds=args.llm_timeout_seconds,
                    policy=args.llm_policy,
                    tz_name=args.llm_tz,
                    daily_slots=_parse_daily_slots(args.llm_daily_slots),
                    logger=commentary_log,
                )
            frame = _render(state, color_on=color_on)
            screen.draw(frame)
            if not args.follow:
                return 0
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


def _ingest_line(state: BotState, line: str) -> None:
    if "[AUTO_SCHEDULE]" in line:
        state.auto_mode = _after("mode=", line)
        state.mode = state.auto_mode
        return
    if "[SABBATH]" in line and "sabbath_active=" in line:
        val = _after("sabbath_active=", line)
        if val is not None:
            state.sabbath_active = val.lower().startswith("t")
        return
    if "[STATE] structure_score_threshold=" in line and "profile=" in line:
        state.profile = _after("profile=", line)
        return
    if "[PAIR_SELECTOR]" in line:
        state.last_pair_selector = line.strip()
        return

    m = STRUCTURE_RE.search(line)
    if m:
        sym = m.group("symbol")
        readiness = float(m.group("readiness"))
        prev_map = state.prev_readiness_by_symbol
        if prev_map is not None:
            prev = float(prev_map.get(sym, 0.0))
            prev_map[sym] = readiness
            if prev < 1.0 and readiness >= 1.0:
                state.last_a_plus_event_ts = time.time()
                state.last_a_plus_event_symbol = sym
        state.last_structure_by_symbol[sym] = {
            "selection_score": float(m.group("score")),
            "readiness": readiness,
            "reason": m.group("reason"),
            "last_gate": m.groupdict().get("last_gate"),
            "since_sweep": m.groupdict().get("since_sweep"),
            "since_cont": m.groupdict().get("since_cont"),
        }
        return

    m = SELECT_RE.search(line)
    if m:
        state.active_symbol = m.group("symbol")
        return

    m = DECISION_RE.search(line)
    if m:
        sym = m.group("symbol")
        state.last_decision_by_symbol[sym] = m.group("rest").strip()


def _render(state: BotState, *, color_on: bool) -> str:
    out: list[str] = []
    width = _term_width(110)
    title = _style(" TRADEBOT SCI ", fg=231, bg=24, bold=True, enable=color_on)
    subtitle = _style(" ICC Dashboard ", fg=231, bg=237, bold=True, enable=color_on)
    out.append(title + subtitle)

    profile = state.profile or "unknown"
    mode = state.mode or "unknown"
    sym = state.active_symbol or "<none>"
    sabbath = state.sabbath_active
    sabbath_txt = "unknown" if sabbath is None else ("ACTIVE" if sabbath else "off")
    sabbath_fg = 208 if sabbath else 70
    if sabbath is None:
        sabbath_fg = 244
    header_left = f"profile={profile}  mode={mode}"
    header_right = f"sabbath={sabbath_txt}  active={sym}"
    gap = max(1, width - len(header_left) - len(header_right) - 1)
    out.append(
        _style(header_left, fg=252, bold=True, enable=color_on)
        + " " * gap
        + _style(header_right, fg=sabbath_fg, bold=True, enable=color_on)
    )
    if state.last_pair_selector:
        out.append(_style("pair_selector: ", fg=245, bold=True, enable=color_on) + f"{state.last_pair_selector}")
    out.append(_style("─" * width, fg=238, enable=color_on))

    # Show top 3 readiness situations.
    items = list((state.last_structure_by_symbol or {}).items())
    items.sort(key=lambda kv: (kv[1].get("readiness", 0.0), kv[1].get("selection_score", 0.0)), reverse=True)
    readiness_lines: list[str] = []
    if not items:
        readiness_lines.append("waiting: no structure data yet (tailing log...)")
    top_items = items[:10]
    page_size = 3
    pages = max(1, (len(top_items) + page_size - 1) // page_size)
    page = int(time.time() // 30) % pages
    start = page * page_size
    shown = top_items[start : start + page_size]
    for sym, info in shown:
        readiness = float(info.get("readiness", 0.0) or 0.0)
        sel = float(info.get("selection_score", 0.0) or 0.0)
        bar = _bar(readiness, width=18)
        readiness_fg = 70 if readiness >= 1.0 else 178 if readiness >= 0.5 else 244
        bar_txt = _style(bar, fg=readiness_fg, bold=True, enable=color_on)
        sym_txt = _style(sym, fg=81, bold=True, enable=color_on)
        readiness_lines.append(f"{sym_txt}  {bar_txt}  readiness={readiness:.2f}  score={sel:.3f}")
        reason = (info.get("reason", "") or "").strip()
        if reason:
            for w in _wrap_lines(f"reason: {reason}", width=width - 4):
                readiness_lines.append(w)
        if info.get("last_gate") or info.get("since_sweep") or info.get("since_cont"):
            readiness_lines.append(
                f"telemetry: last_gate={info.get('last_gate')} since_sweep={info.get('since_sweep')} since_cont={info.get('since_cont')}"
            )
        readiness_lines.append(f"expectation: {_expectation(sym, readiness, state)}")
        readiness_lines.append("")
    readiness_lines = [ln[: width - 2] for ln in readiness_lines]
    if top_items:
        end = min(start + page_size, len(top_items))
        title = f"TOP READINESS (ICC)  [{start+1}-{end} of {len(top_items)}]  rotate=30s"
    else:
        title = "TOP READINESS (ICC)"
    out.append(_box(title, readiness_lines, width=width, color_on=color_on))
    out.append("")

    comm_lines: list[str] = []
    if state.adviser_in_flight:
        comm_lines.append(_style("updating…", fg=178, bold=True, enable=color_on))
        if state.adviser_last_start_ts:
            elapsed = max(0.0, time.time() - state.adviser_last_start_ts)
            comm_lines.append(_style(f"elapsed: {elapsed:.0f}s", fg=244, dim=True, enable=color_on))
        comm_lines.append("")
    if state.adviser_commentary:
        comm_lines.extend(_wrap_lines(state.adviser_commentary.strip(), width=width - 4)[:14])
    else:
        if state.adviser_enabled:
            comm_lines.append(_style("waiting for commentary…", fg=244, dim=True, enable=color_on))
            if state.adviser_last_error and not state.adviser_in_flight:
                comm_lines.append(_style(f"last_error: {state.adviser_last_error}", fg=203, dim=True, enable=color_on))
            if state.adviser_budget_note and not state.adviser_in_flight:
                comm_lines.append(_style(state.adviser_budget_note, fg=178, dim=True, enable=color_on))
        else:
            comm_lines.append(_style("disabled (set COMMENTARY_LLM=internal)", fg=244, dim=True, enable=color_on))
    if state.adviser_last_update_ts:
        age = max(0.0, time.time() - state.adviser_last_update_ts)
        age_fg = 70 if age < 90 else 178 if age < 240 else 203
        comm_lines.append("")
        comm_lines.append(_style(f"last_good_update: {age:.0f}s ago", fg=age_fg, bold=True, enable=color_on))
        if state.adviser_budget_note and not state.adviser_in_flight:
            comm_lines.append(_style(state.adviser_budget_note, fg=244, dim=True, enable=color_on))
    comm_lines = [ln[: width - 2] for ln in comm_lines]
    out.append(_box("AI COMMENTARY", comm_lines, width=width, color_on=color_on))
    out.append("")

    dec_lines: list[str] = []
    last = list((state.last_decision_by_symbol or {}).items())[-6:]
    if not last:
        dec_lines.append("waiting: no decisions logged yet")
    for sym, rest in last:
        sym_txt = _style(sym, fg=81, bold=True, enable=color_on)
        rest_wrapped = _wrap_lines(rest, width=width - 6)
        first = rest_wrapped[0] if rest_wrapped else ""
        dec_lines.append(f"{sym_txt}: {first}")
        for cont in rest_wrapped[1:2]:
            dec_lines.append(f"  {cont}")
    dec_lines = [ln[: width - 2] for ln in dec_lines]
    out.append(_box("LAST DECISIONS", dec_lines, width=width, color_on=color_on))
    out.append("")

    left_box, right_box = _markets_boxes(state, width=width, color_on=color_on)
    out.extend(_merge_boxes_side_by_side(left_box, right_box, width=width))
    return "\n".join(out) + "\n"


def _markets_boxes(state: BotState, *, width: int, color_on: bool) -> tuple[str, str]:
    open_markets: list[str] = []
    closed_markets: list[str] = []

    mode = (state.auto_mode or state.mode or "").lower()
    sabbath = state.sabbath_active is True
    sabbath_note = " (entries blocked)" if sabbath else ""

    # Minimal + safe: reflect what the bot is actively monitoring via auto-schedule mode.
    if mode == "equity":
        open_markets = [f"US Equities{sabbath_note}"]
        closed_markets = ["Crypto", "Forex", "Futures (stubbed)"]
    elif mode == "crypto":
        open_markets = [f"Crypto{sabbath_note}"]
        closed_markets = ["US Equities", "Forex", "Futures (stubbed)"]
    else:
        open_markets = [f"US Equities{sabbath_note}", f"Crypto{sabbath_note}", f"Forex{sabbath_note}"]
        closed_markets = ["Futures (stubbed)"]

    if state.sabbath_active is None:
        open_markets.append("Sabbath: unknown")
    elif sabbath:
        open_markets.append(_style("Sabbath ACTIVE: monitoring only", fg=208, bold=True, enable=color_on))

    half = max(40, (width - 1) // 2)
    left = _box("OPEN MARKETS", open_markets or ["(none)"], width=half, color_on=color_on)
    right = _box("CLOSED MARKETS", closed_markets or ["(none)"], width=width - half - 1, color_on=color_on)
    return left, right


def _merge_boxes_side_by_side(left: str, right: str, *, width: int) -> list[str]:
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    n = max(len(left_lines), len(right_lines))
    left_lines += [""] * (n - len(left_lines))
    right_lines += [""] * (n - len(right_lines))
    merged: list[str] = []
    for a, b in zip(left_lines, right_lines):
        merged.append(f"{a} {b}".rstrip()[:width])
    return merged


def _expectation(symbol: str, readiness: float, state: BotState) -> str:
    if state.sabbath_active:
        return "Sabbath gate is active: no new entries until the window ends."
    if readiness >= 1.0:
        return "ICC sweep+continuation confirmed. Next: entry evaluation + risk cap + venue check."
    if readiness >= 0.5:
        return "Sweep confirmed. Next: wait for continuation candle/structure flip confirmation."
    return "Not ready. Next: wait for a real correction/sweep against the trend."


def _after(prefix: str, line: str) -> str | None:
    idx = line.find(prefix)
    if idx == -1:
        return None
    tail = line[idx + len(prefix) :].strip()
    # Stop at whitespace or punctuation we commonly see.
    for sep in (" ", "]", ","):
        j = tail.find(sep)
        if j != -1:
            tail = tail[:j]
    return tail.strip("'\"")


def _parse_daily_slots(raw: str) -> list[tuple[int, int]]:
    slots: list[tuple[int, int]] = []
    for part in (raw or "").split(","):
        p = part.strip()
        if not p:
            continue
        if ":" not in p:
            continue
        hh_s, mm_s = p.split(":", 1)
        try:
            hh = int(hh_s)
            mm = int(mm_s)
        except Exception:
            continue
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            slots.append((hh, mm))
    return sorted(set(slots))


def _current_daily_slot_key(now_dt: datetime, *, slots: list[tuple[int, int]]) -> str | None:
    if not slots:
        return None
    eligible = [(h, m) for (h, m) in slots if (h, m) <= (now_dt.hour, now_dt.minute)]
    if not eligible:
        return None
    h, m = max(eligible)
    return f"{now_dt.date().isoformat()}#{h:02d}:{m:02d}"


def _maybe_update_adviser_commentary(
    state: BotState,
    *,
    min_seconds: float,
    max_calls_per_day: int,
    budget_path: Path,
    timeout_seconds: float,
    policy: str,
    tz_name: str,
    daily_slots: list[tuple[int, int]],
    logger: logging.Logger,
) -> None:
    if state.adviser_in_flight:
        return
    if state.sabbath_active:
        state.adviser_commentary = "Sabbath window active — no play-by-play. Monitoring only."
        state.adviser_last_error = None
        state.adviser_budget_note = None
        _log_event(logger, "skip_sabbath", {"reason": "sabbath_active"})
        return

    # Safety clamp: avoid accidental spam even if a user misconfigures values.
    if min_seconds < 60:
        min_seconds = 60

    signature = _state_signature(state)
    now = time.time()
    # Backoff (errors like billing/quota/rate-limit) overrides the baseline min-seconds.
    if state.adviser_last_attempt_ts and state.adviser_backoff_seconds > 0:
        since = now - state.adviser_last_attempt_ts
        remaining = state.adviser_backoff_seconds - since
        if remaining > 0.5:
            secs_total = int(max(1, math.ceil(remaining)))
            mins = int(secs_total // 60)
            secs = int(secs_total % 60)
            state.adviser_budget_note = f"cooldown: retry in {mins}m{secs:02d}s"
            _log_event(logger, "skip_backoff", {"remaining_seconds": secs_total})
            return
        if state.adviser_budget_note and state.adviser_budget_note.startswith("cooldown:"):
            state.adviser_budget_note = None

    if state.adviser_last_attempt_ts and now - state.adviser_last_attempt_ts < min_seconds:
        _log_event(
            logger,
            "skip_min_seconds",
            {"since_last_attempt": round(now - state.adviser_last_attempt_ts, 1), "min_seconds": min_seconds},
        )
        return
    if state.adviser_last_signature == signature and state.adviser_last_update_ts:
        if now - state.adviser_last_update_ts < min_seconds:
            _log_event(
                logger,
                "skip_signature_cooldown",
                {"since_last_update": round(now - state.adviser_last_update_ts, 1), "min_seconds": min_seconds},
            )
            return

    policy = (policy or "interval").strip().lower()
    if policy not in {"interval", "a_plus_only", "a_plus_or_4x"}:
        policy = "interval"

    due_reason: str | None = None
    if policy == "interval":
        due_reason = "interval"
    else:
        a_plus_ts = state.last_a_plus_event_ts
        last_handled = state.adviser_last_a_plus_ts or 0.0
        if a_plus_ts and a_plus_ts > last_handled:
            due_reason = "a_plus"
        elif policy == "a_plus_or_4x":
            try:
                now_dt = datetime.now(ZoneInfo(tz_name or "America/New_York"))
            except Exception:
                now_dt = datetime.now()
            slot_key = _current_daily_slot_key(now_dt, slots=daily_slots)
            if slot_key and slot_key != state.adviser_last_daily_slot_key:
                due_reason = "daily"
            else:
                state.adviser_budget_note = "commentary: waiting (A+ trigger or next daily slot)"
        else:
            state.adviser_budget_note = "commentary: waiting for A+ continuation (readiness=1.00)"

    if due_reason is None:
        _log_event(logger, "skip_not_due", {"policy": policy, "note": state.adviser_budget_note})
        return

    if max_calls_per_day > 0:
        ok, note = _llm_budget_try_consume(budget_path, limit=max_calls_per_day)
        if not ok:
            state.adviser_budget_note = note
            _log_event(logger, "skip_budget", {"note": note})
            return
        state.adviser_budget_note = note
    else:
        state.adviser_budget_note = None

    _log_event(logger, "commentary_due", {"reason": due_reason, "policy": policy})
    state.adviser_in_flight = True
    state.adviser_last_error = None
    state.adviser_last_exit_code = None
    state.adviser_last_start_ts = time.time()
    state.adviser_last_finish_ts = None

    def worker() -> None:
        request_payload: dict | None = None
        response_payload: dict | None = None
        try:
            prompt = _build_adviser_prompt(state)
            settings = load_settings().ai
            if timeout_seconds > 0:
                settings = settings.model_copy(update={"timeout_seconds": int(timeout_seconds)})
            client = TradeSciAIClient(settings)
            messages = build_commentary_messages(prompt)
            commentary = client.generate_text(messages)
            request_payload = getattr(client, "last_request_payload", None)
            response_payload = getattr(client, "last_response_json", None)
            _log_payloads(logger, request_payload, response_payload)
            stdout = commentary
            stderr = ""
            state.adviser_last_exit_code = 0 if commentary else 1
            if commentary and commentary.strip():
                state.adviser_commentary = commentary.strip()
                state.adviser_last_update_ts = time.time()
                state.adviser_last_signature = signature
                _log_event(
                    logger,
                    "commentary_success",
                    {"reason": due_reason, "chars": len(state.adviser_commentary)},
                )
                if due_reason == "daily":
                    try:
                        now_dt = datetime.now(ZoneInfo(tz_name or "America/New_York"))
                    except Exception:
                        now_dt = datetime.now()
                    slot_key = _current_daily_slot_key(now_dt, slots=daily_slots)
                    if slot_key:
                        state.adviser_last_daily_slot_key = slot_key
                elif due_reason == "a_plus":
                    state.adviser_last_a_plus_ts = state.last_a_plus_event_ts or time.time()
                state.adviser_backoff_seconds = 0.0
                state.adviser_budget_note = None
            else:
                # Don't blank the pane; keep last good commentary if we have one.
                if not stdout:
                    state.adviser_last_error = "empty commentary response from provider"
                else:
                    state.adviser_last_error = "no extractable commentary from provider"
            if state.adviser_last_exit_code and not state.adviser_last_error:
                state.adviser_last_error = "commentary provider returned empty response"
            if state.adviser_last_error:
                state.adviser_backoff_seconds = _next_backoff_seconds(
                    prev=state.adviser_backoff_seconds,
                    error_text=f"{stdout}\n{stderr}",
                )
                _log_event(
                    logger,
                    "commentary_error",
                    {"error": state.adviser_last_error, "backoff_seconds": state.adviser_backoff_seconds},
                )
        except Exception as exc:
            # Keep last good commentary.
            state.adviser_last_error = f"{type(exc).__name__}: {exc}"[:200]
            state.adviser_backoff_seconds = _next_backoff_seconds(prev=state.adviser_backoff_seconds, error_text=str(exc))
            _log_event(
                logger,
                "commentary_exception",
                {"error": state.adviser_last_error, "backoff_seconds": state.adviser_backoff_seconds},
            )
        finally:
            _log_payloads(logger, request_payload, response_payload)
            state.adviser_last_attempt_ts = time.time()
            state.adviser_last_finish_ts = time.time()
            state.adviser_in_flight = False

    threading.Thread(target=worker, daemon=True).start()


def _state_signature(state: BotState) -> str:
    items = list((state.last_structure_by_symbol or {}).items())
    items.sort(key=lambda kv: (kv[1].get("readiness", 0.0), kv[1].get("selection_score", 0.0)), reverse=True)
    top = [(sym, round(info.get("readiness", 0.0), 2)) for sym, info in items[:3]]
    active = state.active_symbol or ""
    active_dec = (state.last_decision_by_symbol or {}).get(active) or ""
    return json.dumps(
        {
            "profile": state.profile,
            "mode": state.mode,
            "sabbath": state.sabbath_active,
            "active": active,
            "top": top,
            "pair": state.last_pair_selector,
            "active_dec": active_dec[:120],
        },
        sort_keys=True,
    )


def _build_adviser_prompt(state: BotState) -> str:
    items = list((state.last_structure_by_symbol or {}).items())
    items.sort(key=lambda kv: (kv[1].get("readiness", 0.0), kv[1].get("selection_score", 0.0)), reverse=True)
    top = items[:10]
    watch = [sym for sym, info in top if info.get("readiness", 0.0) >= 0.8][:5]
    active = state.active_symbol or "none"
    active_dec = (state.last_decision_by_symbol or {}).get(active) or "none"
    pair = state.last_pair_selector or "none"
    readiness_lines: list[str] = []
    for sym, info in top:
        reason = (info.get("reason", "") or "").replace("\n", " ")
        if len(reason) > 160:
            reason = reason[:157].rstrip() + "…"
        readiness_lines.append(
            f"{sym:>6}  ready={info.get('readiness', 0.0):0.2f}  score={info.get('selection_score', 0.0):0.3f}  reason={reason or '-'}"
        )

    instructions = (
        "You are an energetic ICC coach giving live play-by-play for a trading dashboard.\n"
        "Write like a person (not like a system log summary). Avoid reading timestamps/config back to the user.\n"
        "Use Trade By SCI-style phrasing: direct, confident, concrete. No hedging, no generic filler.\n"
        "Do not mention missing context, limitations, or that you are inferring.\n"
        "Treat the decision codes as internal tradebot concepts and explain them confidently in plain English.\n"
        "Goal: twice as long and more detailed than a short recap (aim ~220-350 words).\n\n"
        "Must include:\n"
        "1) A play-by-play narrative of what the bot is doing right now and why.\n"
        "2) A 'What I'm watching next' section with 3-6 bullets including speculative/conditional predictions.\n"
        "3) If any symbols look close to an A+ continuation, explicitly say so and what would likely be needed.\n"
        "4) Keep it encouraging and clear.\n"
    )

    parts: list[str] = [instructions]
    parts.append(
        f"Context: profile={state.profile} mode={state.mode} sabbath_active={state.sabbath_active} active={active}"
    )
    if pair:
        parts.append(f"Pair selector status: {pair}")
    if watch:
        parts.append("High-readiness watchlist (ready>=0.80): " + ", ".join(watch))
    if readiness_lines:
        parts.append("Readiness table (top 10):\n" + "\n".join(readiness_lines))
    if active_dec and active_dec != "none":
        parts.append(f"Last decision for active symbol: {active_dec}")
    return "\n\n".join(parts)


def _llm_today_key() -> str:
    # Local day is good enough for budgeting; keeps behavior simple & deterministic.
    return time.strftime("%Y-%m-%d", time.localtime())


def _llm_budget_try_consume(path: Path, *, limit: int) -> tuple[bool, str | None]:
    """
    Cross-process budget shared by all commentary panes.
    Returns (ok_to_call, note_for_ui).
    """
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover
        # If we can't lock, fail open but at least show a note to the user.
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
                    remaining = 0
                    note = f"budget: {calls}/{limit} calls today (paused)"
                    # Keep file up to date with the current day.
                    data = {"day": day, "calls": calls, "limit": limit, "updated_ts": time.time()}
                    f.seek(0)
                    f.truncate(0)
                    f.write(json.dumps(data, sort_keys=True))
                    f.flush()
                    os.fsync(f.fileno())
                    return False, note
                calls += 1
                remaining = max(0, limit - calls)
                data = {"day": day, "calls": calls, "limit": limit, "updated_ts": time.time()}
                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, sort_keys=True))
                f.flush()
                os.fsync(f.fileno())
                note = f"budget: {calls}/{limit} calls today (remaining {remaining})"
                return True, note
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        # Fail open but show a note so the user knows budget enforcement is degraded.
        return True, f"budget: unavailable ({type(exc).__name__})"


def _next_backoff_seconds(*, prev: float, error_text: str) -> float:
    text = (error_text or "").lower()
    # Fatal-ish: don't hammer the provider when we know it won't work.
    if "insufficient balance" in text or "402" in text:
        return max(prev, 3600.0)
    if "rate limit" in text or "too many request" in text or "429" in text:
        return max(prev, 900.0)
    # Soft backoff on generic failures.
    if prev <= 0:
        return 60.0
    return min(3600.0, max(60.0, prev * 2.0))


if __name__ == "__main__":
    raise SystemExit(main())
