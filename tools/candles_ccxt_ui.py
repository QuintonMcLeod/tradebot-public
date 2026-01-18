#!/usr/bin/env python3
"""
Candle chart UI for CCXT/Coinbase data.
Tails the tradebot log to determine the active symbol, then fetches candles from Coinbase.
Reuses rendering logic similar to candles_ibkr_ui.py but without IBKR dependencies.
"""
import argparse
import atexit
import math
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Try to import rich if available
try:
    import rich
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
    RICH_MOD = {
        "Console": Console,
        "Panel": Panel,
        "Text": Text,
        "ROUNDED": box.ROUNDED
    }
except ImportError:
    RICH_AVAILABLE = False
    RICH_MOD = {}

# Local imports (ensure PYTHONPATH=src is set)
from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider
from tradebot_sci.market.models import Candle

# Regex to find active symbol in logs
# 2024-01-01 ... [SELECT] Active symbol: ETHUSD (score=...)
SELECT_RE = re.compile(r"\[SELECT\] Active symbol: (?P<symbol>[A-Z0-9]+)")

# Regex to find structure info
# [STRUCTURE] ETHUSD selection_score=1.002 readiness=0.50 ...
STRUCTURE_RE = re.compile(r"\[STRUCTURE\] (?P<symbol>[A-Z0-9]+) (?P<rest>.*)")


def _to_epoch(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


class _SmoothScreen:
    def __init__(self) -> None:
        self._last_lines: list[str] = []
        self._cursor_hidden = False

    def _hide_cursor(self) -> None:
        if self._cursor_hidden:
            return
        sys.stdout.write("\033[?25l")
        self._cursor_hidden = True

    def _show_cursor(self) -> None:
        if not self._cursor_hidden:
            return
        sys.stdout.write("\033[?25h")
        self._cursor_hidden = False

    def close(self) -> None:
        self._show_cursor()
        sys.stdout.flush()

    def draw(self, frame: str) -> None:
        self._hide_cursor()
        lines = frame.splitlines()
        # Simple differential update to reduce flicker
        max_lines = max(len(lines), len(self._last_lines))
        # If frame size changed significantly, clear screen first
        if abs(len(lines) - len(self._last_lines)) > 5:
            sys.stdout.write("\033[2J\033[H")
            self._last_lines = []
        
        for i in range(max_lines):
            new = lines[i] if i < len(lines) else ""
            old = self._last_lines[i] if i < len(self._last_lines) else None
            # Only update changed lines
            if old is not None and new == old:
                continue
            # Move cursor to row i+1
            sys.stdout.write(f"\033[{i+1};1H\033[2K{new}")
        self._last_lines = lines
        sys.stdout.flush()


def _fetch_candles(provider: CoinbaseMarketDataProvider, symbol: str) -> list[Candle]:
    try:
        # Fetch 5m candles (300s)
        # Coinbase provider handles granularity mapping if we fixed it properly :)
        return provider.get_latest_candles(symbol, timeframe="5m", limit=100)
    except Exception as e:
        # logger.error ... but we are a UI tool, maybe just print to stderr or return empty
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Candle chart UI for Coinbase/CCXT.")
    parser.add_argument("--log", default=os.getenv("TRADEBOT_LOG", "logs/tradebot.log"))
    parser.add_argument("--follow", action="store_true", help="Run in loop mode.")
    parser.add_argument("--interval", type=float, default=5, help="Refresh interval (seconds).")
    parser.add_argument("--refresh-seconds", type=float, default=1.0, help="Data fetch interval.")
    parser.add_argument("--render", choices=["plain", "rich"], default="rich")
    
    args = parser.parse_args()

    # Setup
    color_on = _supports_color()
    use_rich = (args.render == "rich" and RICH_AVAILABLE)
    log_path = Path(args.log)
    screen = _SmoothScreen()
    atexit.register(screen.close)
    
    provider = CoinbaseMarketDataProvider()
    atexit.register(provider.close)

    current_symbol: str | None = None
    structure_info: dict[str, Any] = {}
    
    bars: list[Candle] = []
    last_fetch_ts = 0.0
    last_fetch_err: str | None = None
    
    # State for scrolling log reading
    last_inode = None
    last_size = 0

    while True:
        try:
            # 1. Read log to find active symbol and structure info
            if log_path.exists():
                stat = log_path.stat()
                if last_inode is None or stat.st_ino != last_inode or stat.st_size < last_size:
                    last_inode = stat.st_ino
                    last_size = 0  # reset if rotated
                
                with log_path.open("r", encoding="utf-8", errors="replace") as f:
                    if last_size:
                        f.seek(last_size)
                    chunk = f.read()
                    last_size = f.tell()
                    
                if chunk:
                    for line in chunk.splitlines():
                        m_sel = SELECT_RE.search(line)
                        if m_sel:
                            sym = m_sel.group("symbol")
                            if sym != current_symbol:
                                current_symbol = sym
                                bars = [] # clear bars on switch
                                last_fetch_ts = 0 # force fetch
                                structure_info = {}
                        
                        m_struct = STRUCTURE_RE.search(line)
                        if m_struct and m_struct.group("symbol") == current_symbol:
                            # Parse rest: key=value ...
                            rest = m_struct.group("rest")
                            info = {}
                            for kv in rest.split():
                                if "=" in kv:
                                    k, v = kv.split("=", 1)
                                    try:
                                        info[k] = float(v)
                                    except ValueError:
                                        info[k] = v
                            structure_info = info
            
            # 2. Fetch data if needed
            now = time.time()
            if current_symbol and (now - last_fetch_ts > args.refresh_seconds):
                try:
                    # Map symbol if needed? Coinbase provider expects like BTCUSD (and maps internally to BTC-USD)
                    # CCXT symbols in log are usually like BTCUSD.
                    fetched = _fetch_candles(provider, current_symbol)
                    if fetched:
                        bars = fetched
                        last_fetch_err = None
                    last_fetch_ts = now
                except Exception as e:
                    last_fetch_err = str(e)

            # 3. Render
            width = min(160, os.get_terminal_size().columns)
            height = 20 # fixed height for chart area

            last_bar_epoch = _to_epoch(bars[-1].timestamp) if bars else None
            updated_age = int(now - last_fetch_ts) if last_fetch_ts > 0 else None

            if use_rich:
                frame = _render_frame_rich(
                    sym=current_symbol,
                    mode="CCXT/Coinbase",
                    bars=bars,
                    last_bar_epoch=last_bar_epoch,
                    last_fetch_err=last_fetch_err,
                    status_text=last_fetch_err or "",
                    status_style="bold white on red" if last_fetch_err else "dim",
                    updated_age=updated_age,
                    width=width,
                    chart_height=height,
                    color_on=color_on,
                    rich_mod=RICH_MOD,
                    structure_info=structure_info, refresh_rate=args.refresh_seconds
                )
            else:
                # Fallback to simple text if needed (omitted for brevity, users mostly use rich)
                frame = "Rich libraries not found or render=plain selected.\n"
            
            screen.draw(frame)
            
            if not args.follow:
                return 0
            
            time.sleep(args.interval)

        except KeyboardInterrupt:
            return 0
        except Exception:
            # robustness
            time.sleep(1)


def _render_frame_rich(
    *,
    sym: str | None,
    mode: str,
    bars: list[Candle],
    last_bar_epoch: float | None,
    last_fetch_err: str | None,
    status_text: str,
    status_style: str,
    updated_age: int | None,
    width: int,
    chart_height: int,
    color_on: bool,
    rich_mod: dict[str, Any],
    structure_info: dict[str, Any] | None, refresh_rate: float = 15.0,
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
        (" CANDLES ", "bold black on blue"),
        (" Coinbase (5m) " + str(refresh_rate) + "s ", "bold white on grey23"),
    )
    console.print(header)

    if sym is None:
        console.print(Panel(Text("waiting: no active symbol selected by bot strategies...", style="dim"), box=ROUNDED))
        return console.export_text(styles=True)

    now = time.time()
    age_s = None if last_bar_epoch is None else max(0.0, now - last_bar_epoch)
    age_txt = "unknown" if age_s is None else f"{int(age_s//60)}m{int(age_s%60):02d}s"

    left = f"symbol={sym}  bar_age={age_txt}"
    right = f"updated={int(updated_age):02d}s ago" if updated_age is not None else "updated=never"
    
    pad = max(1, width - len(left) - len(right))
    console.print(Text(left, style="bold white") + Text(" " * pad) + Text(right, style="bold cyan"), no_wrap=True)
    
    info = structure_info or {}
    score_txt = f"{info.get('selection_score', 0.0):.3f}"
    gate_txt = str(info.get("last_gate") or "-")
    console.print(Text(f"mode: {mode} | score={score_txt} gate={gate_txt}", style="dim"))
    
    if status_text:
        console.print(Text(status_text[:width], style=status_style), no_wrap=True)
    else:
        # spacer
        console.print(Text(" ", style="dim"))

    # Plot logic (simplified from candles_ibkr_ui.py)
    if not bars:
        console.print(Panel(Text("(no bars loaded)", style="dim"), title="CANDLE CHART", box=ROUNDED))
        return console.export_text(styles=True)

    # Sort by time
    ordered = sorted(bars, key=lambda b: _to_epoch(b.timestamp) or 0.0)
    
    # Chart Params
    axis_w = 10
    plot_w = max(28, width - 6 - axis_w)
    max_candles = max(12, min(plot_w // 2, 80))
    vis = ordered[-max_candles:]
    
    highs = [float(b.high) for b in vis]
    lows = [float(b.low) for b in vis]
    hi = max(highs)
    lo = min(lows)
    
    # Avoid zero division
    if hi <= lo:
        hi = lo + 1.0

    def y(price: float) -> int:
        return int(round((hi - price) / (hi - lo) * (chart_height - 1)))

    cols = max(1, len(vis) * 2 - 1)
    grid: list[list[tuple[str, str]]] = [[(" ", "") for _ in range(cols)] for _ in range(chart_height)]
    
    # Grid lines
    h_rows = {0, chart_height - 1, chart_height // 2}
    for r in h_rows:
        for c in range(cols):
            grid[r][c] = ("·", "grey30")

    # Render bars
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
        
        # Wick
        for r in range(min(yh, yl), max(yh, yl) + 1):
            if 0 <= r < chart_height: grid[r][cx] = ("│", wick_style)
        # Body
        for r in range(body_top, body_bot + 1):
             if 0 <= r < chart_height: grid[r][cx] = ("█", body_style)

    # Convert grid to Text
    chart = Text()
    last_close = float(vis[-1].close)
    last_y = y(last_close)
    last_tag_style = "bold black on yellow" if float(vis[-1].close) >= float(vis[-1].open) else "bold white on red"

    def axis_label(r: int) -> str:
        if r not in h_rows: return ""
        price = hi - (r / max(1, chart_height - 1)) * (hi - lo)
        return f"{price:.2f}".rjust(axis_w)

    for r in range(chart_height):
        line = Text()
        for ch, st in grid[r]:
            line.append(ch, style=st)
        
        # Pad to plot area
        if len(line.plain) < plot_w:
            line.append(" " * (plot_w - len(line.plain)))
        
        # Axis
        label = axis_label(r)
        if r == last_y:
            line.append(f"[{last_close:.2f}]".rjust(axis_w), style=last_tag_style)
        elif label:
            line.append(label, style="grey50")
            
        chart.append(line)
        chart.append("\n")

    console.print(Panel(chart, title="CANDLE CHART (5m)", box=ROUNDED, padding=(0,1)))
    return console.export_text(styles=True)


if __name__ == "__main__":
    raise SystemExit(main())
