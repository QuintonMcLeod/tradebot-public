from __future__ import annotations

import argparse
import atexit
import logging
import os
import random
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CSI = "\x1b["
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

STRUCTURE_RE = re.compile(r"\[STRUCTURE\]\s+(?P<symbol>[A-Z0-9]+)\s+(?P<fields>.*)")
SELECT_RE = re.compile(r"\[SELECT\]\s+Active symbol:\s+(?P<symbol>[A-Z0-9]+)\s+\(")
DECISION_ACTION_RE = re.compile(r"Decision:\s+(?P<symbol>[A-Z0-9]+)\s+.*?\\baction=(?P<action>[a-z_]+)\\b")


@dataclass
class State:
    active_symbol: str | None = None
    last_action_by_symbol: dict[str, str] | None = None
    structure_by_symbol: dict[str, dict] | None = None
    # Stabilized y-axis (hi, lo) per symbol, updated only when a bar closes.
    scale_by_symbol: dict[str, tuple[float, float]] | None = None
    scale_anchor_epoch_by_symbol: dict[str, float] | None = None
    # Prevent symbol swapping within a rotation bucket when top3 ordering changes.
    rotation_bucket_start: float | None = None
    rotation_symbols: list[str] | None = None


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


def _try_import_rich() -> dict[str, Any] | None:
    try:
        from rich.box import ROUNDED  # type: ignore
        from rich.console import Console  # type: ignore
        from rich.panel import Panel  # type: ignore
        from rich.table import Table  # type: ignore
        from rich.text import Text  # type: ignore

        return {"Console": Console, "Panel": Panel, "ROUNDED": ROUNDED, "Table": Table, "Text": Text}
    except Exception:
        return None


def _term_size(default_cols: int = 100, default_rows: int = 24) -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size((default_cols, default_rows))
        return max(80, size.columns), max(18, size.lines)
    except Exception:
        return default_cols, default_rows


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
            sys.stdout.write(f"{CSI}{i+1};1H{CSI}2K{new}")
        self._last_lines = lines
        sys.stdout.flush()


def _fit_to_rows(frame: str, *, rows: int) -> str:
    """
    Keep the rendered frame within the visible terminal height.

    If we ever write past the last visible row, many terminals/tmux will scroll,
    which looks like the chart "bounces" up/down. We avoid that by hard-capping
    to `rows` and padding with blanks so the line count stays constant.
    """
    if rows <= 0:
        return frame
    lines = frame.splitlines()
    if len(lines) > rows:
        lines = lines[:rows]
    elif len(lines) < rows:
        lines = lines + [""] * (rows - len(lines))
    return "\n".join(lines)


def _ingest_line(state: State, line: str) -> None:
    m = STRUCTURE_RE.search(line)
    if m:
        sym = m.group("symbol")
        fields = m.group("fields")
        reason = None
        if "(" in fields and fields.rstrip().endswith(")"):
            fields, reason_part = fields.split("(", 1)
            reason = reason_part.rstrip(")").strip() or None
        parsed = dict(re.findall(r"([a-z_]+)=([^\s]+)", fields.strip()))
        state.structure_by_symbol[sym] = {
            "selection_score": float(parsed.get("selection_score", 0.0)),
            "readiness": float(parsed.get("readiness", 0.0)),
            "last_gate": parsed.get("last_gate"),
            "since_sweep": parsed.get("since_sweep"),
            "since_cont": parsed.get("since_cont"),
            "reason": reason,
        }
    m = SELECT_RE.search(line)
    if m:
        state.active_symbol = m.group("symbol")
    m = DECISION_ACTION_RE.search(line)
    if m:
        state.last_action_by_symbol[m.group("symbol")] = m.group("action")


def _top_symbols(state: State, n: int) -> list[str]:
    items = list((state.structure_by_symbol or {}).items())
    items.sort(key=lambda kv: (kv[1].get("readiness", 0.0), kv[1].get("selection_score", 0.0)), reverse=True)
    return [sym for sym, _ in items[:n]]


def _pick_symbol(state: State, *, rotate_seconds: int) -> tuple[str | None, str]:
    active = state.active_symbol
    if active:
        action = (state.last_action_by_symbol or {}).get(active, "")
        if action and action != "stand_aside":
            return active, f"active_symbol locked (action={action})"
    top3 = _top_symbols(state, 3)
    if not top3:
        return active, "no structure yet; showing active_symbol"
    now = time.time()
    bucket_start = (now // rotate_seconds) * rotate_seconds
    if state.rotation_bucket_start != bucket_start:
        state.rotation_bucket_start = bucket_start
        state.rotation_symbols = list(top3)
    symbols = state.rotation_symbols or list(top3)
    idx = int((now - bucket_start) // rotate_seconds) % len(symbols)
    return symbols[idx], "rotating top3 (no active trade)"


def _to_epoch(dt) -> float | None:  # type: ignore[no-untyped-def]
    if dt is None:
        return None
    # ib_insync BarData.date is often a datetime.
    try:
        return float(dt.timestamp())
    except Exception:
        pass
    try:
        # Sometimes it's a string like "20251216  13:20:00"
        s = str(dt)
        if s.isdigit():
            return float(s)
        # Best-effort parse: keep it simple; if fails, return None.
        import datetime as _dt

        for fmt in ("%Y%m%d  %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
            try:
                return _dt.datetime.strptime(s, fmt).timestamp()
            except Exception:
                continue
    except Exception:
        return None
    return None


def _render_candles(bars, *, width: int, height: int, color_on: bool) -> list[str]:  # type: ignore[no-untyped-def]
    if not bars:
        return ["(no bars yet)"]

    # Reserve space for right-side price labels / last-price tag.
    axis_w = 10
    plot_w = max(20, width - axis_w)

    # Render oldest -> newest left-to-right (sort defensively; some sources return newest-first).
    max_candles = max(10, min(plot_w - 2, 80))
    ordered = sorted(
        list(bars),
        key=lambda b: (_to_epoch(getattr(b, "date", None)) or 0.0),
    )
    vis = ordered[-max_candles:]
    # Ensure newest bar is far right.
    if len(vis) >= 2:
        t0 = _to_epoch(getattr(vis[0], "date", None)) or 0.0
        t1 = _to_epoch(getattr(vis[-1], "date", None)) or 0.0
        if t0 > t1:
            vis = list(reversed(vis))
    highs = [float(b.high) for b in vis]
    lows = [float(b.low) for b in vis]
    hi = max(highs)
    lo = min(lows)
    if hi <= lo:
        return ["(flat)"]

    def y(price: float) -> int:
        return int(round((hi - price) / (hi - lo) * (height - 1)))

    # Use sparse spacing so candles are distinguishable without halving the count.
    # Insert one spacer column every N candles.
    gap_every = 3
    total_gaps = (len(vis) - 1) // gap_every
    cols = max(1, len(vis) + total_gaps)
    if cols > plot_w:
        # Trim bars to fit available plot width.
        # Each candle is 1 column plus a gap every `gap_every`.
        max_fit = max(10, plot_w - max(1, plot_w // (gap_every + 1)))
        vis = vis[-max_fit:]
        total_gaps = (len(vis) - 1) // gap_every
        cols = max(1, len(vis) + total_gaps)

    def col_for(i: int) -> int:
        return i + (i // gap_every)

    # Background gridlines (horizontal only).
    base = [[" " for _ in range(cols)] for _ in range(height)]
    h_rows = {0, height - 1, height // 4, height // 2, (3 * height) // 4}
    for r in h_rows:
        if 0 <= r < height:
            for c in range(cols):
                base[r][c] = "·"

    grid = base
    for x, b in enumerate(vis):
        cx = col_for(x)
        yh = y(float(b.high))
        yl = y(float(b.low))
        yo = y(float(b.open))
        yc = y(float(b.close))
        body_top = min(yo, yc)
        body_bot = max(yo, yc)
        for r in range(min(yh, yl), max(yh, yl) + 1):
            grid[r][cx] = "│"
        for r in range(body_top, body_bot + 1):
            grid[r][cx] = "█"

        bull = float(b.close) >= float(b.open)
        if color_on:
            fg = 70 if bull else 203
            for r in range(body_top, body_bot + 1):
                grid[r][cx] = _style(grid[r][cx], fg=fg, bold=True, enable=True)
            for r in range(min(yh, yl), max(yh, yl) + 1):
                if grid[r][cx] == "│":
                    grid[r][cx] = _style("│", fg=245, enable=True)
            # Dim horizontal gridlines.
            for r in range(height):
                for c in range(cols):
                    if isinstance(grid[r][c], str) and grid[r][c] == "·":
                        grid[r][c] = _style(grid[r][c], fg=239, dim=True, enable=True)

    # Build right-side price axis + last price marker.
    last = vis[-1]
    last_close = float(getattr(last, "close", 0.0) or 0.0)
    last_open = float(getattr(last, "open", 0.0) or 0.0)
    last_y = y(last_close)
    last_bull = last_close >= last_open

    def axis_label(r: int) -> str:
        if r not in h_rows:
            return ""
        price = hi - (r / max(1, height - 1)) * (hi - lo)
        return f"{price:.2f}".rjust(axis_w)

    lines: list[str] = []
    for r in range(height):
        row = "".join(grid[r])
        label = axis_label(r)

        # Last price "tag" at the right, similar to the platform screenshot.
        if r == last_y:
            tag = f"[{last_close:.2f}]"
            if color_on:
                fg = 16
                bg = 190 if last_bull else 203
                tag = _style(tag, fg=fg, bg=bg, bold=True, enable=True)
            label = tag.rjust(axis_w)

        # Ensure the plot is fixed width so the right axis stays aligned.
        row = row[:plot_w].ljust(plot_w)
        lines.append(f"{row}{label}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Bottom-left candle view (IBKR delayed bars) for tmux.")
    parser.add_argument("--log", default=os.getenv("TRADEBOT_LOG", "logs/tradebot.log"))
    parser.add_argument("--follow", action="store_true", help="Follow the log (tail -F style).")
    parser.add_argument("--interval", type=float, default=0.5, help="UI refresh interval (seconds).")
    parser.add_argument("--rotate-seconds", type=int, default=30, help="Rotation period when not in an active trade.")
    parser.add_argument("--refresh-seconds", type=int, default=15, help="How often to refetch bars from IBKR.")
    parser.add_argument("--bars", type=int, default=120, help="Requested bars (5 mins).")
    parser.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("IBKR_PORT", "7497")))
    parser.add_argument("--client-id", type=int, default=0, help="0 = auto-pick to avoid collisions.")
    parser.add_argument(
        "--crypto-exchange",
        default=os.getenv("IBKR_CRYPTO_EXCHANGE", "ZEROHASH"),
        help="IBKR crypto exchange (commonly ZEROHASH).",
    )
    parser.add_argument(
        "--render",
        default=os.getenv("CANDLES_RENDER", "auto"),
        choices=["auto", "plain", "rich"],
        help="Rendering backend (rich uses nicer panels if installed).",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        default=None,
        help="Clear+redraw the entire pane each refresh (flickers, but avoids tmux scroll/bounce issues).",
    )
    parser.add_argument(
        "--no-full-refresh",
        dest="full_refresh",
        action="store_false",
        default=None,
        help="Force smooth diff-style updates (disables tmux auto full refresh).",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color rendering.")
    args = parser.parse_args()

    try:
        from ib_insync import IB, Crypto, Forex, Stock  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: ib_insync not available: {exc}", file=sys.stderr)
        return 2

    # Prevent ib_insync from printing/logging errors into the pane (it breaks the UI).
    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
    logging.getLogger("ib_insync").propagate = False

    color_on = _supports_color() and not args.no_color
    rich_mod = _try_import_rich()
    use_rich = args.render == "rich" or (args.render == "auto" and rich_mod is not None)
    # Auto behavior: in tmux default to full-refresh (more stable), otherwise smooth updates.
    in_tmux = bool(os.getenv("TMUX")) or os.getenv("TERM", "").startswith("screen")
    full_refresh = args.full_refresh if args.full_refresh is not None else in_tmux
    screen = None if full_refresh else _SmoothScreen()
    if screen is not None:
        atexit.register(screen.close)
    else:
        # Full refresh mode: still hide cursor to reduce visual noise.
        sys.stdout.write(f"{CSI}?25l")
        sys.stdout.flush()

        def _show_cursor() -> None:
            sys.stdout.write(f"{CSI}?25h")
            sys.stdout.flush()

        atexit.register(_show_cursor)

    state = State(
        last_action_by_symbol={},
        structure_by_symbol={},
        scale_by_symbol={},
        scale_anchor_epoch_by_symbol={},
        rotation_bucket_start=None,
        rotation_symbols=None,
    )
    path = Path(args.log)
    if not path.exists() and not args.follow:
        print(f"[CANDLES] log not found at {path}", file=sys.stderr)
        return 2

    last_inode = None
    last_size = 0

    ib = IB()
    client_id = args.client_id or (int(time.time()) % 10_000) + random.randint(100, 999)
    connected = False
    last_ib_error: tuple[int, str] | None = None
    last_ib_status: tuple[int, str] | None = None
    last_ib_status_ts: float | None = None

    def on_error(req_id, error_code, error_string, contract):  # type: ignore[no-untyped-def]
        nonlocal last_ib_error, last_ib_status, last_ib_status_ts
        code = int(error_code)
        msg = str(error_string).strip()
        last_ib_status = (code, msg)
        last_ib_status_ts = time.time()
        # Informational connectivity/status codes; don't treat as warnings.
        info_codes = {2104, 2106, 2107, 2108, 2157, 2158}
        if code in info_codes:
            return
        last_ib_error = (code, msg)

    ib.errorEvent += on_error

    def ensure_connected() -> bool:
        nonlocal connected
        if connected and ib.isConnected():
            return True
        try:
            ib.connect(args.host, args.port, clientId=client_id, timeout=2.0)
            connected = True
            return True
        except Exception:
            connected = False
            return False

    cached_symbol: str | None = None
    cached_bars = []
    last_fetch_ts: float | None = None
    last_bar_epoch: float | None = None
    last_fetch_err: str | None = None
    status_text: str = ""
    status_style: str = "dim"

    def build_contract(symbol: str):
        sym = symbol.strip().upper()
        # Heuristics:
        # - Crypto pairs in this bot: BTCUSD/ETHUSD/SOLUSD...
        # - Forex pairs: 6 letters, no separators (e.g., EURUSD) but only when both legs are known FX currencies.
        if re.fullmatch(r"[A-Z]{3,10}USD", sym):
            base = sym[:-3]
            if base in {"BTC", "ETH", "SOL", "LTC", "BCH", "XRP", "ADA", "DOGE", "AVAX", "LINK"}:
                return Crypto(base, args.crypto_exchange, "USD")
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

    def pick_what_to_show(contract) -> str:  # type: ignore[no-untyped-def]
        # IBKR expects different whatToShow values depending on instrument type.
        # - Crypto: AGGTRADES (TRADES can error 10299)
        # - Forex: MIDPOINT
        # - Stocks/ETFs: TRADES
        try:
            sec_type = str(getattr(contract, "secType", "") or "").upper()
        except Exception:
            sec_type = ""
        if sec_type == "CRYPTO":
            return "AGGTRADES"
        if sec_type == "CASH":
            return "MIDPOINT"
        return "TRADES"

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
                        _ingest_line(state, line)

            sym, mode = _pick_symbol(state, rotate_seconds=args.rotate_seconds)
            now = time.time()
            if sym and (cached_symbol != sym):
                cached_symbol = sym
                last_fetch_ts = None
                last_fetch_err = None
                # Don't display stale bars from the previous symbol; wait for bars for this symbol.
                cached_bars = []
                last_bar_epoch = None

            refresh_in = 0
            if last_fetch_ts is not None:
                refresh_in = max(0, int(round(args.refresh_seconds - (now - last_fetch_ts))))
            updated_age = None if last_fetch_ts is None else max(0, int(round(now - last_fetch_ts)))

            should_fetch = sym is not None and (last_fetch_ts is None or now - last_fetch_ts >= args.refresh_seconds)
            if should_fetch:
                last_fetch_ts = now
                last_ib_error = None
                if ensure_connected():
                    try:
                        ib.reqMarketDataType(3)  # delayed
                        contract = build_contract(sym)
                        qualified = ib.qualifyContracts(contract)
                        if not qualified:
                            last_fetch_err = f"Unknown/unsupported contract for {sym}: {contract}"
                            raise RuntimeError(last_fetch_err)
                        contract = qualified[0]
                        what_to_show = pick_what_to_show(contract)
                        # Request a bit more history than we display so the chart stays "full"
                        # even when the session is partial or IB returns fewer bars.
                        minutes = max(60, int(args.bars) * 5)
                        days = max(1, (minutes // (60 * 24)) + 2)
                        days = min(days, 5)
                        duration = f"{days} D"
                        bars = ib.reqHistoricalData(
                            contract,
                            endDateTime="",
                            durationStr=duration,
                            barSizeSetting="5 mins",
                            whatToShow=what_to_show,
                            useRTH=False,
                            formatDate=1,
                            keepUpToDate=False,
                        )
                        if bars:
                            cached_bars = list(bars)
                            last_bar_epoch = _to_epoch(getattr(bars[-1], "date", None))
                            last_fetch_err = None
                            # Update stabilized scale only when a bar "closes" (avoid bouncing within a forming bar).
                            try:
                                ordered = sorted(
                                    cached_bars,
                                    key=lambda b: (_to_epoch(getattr(b, "date", None)) or 0.0),
                                )
                                # Use the last *completed* bar as the anchor (exclude the current forming bar).
                                if len(ordered) >= 2:
                                    anchor = _to_epoch(getattr(ordered[-2], "date", None)) or 0.0
                                    prev_anchor = (
                                        state.scale_anchor_epoch_by_symbol.get(sym, 0.0)
                                        if state.scale_anchor_epoch_by_symbol
                                        else 0.0
                                    )
                                    if anchor and anchor != prev_anchor:
                                        hist = ordered[:-1]
                                        curr_hi = max(float(b.high) for b in hist)
                                        curr_lo = min(float(b.low) for b in hist)
                                        if curr_hi > curr_lo:
                                            state.scale_by_symbol[sym] = (curr_hi, curr_lo)
                                            state.scale_anchor_epoch_by_symbol[sym] = anchor
                            except Exception:
                                pass
                        else:
                            last_fetch_err = "no bars returned"
                    except Exception as exc:
                        last_fetch_err = str(exc)
                    if last_ib_error and not last_fetch_err:
                        last_fetch_err = f"IBKR error {last_ib_error[0]}: {last_ib_error[1]}"
                else:
                    last_fetch_err = f"unable to connect to IBKR on {args.host}:{args.port}"

            # Build a fixed-height status line (always present in render) so the chart never shifts.
            if last_fetch_err:
                status_text = f"warning: {last_fetch_err}"
                status_style = "bold white on red"
            elif last_ib_status:
                age = 0.0 if last_ib_status_ts is None else max(0.0, time.time() - last_ib_status_ts)
                if age < 30:
                    status_text = f"ibkr: {last_ib_status[0]} {last_ib_status[1]}"
                    status_style = "dim"
                else:
                    status_text = ""
                    status_style = "dim"
            else:
                status_text = ""
                status_style = "dim"

            cols, rows = _term_size(110, 26)
            chart_height = max(8, min(14, rows - 10))
            structure_info = (state.structure_by_symbol or {}).get(sym) if sym else None
            frame = _render_frame(
                sym=sym,
                mode=mode,
                bars=cached_bars,
                last_bar_epoch=last_bar_epoch,
                last_fetch_err=last_fetch_err,
                status_text=status_text,
                status_style=status_style,
                updated_age=updated_age,
                refresh_in=refresh_in,
                refresh_seconds=args.refresh_seconds,
                width=cols,
                chart_height=chart_height,
                color_on=color_on,
                use_rich=use_rich,
                rich_mod=rich_mod,
                scale=(state.scale_by_symbol or {}).get(sym) if sym else None,
                structure_info=structure_info,
            )
            frame = _fit_to_rows(frame, rows=rows)
            if screen is not None:
                screen.draw(frame)
            else:
                # Full clear+redraw (requested): accept flicker in exchange for stability.
                sys.stdout.write(f"{CSI}H{CSI}2J")
                sys.stdout.write(frame)
                sys.stdout.flush()

            if not args.follow:
                return 0
            time.sleep(args.interval)
        except KeyboardInterrupt:
            try:
                if ib.isConnected():
                    ib.disconnect()
            except Exception:
                pass
            return 0


def _render_frame(
    *,
    sym: str | None,
    mode: str,
    bars,
    last_bar_epoch: float | None,
    last_fetch_err: str | None,
    status_text: str,
    status_style: str,
    updated_age: int | None,
    refresh_in: int,
    refresh_seconds: int,
    width: int,
    chart_height: int,
    color_on: bool,
    use_rich: bool,
    rich_mod: dict[str, Any] | None,
    scale: tuple[float, float] | None,
    structure_info: dict[str, Any] | None,
) -> str:  # type: ignore[no-untyped-def]
    if use_rich and rich_mod is not None:
        try:
            return _render_frame_rich(
                sym=sym,
                mode=mode,
                bars=bars,
                last_bar_epoch=last_bar_epoch,
                last_fetch_err=last_fetch_err,
                status_text=status_text,
                status_style=status_style,
                updated_age=updated_age,
                refresh_in=refresh_in,
                refresh_seconds=refresh_seconds,
                width=width,
                chart_height=chart_height,
                color_on=color_on,
                rich_mod=rich_mod,
                scale=scale,
                structure_info=structure_info,
            )
        except Exception:
            pass
    out: list[str] = []
    title = _style(" CANDLES ", fg=231, bg=22, bold=True, enable=color_on)
    subtitle = _style(" IBKR delayed (mdType=3) ", fg=231, bg=237, bold=True, enable=color_on)
    out.append(title + subtitle)

    if sym is None:
        out.append(_style("waiting: no symbol yet", fg=244, dim=True, enable=color_on))
        out.append(_style("─" * width, fg=238, enable=color_on))
        out.append(_box("CANDLE CHART", ["(no symbol selected)"], width=width, color_on=color_on))
        return "\n".join(out) + "\n"

    now = time.time()
    age_s = None if last_bar_epoch is None else max(0.0, now - last_bar_epoch)
    age_txt = "age=unknown" if age_s is None else f"age={int(age_s//60)}m{int(age_s%60):02d}s"
    cd_txt = "updated=never" if updated_age is None else f"updated={updated_age}s ago"
    right = _style(cd_txt, fg=81, bold=True, enable=color_on)
    left = _style(f"symbol={sym}  {age_txt}", fg=252, bold=True, enable=color_on)
    gap = max(1, width - len(ANSI_RE.sub('', left)) - len(ANSI_RE.sub('', right)) - 1)
    out.append(left + " " * gap + right)
    out.append(_style(f"mode: {mode}", fg=245, enable=color_on))
    info = structure_info or {}
    score_txt = "-" if "selection_score" not in info else f"{info.get('selection_score', 0.0):.3f}"
    ready_txt = "-" if "readiness" not in info else f"{info.get('readiness', 0.0):.2f}"
    gate_txt = info.get("last_gate") or "-"
    sweep_txt = info.get("since_sweep") or "-"
    cont_txt = info.get("since_cont") or "-"
    out.append(
        _style(
            f"score={score_txt}  ready={ready_txt}  gate={gate_txt}  sweep={sweep_txt}  cont={cont_txt}",
            fg=245,
            enable=color_on,
        )
    )
    out.append(_style("─" * width, fg=238, enable=color_on))

    body: list[str] = []
    # Fixed status line (always present) so the chart doesn't shift.
    if status_text:
        body.append(_style(status_text, fg=231, bg=124, bold=True, enable=color_on))
    else:
        body.append("")
    body.append("")

    if bars:
        close = float(getattr(bars[-1], "close", 0.0) or 0.0)
        o = float(getattr(bars[-1], "open", 0.0) or 0.0)
        trend = "bull" if close >= o else "bear"
        trend_fg = 70 if trend == "bull" else 203
        body.append(_style(f"last_close={close:.2f} ({trend})", fg=trend_fg, bold=True, enable=color_on))
        body.append("")
        body.extend(_render_candles(bars, width=width - 4, height=chart_height, color_on=color_on))
    else:
        body.append("(no bars yet)")

    out.append(_box("CANDLE CHART (5m)", [ln[: width - 2] for ln in body], width=width, color_on=color_on))
    return "\n".join(out) + "\n"


def _render_frame_rich(
    *,
    sym: str | None,
    mode: str,
    bars,
    last_bar_epoch: float | None,
    last_fetch_err: str | None,
    status_text: str,
    status_style: str,
    updated_age: int | None,
    refresh_in: int,
    refresh_seconds: int,
    width: int,
    chart_height: int,
    color_on: bool,
    rich_mod: dict[str, Any],
    scale: tuple[float, float] | None,
    structure_info: dict[str, Any] | None,
) -> str:
    Console = rich_mod["Console"]
    Panel = rich_mod["Panel"]
    ROUNDED = rich_mod["ROUNDED"]
    Text = rich_mod["Text"]

    console = Console(
        width=width,
        record=True,
        force_terminal=True,
        color_system="256" if color_on else None,
        legacy_windows=False,
    )

    header = Text.assemble(
        (" CANDLES ", "bold black on green"),
        (" IBKR delayed (mdType=3) ", "bold white on grey23"),
    )
    console.print(header)

    if sym is None:
        console.print(Panel(Text("waiting: no symbol yet", style="dim"), box=ROUNDED))
        return console.export_text(styles=True)

    now = time.time()
    age_s = None if last_bar_epoch is None else max(0.0, now - last_bar_epoch)
    age_txt = "unknown" if age_s is None else f"{int(age_s//60)}m{int(age_s%60):02d}s"

    # Avoid Table reflow (can cause perceived "bouncing" when widths change each second).
    # Build a fixed-width header line (no per-second countdown to avoid flicker).
    left = f"symbol={sym}  age={age_txt}"
    if updated_age is None:
        right = "updated=never"
    else:
        right = f"updated={int(updated_age):02d}s ago"
    pad = max(1, width - len(left) - len(right))
    console.print(Text(left, style="bold white") + Text(" " * pad) + Text(right, style="bold cyan"), no_wrap=True)
    console.print(Text(f"mode: {mode}", style="dim"))
    info = structure_info or {}
    score_txt = "-" if "selection_score" not in info else f"{info.get('selection_score', 0.0):.3f}"
    ready_txt = "-" if "readiness" not in info else f"{info.get('readiness', 0.0):.2f}"
    gate_txt = info.get("last_gate") or "-"
    sweep_txt = info.get("since_sweep") or "-"
    cont_txt = info.get("since_cont") or "-"
    console.print(
        Text(
            f"score={score_txt}  ready={ready_txt}  gate={gate_txt}  sweep={sweep_txt}  cont={cont_txt}",
            style="dim",
        )
    )
    if status_text:
        console.print(Text(status_text[:width], style=status_style), no_wrap=True)
    else:
        console.print(Text(" ", style="dim"), no_wrap=True)

    # Build a colored candle plot with a right-side axis and last-price tag.
    bar_list = list(bars or [])
    if not bar_list:
        console.print(Panel(Text("(no bars yet)", style="dim"), title="CANDLE CHART (5m)", box=ROUNDED))
        return console.export_text(styles=True)

    ordered = sorted(bar_list, key=lambda b: (_to_epoch(getattr(b, "date", None)) or 0.0))
    axis_w = 10
    plot_w = max(28, width - 6 - axis_w)
    # Force a spacer between every candle for clarity.
    max_candles = max(12, min(plot_w // 2, 80))
    vis = ordered[-max_candles:]
    highs = [float(b.high) for b in vis]
    lows = [float(b.low) for b in vis]
    hi = max(highs)
    lo = min(lows)
    # Stabilize y-axis if we have a saved scale for this symbol.
    if scale is not None:
        s_hi, s_lo = scale
        if s_hi > s_lo:
            hi, lo = s_hi, s_lo
    if hi <= lo:
        console.print(Panel(Text("(flat)", style="dim"), title="CANDLE CHART (5m)", box=ROUNDED))
        return console.export_text(styles=True)

    def y(price: float) -> int:
        return int(round((hi - price) / (hi - lo) * (chart_height - 1)))

    cols = max(1, len(vis) * 2 - 1)  # candle + spacer
    # Horizontal grid levels.
    h_rows = {0, chart_height - 1, chart_height // 4, chart_height // 2, (3 * chart_height) // 4}
    grid: list[list[tuple[str, str]]] = [[(" ", "") for _ in range(cols)] for _ in range(chart_height)]
    for r in h_rows:
        if 0 <= r < chart_height:
            for c in range(cols):
                grid[r][c] = ("·", "grey30")

    for i, b in enumerate(vis):
        cx = i * 2
        yh = y(float(b.high))
        yl = y(float(b.low))
        yo = y(float(b.open))
        yc = y(float(b.close))
        body_top = min(yo, yc)
        body_bot = max(yo, yc)
        bull = float(b.close) >= float(b.open)
        body_style = "bold green" if bull else "bold red"
        wick_style = "grey70"
        for r in range(min(yh, yl), max(yh, yl) + 1):
            grid[r][cx] = ("│", wick_style)
        for r in range(body_top, body_bot + 1):
            grid[r][cx] = ("█", body_style)

    last = vis[-1]
    last_close = float(getattr(last, "close", 0.0) or 0.0)
    last_open = float(getattr(last, "open", 0.0) or 0.0)
    last_y = y(last_close)
    last_bull = last_close >= last_open
    last_tag_style = "bold black on yellow" if last_bull else "bold white on red"

    def axis_label(r: int) -> str:
        if r not in h_rows:
            return ""
        price = hi - (r / max(1, chart_height - 1)) * (hi - lo)
        return f"{price:.2f}".rjust(axis_w)

    chart = Text()
    for r in range(chart_height):
        line = Text()
        for ch, st in grid[r]:
            line.append(ch, style=st)
        # pad/trim plot width
        if len(line.plain) < plot_w:
            line.append(" " * (plot_w - len(line.plain)))
        elif len(line.plain) > plot_w:
            line = Text(line.plain[:plot_w])

        label = axis_label(r)
        if r == last_y:
            line.append(f"[{last_close:.2f}]".rjust(axis_w), style=last_tag_style)
        elif label:
            line.append(label, style="grey50")
        chart.append(line)
        chart.append("\n")

    console.print(Panel(chart, title="CANDLE CHART (5m)", box=ROUNDED, padding=(0, 1)))
    return console.export_text(styles=True)


if __name__ == "__main__":
    raise SystemExit(main())
