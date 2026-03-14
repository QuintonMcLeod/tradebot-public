#!/usr/bin/env python3
"""
engine_replay.py — Thin CLI interface for the Minovsky Engine.

This is NOT the engine. The engine is MinovskyEngine (minovsky_engine.py),
which is built on the Backtester foundation. This file just:
  1. Parses CLI arguments
  2. Creates a MinovskyEngine
  3. Calls engine.run()
  4. Prints results

Usage:
    python tools/engine/engine_replay.py --cartridge conductor_14d_all
    python tools/engine/engine_replay.py --cartridge conductor_14d_all --symbols EURUSD,USDJPY
    python tools/engine/engine_replay.py --days 14
    python tools/engine/engine_replay.py --days 14 --symbols EURUSD,USDJPY --balance 10000
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_repo = Path(__file__).resolve().parents[2]
_src  = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
for _noisy in ("tradebot_sci.market", "tradebot_sci.confluence",
               "tradebot_sci.strategy.safety_guard", "httpcore", "httpx"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("engine_replay")


# ── Imports ───────────────────────────────────────────────────────────────────
from tools.engine.minovsky_engine import MinovskyEngine


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTING — pretty-print BacktestResult
# ═══════════════════════════════════════════════════════════════════════════════

def print_results(result, initial_balance: float, elapsed: float):
    """Print simulation results in the standard engine_replay format."""
    trades = result.trades or []
    pnl = result.total_pnl
    final = result.final_capital

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0
    rr = round(avg_win / abs(avg_loss), 2) if avg_loss else 0

    # Per-symbol breakdown
    sym_trades = {}
    for t in trades:
        sym = t.symbol
        if sym not in sym_trades:
            sym_trades[sym] = {"trades": 0, "pnl": 0.0}
        sym_trades[sym]["trades"] += 1
        sym_trades[sym]["pnl"] += t.pnl

    for sym, info in sorted(sym_trades.items()):
        logger.info(
            f"[ENGINE] [{sym}] {info['trades']} trades  PnL=${info['pnl']:+.2f}"
        )

    logger.info("═" * 70)
    logger.info(f"[ENGINE] ✅ Done in {elapsed:.1f}s")
    logger.info(
        f"[ENGINE] Trades: {len(trades)}  "
        f"(W={len(wins)} L={len(losses)})  WR={wr:.0f}%"
    )
    logger.info(
        f"[ENGINE] PnL: ${pnl:+.2f}  "
        f"AvgWin=${avg_win:+.2f}  AvgLoss=${avg_loss:+.2f}"
    )
    logger.info(
        f"[ENGINE] Final Balance: ${final:.2f}  "
        f"(started ${initial_balance:.2f})"
    )
    logger.info(
        f"[ENGINE] ProfitFactor={profit_factor}  "
        f"MaxDD={result.max_drawdown_pct:.1f}%  RR={rr}"
    )

    # ── Trade log ─────────────────────────────────────────────────────────
    if trades:
        logger.info("─" * 120)
        logger.info(
            f"{'#':<4} {'Symbol':<10} {'Side':<6} {'Entry':<20} "
            f"{'Exit':<20} {'EntryPx':<12} {'ExitPx':<12} "
            f"{'PnL':>9}  {'Exit Reason'}"
        )
        logger.info("─" * 120)
        for i, t in enumerate(trades, 1):
            ep = (
                f"${t.entry_price:.2f}"
                if t.entry_price > 100
                else f"{t.entry_price:.5f}"
            )
            xp = (
                f"${t.exit_price:.2f}"
                if t.exit_price > 100
                else f"{t.exit_price:.5f}"
            )
            entry_ts = t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else ""
            exit_ts = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else ""
            win_mark = "✅" if t.pnl > 0 else "  "
            logger.info(
                f"{i:<4} {t.symbol:<10} {t.direction:<6} "
                f"{entry_ts:<20} {exit_ts:<20} "
                f"{ep:<12} {xp:<12} "
                f"${t.pnl:>+8.2f} {win_mark} {t.exit_reason[:40]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# NON-CARTRIDGE MODE — load data from candle_history (legacy path)
# ═══════════════════════════════════════════════════════════════════════════════

def run_candle_history_mode(
    days: int,
    balance: float,
    symbols_filter=None,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
):
    """Run engine using recorded candle_history data (non-cartridge mode).

    Loads observations from the local candle history cache (per-symbol
    subdirectories with daily .jsonl files) and feeds them into the
    Backtester.
    """
    from tradebot_sci.config.loader import get_settings
    from tradebot_sci.simulation.backtester import Backtester, Candle

    settings = get_settings()
    profile = settings.get_active_profile()

    _CONFIG_DIR = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    ) / "tradebot-sci"
    _CANDLE_DIR = _CONFIG_DIR / "data" / "candle_history"

    # Date range: prefer explicit start/end, fall back to --days offset
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    else:
        end_date = datetime.now(tz=timezone.utc)

    if start_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    else:
        start_date = end_date - timedelta(days=days)

    # ── Discover available symbols from candle_history subdirectories ──
    available_symbols: set[str] = set()
    if _CANDLE_DIR.exists():
        for d in _CANDLE_DIR.iterdir():
            if d.is_dir() and any(d.glob("*.jsonl")):
                available_symbols.add(d.name)

    symbols = sorted(available_symbols)
    if symbols_filter:
        symbols = [s for s in symbols_filter if s in available_symbols]

    if not symbols:
        logger.error("No symbols found in candle_history. Use --cartridge instead.")
        return

    # ── Load candles from .jsonl observation snapshots ─────────────────
    # Each .jsonl line is a full observation: {"ts": ..., "sym": ..., "ltf": [...], "htf": [...]}
    # We extract the LAST ltf candle from each observation to build the
    # candle timeline for the backtester.
    import json as _json

    all_ltf: dict[str, list[Candle]] = {}
    all_htf: dict[str, list[Candle]] = {}

    for sym in symbols:
        sym_dir = _CANDLE_DIR / sym
        ltf_candles: list[Candle] = []
        htf_candles: list[Candle] = []
        seen_ltf_ts: set[str] = set()
        seen_htf_ts: set[str] = set()

        # Sort files by date to process in order
        files = sorted(sym_dir.glob("*.jsonl"))
        for f in files:
            # Filter by date: filename like EURUSD_2026-03-01.jsonl
            match = f.stem.split("_", 1)
            if len(match) >= 2:
                file_date = match[1]
                if file_date < start_date.strftime("%Y-%m-%d"):
                    continue
                if file_date > end_date.strftime("%Y-%m-%d"):
                    continue

            try:
                for line in f.read_text().splitlines():
                    if not line.strip():
                        continue
                    obs = _json.loads(line)

                    # Extract LTF candles (deduplicate by timestamp)
                    for c in obs.get("ltf", []):
                        ts_str = c["t"]
                        if ts_str in seen_ltf_ts:
                            continue
                        seen_ltf_ts.add(ts_str)
                        ltf_candles.append(Candle(
                            timestamp=datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00")
                            ),
                            open=float(c["o"]),
                            high=float(c["h"]),
                            low=float(c["l"]),
                            close=float(c["c"]),
                            volume=float(c.get("v", 0)),
                        ))

                    # Extract HTF candles (deduplicate by timestamp)
                    for c in obs.get("htf", []):
                        ts_str = c["t"]
                        if ts_str in seen_htf_ts:
                            continue
                        seen_htf_ts.add(ts_str)
                        htf_candles.append(Candle(
                            timestamp=datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00")
                            ),
                            open=float(c["o"]),
                            high=float(c["h"]),
                            low=float(c["l"]),
                            close=float(c["c"]),
                            volume=float(c.get("v", 0)),
                        ))
            except Exception as e:
                logger.warning(f"[ENGINE] Error reading {f}: {e}")

        if ltf_candles:
            # Sort by timestamp
            ltf_candles.sort(key=lambda c: c.timestamp)
            htf_candles.sort(key=lambda c: c.timestamp)
            all_ltf[sym] = ltf_candles
            all_htf[sym] = htf_candles
            logger.info(
                f"[ENGINE] {sym}: {len(ltf_candles)} LTF candles, "
                f"{len(htf_candles)} HTF candles "
                f"({ltf_candles[0].timestamp.date()} → {ltf_candles[-1].timestamp.date()})"
            )

    if not all_ltf:
        logger.error("No candle data loaded from candle_history.")
        return

    # ── Write temporary JSON files for the backtester ─────────────────
    import tempfile
    data_paths: dict[str, str] = {}
    htf_data_paths: dict[str, str] = {}
    temp_files: list[str] = []

    for sym, candles in all_ltf.items():
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{sym}_ltf.json", delete=False
        )
        _json.dump(
            [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ],
            tmp,
        )
        tmp.close()
        data_paths[sym] = tmp.name
        temp_files.append(tmp.name)

    for sym, candles in all_htf.items():
        if not candles:
            continue
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{sym}_htf.json", delete=False
        )
        _json.dump(
            [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ],
            tmp,
        )
        tmp.close()
        htf_data_paths[sym] = tmp.name
        temp_files.append(tmp.name)

    # Create backtester with local data
    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    # Force market open for replay
    backtester._is_market_hours_utc = lambda ts: True

    logger.info(
        f"[ENGINE] Candle-history mode: {len(symbols)} symbols, "
        f"{start_date.date()} → {end_date.date()}, ${balance:.2f} capital"
    )

    t0 = time.perf_counter()
    try:
        result = backtester.run_backtest(
            initial_capital=balance,
            start_date=start_date,
            end_date=end_date,
            symbols=list(all_ltf.keys()),
            data_paths=data_paths,
            htf_data_paths=htf_data_paths,
        )
    finally:
        # Clean up temp files
        for tf in temp_files:
            try:
                os.unlink(tf)
            except OSError:
                pass

    elapsed = time.perf_counter() - t0
    print_results(result, balance, elapsed)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Engine Replay — run the SimulationEngine (built on backtester)"
    )
    parser.add_argument(
        "--cartridge", type=str, default=None,
        help="Cartridge name (e.g. conductor_14d_all). "
             "Loads profile, symbols, dates, data from the cartridge config."
    )
    parser.add_argument(
        "--days", type=int, default=14,
        help="Days of history (non-cartridge mode only, default: 14)"
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Start date YYYY-MM-DD (non-cartridge mode, overrides --days)"
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="End date YYYY-MM-DD (non-cartridge mode, defaults to today)"
    )
    parser.add_argument(
        "--balance", type=float, default=5500.0,
        help="Starting balance (non-cartridge mode only, default: 5500)"
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated symbols override (e.g. EURUSD,USDJPY)"
    )
    parser.add_argument(
        "--strategy", type=str, default=None,
        help="Strategy override (e.g. forex_conductor)"
    )
    args = parser.parse_args()

    syms = (
        [s.strip().upper() for s in args.symbols.split(",")]
        if args.symbols
        else None
    )

    if args.cartridge:
        # ── Cartridge mode: use SimulationEngine ──────────────────────
        logger.info(f"[ENGINE] Loading cartridge: {args.cartridge}")
        t0 = time.perf_counter()

        engine = MinovskyEngine.from_cartridge(
            cartridge_name=args.cartridge,
            symbol_override=syms,
            strategy_override=args.strategy,
        )
        result = engine.run()
        elapsed = time.perf_counter() - t0

        print_results(result, engine.initial_capital, elapsed)
    else:
        # ── Candle-history mode (legacy) ──────────────────────────────
        run_candle_history_mode(
            days=args.days,
            balance=args.balance,
            symbols_filter=syms,
            start_date_str=args.start_date,
            end_date_str=args.end_date,
        )


if __name__ == "__main__":
    main()

