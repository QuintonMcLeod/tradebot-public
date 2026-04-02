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

with open(f"{str(Path.home())}/.config/tradebot-sci/logs/gui_start_debug.log", "a") as df:
    df.write(f"\n--- ENGINE REPLAY START ---\n")
    df.write(f"SYS PATH: {sys.path}\n")
    df.write(f"CWD: {os.getcwd()}\n")
    df.write(f"ARGS: {sys.argv}\n")
    try:
        from tradebot_sci.paths import CONFIG_FILE
        df.write(f"CONFIG PATH RESOLVED: {CONFIG_FILE}\n")
    except Exception as e:
        df.write(f"FAILED TO GET PATHS: {e}\n")

# ── Imports ───────────────────────────────────────────────────────────────────
from tools.engine.minovsky_engine import MinovskyEngine
from datetime import datetime
def parse_cli_date(d_str: str) -> datetime:
    try:
        return datetime.strptime(d_str, "%Y-%m-%d")
    except ValueError:
        return datetime.strptime(d_str, "%m/%d/%Y")


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

    # ── JSON summary to stdout (consumed by GUI main.js) ──────────────
    import json
    json_trades = []
    for t in trades:
        dur = ""
        if t.entry_time and t.exit_time:
            delta = t.exit_time - t.entry_time
            mins = int(delta.total_seconds() / 60)
            if mins >= 60:
                dur = f"{mins // 60}h {mins % 60}m"
            else:
                dur = f"{mins}m"
        json_trades.append({
            "symbol": t.symbol,
            "side": t.direction,
            "pnl": round(t.pnl, 2),
            "time": t.entry_time.isoformat() if t.entry_time else None,
            "duration": dur,
            "reason": t.exit_reason or "",
            "strategy": getattr(t, "strategy_name", ""),
        })

    summary = {
        "total_pnl": round(pnl, 2),
        "win_rate": round(wr, 1),
        "total_trades": len(trades),
        "max_drawdown": round(result.max_drawdown_pct, 2),
        "profit_factor": profit_factor,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "risk_reward": rr,
        "initial_capital": initial_balance,
        "final_capital": round(final, 2),
        "trades": json_trades,
    }
    
    with open(f"{str(Path.home())}/.config/tradebot-sci/logs/gui_start_debug.log", "a") as df:
        df.write(f"\n--- ENGINE REPLAY JSON OUTPUT ---\n")
        df.write(json.dumps(summary, indent=2))
        
    print(json.dumps(summary), flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CANDLE DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_candle_dir() -> Path:
    """Return the candle_history directory path."""
    _CONFIG_DIR = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    ) / "tradebot-sci"
    return _CONFIG_DIR / "data" / "candle_history"


def _discover_symbols(candle_dir: Path, symbols_filter=None, api_fallback: bool = False) -> list[str]:
    """Discover available symbols from candle_history subdirectories."""
    # If API fallback is allowed, trust the explicitly provided symbols list
    if api_fallback and symbols_filter:
        return list(symbols_filter)
        
    available: set[str] = set()
    if candle_dir.exists():
        for d in candle_dir.iterdir():
            if d.is_dir() and any(d.glob("*.jsonl")):
                available.add(d.name)
    symbols = sorted(available)
    if symbols_filter:
        symbols = [s for s in symbols_filter if s in available]
    return symbols


def _load_candles_for_range(
    candle_dir: Path,
    symbols: list[str],
    date_start: str,
    date_end: str,
    api_fallback: bool = False,
):
    """Load LTF and HTF candles from .jsonl files for the given date range.

    Uses threading to load multiple symbols concurrently (disk I/O releases
    the GIL, so threads provide real parallelism for file reading).

    Returns (all_ltf, all_htf) dicts mapping symbol -> list of Candle.
    """
    import json as _json
    from concurrent.futures import ThreadPoolExecutor
    from tradebot_sci.simulation.backtester import Candle

    def _load_symbol(sym: str):
        """Load candles for a single symbol (runs in a thread)."""
        sym_dir = candle_dir / sym
        if not sym_dir.exists():
            return sym, [], []
        ltf_candles = []
        htf_candles = []
        mtf_candles = []
        seen_ltf: set[str] = set()
        seen_htf: set[str] = set()
        seen_mtf: set[str] = set()

        for f in sorted(sym_dir.glob("*.jsonl")):
            parts = f.stem.split("_", 1)
            if len(parts) >= 2:
                file_date = parts[1]
                if file_date < date_start:
                    continue
                if file_date > date_end:
                    continue
            try:
                for line in f.read_text().splitlines():
                    if not line.strip():
                        continue
                    obs = _json.loads(line)
                    for c in obs.get("ltf", []):
                        ts_str = c["t"]
                        if ts_str not in seen_ltf:
                            seen_ltf.add(ts_str)
                            ltf_candles.append(Candle(
                                timestamp=datetime.fromisoformat(ts_str.replace("Z", "+00:00")),
                                open=float(c["o"]), high=float(c["h"]),
                                low=float(c["l"]), close=float(c["c"]),
                                volume=float(c.get("v", 0)),
                            ))
                    for c in obs.get("htf", []):
                        ts_str = c["t"]
                        if ts_str not in seen_htf:
                            seen_htf.add(ts_str)
                            htf_candles.append(Candle(
                                timestamp=datetime.fromisoformat(ts_str.replace("Z", "+00:00")),
                                open=float(c["o"]), high=float(c["h"]),
                                low=float(c["l"]), close=float(c["c"]),
                                volume=float(c.get("v", 0)),
                            ))
                    for c in obs.get("mtf", []):
                        ts_str = c["t"]
                        if ts_str not in seen_mtf:
                            seen_mtf.add(ts_str)
                            mtf_candles.append(Candle(
                                timestamp=datetime.fromisoformat(ts_str.replace("Z", "+00:00")),
                                open=float(c["o"]), high=float(c["h"]),
                                low=float(c["l"]), close=float(c["c"]),
                                volume=float(c.get("v", 0)),
                            ))
            except Exception as e:
                logging.getLogger("engine_replay").warning(f"[ENGINE] Error reading {f}: {e}")

        # Trigger API fallback if we have NO candles, OR if we are significantly missing the warmup period
        needs_fallback = not ltf_candles
        if api_fallback and ltf_candles:
            first_loaded = ltf_candles[0].timestamp
            target_start = parse_cli_date(date_start).replace(tzinfo=timezone.utc)
            # If our first local candle is more than 5 days after the requested start
            if (first_loaded - target_start).total_seconds() > 5 * 86400:
                needs_fallback = True

        if api_fallback and needs_fallback:
            try:
                from tradebot_sci.config.loader import load_config_json
                from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
                from tradebot_sci import paths as _paths
                secrets_path = _paths.SECRETS_FILE
                
                account_id = None
                api_key = None
                env = "practice"
                if secrets_path.exists():
                    from dotenv import dotenv_values
                    secrets = dotenv_values(secrets_path)
                    config = load_config_json()
                    account_id = config.get("brokers", {}).get("oanda", {}).get("account_id")
                    api_key = secrets.get("OANDA_API_KEY") or secrets.get("OANDA_API_TOKEN")
                    env = config.get("brokers", {}).get("oanda", {}).get("environment", "practice")
                
                if account_id and api_key:
                    provider = OandaMarketDataProvider(account_id, api_key, env)
                    
                    start_dt = parse_cli_date(date_start).replace(tzinfo=timezone.utc)
                    end_dt = parse_cli_date(date_end).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                    
                    # 5-min candles
                    delta_ltf = end_dt - start_dt
                    minutes_ltf = int(delta_ltf.total_seconds() / 60)
                    limit_ltf = min(5000, minutes_ltf // 5)
                    
                    # 4-hour candles
                    delta_htf = end_dt - start_dt
                    hours_htf = int(delta_htf.total_seconds() / 3600)
                    limit_htf = min(5000, hours_htf // 4)
                    
                    _log = logging.getLogger("engine_replay")
                    _log.info(f"[API-FALLBACK] Fetching {limit_ltf} LTF and {limit_htf} HTF candles for {sym}")
                    
                    # Custom fetch to specify `from` and `to` with pagination (OANDA limits to 5000 per request)
                    import oandapyV20.endpoints.instruments as instruments
                    oanda_sym = provider._normalize_symbol(sym)
                    
                    def _fetch_paginated_candles(granularity: str, start: datetime, end: datetime) -> list:
                        all_candles = []
                        current_start = start
                        # OANDA allows max 5000 candles per request.
                        # For M5, 5000 candles is ~17.3 days.
                        # For H4, 5000 candles is ~833 days.
                        while current_start < end:
                            duration_seconds = (end - current_start).total_seconds()
                            if granularity == "M5":
                                needed = int(duration_seconds / 300) + 10
                            elif granularity == "H4":
                                needed = int(duration_seconds / 14400) + 10
                            else:
                                needed = 5000
                            
                            params = {
                                "granularity": granularity,
                                "price": "M",
                                "from": current_start.isoformat(),
                                "count": min(5000, max(1, needed))
                            }
                            
                            try:
                                r = instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
                                provider.client.request(r)
                                batch = r.response.get("candles", [])
                                
                                if not batch:
                                    break # No more data
                                    
                                all_candles.extend(batch)
                                
                                # Update current_start to the time of the LAST candle retrieved + 1 second
                                last_time_str = batch[-1]["time"]
                                if "." in last_time_str:
                                    base, rest = last_time_str.split(".", 1)
                                    rest = rest.replace("Z", "+00:00")
                                    last_time_str = f"{base}.{rest[:6]}"
                                else:
                                    last_time_str = last_time_str.replace("Z", "+00:00")
                                    
                                last_ts = datetime.fromisoformat(last_time_str).replace(tzinfo=timezone.utc)
                                
                                if last_ts >= end:
                                    break
                                    
                                current_start = last_ts + timedelta(seconds=1)
                                
                            except Exception as e:
                                _log.error(f"[API-FALLBACK] Pagination fail for {granularity} at {current_start}: {e}")
                                break
                                
                        return [c for c in all_candles if datetime.fromisoformat(c["time"].split(".")[0].replace("Z", "+00:00")).replace(tzinfo=timezone.utc) <= end]

                    # ── Resolve Timeframes from active profile ─────────────────
                    from tradebot_sci.config.loader import get_settings
                    _active_prof = get_settings().get_active_profile()
                    _exec_setting = getattr(_active_prof, "candle_timeframe", None) or "5m"
                    _htf_setting = getattr(_active_prof, "htf_timeframe", None) or "4h"
                    _mtf_setting = getattr(_active_prof, "mtf_timeframe", None) or "1h"
                    
                    # Map common timeframes to OANDA granularity
                    _oanda_granularity_map = {
                        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
                        "1h": "H1", "4h": "H4", "1d": "D", "1w": "W"
                    }
                    oanda_exec_tf = _oanda_granularity_map.get(_exec_setting.lower(), "M5")
                    oanda_htf_tf = _oanda_granularity_map.get(_htf_setting.lower(), "H1")
                    oanda_mtf_tf = _oanda_granularity_map.get(_mtf_setting.lower(), "H1")
                    _log.info(f"[API-FALLBACK] Using mapped OANDA EXEC Timeframe: {oanda_exec_tf} (from profile setting: {_exec_setting})")
                    _log.info(f"[API-FALLBACK] Using mapped OANDA HTF Timeframe: {oanda_htf_tf} (from profile setting: {_htf_setting})")
                    _log.info(f"[API-FALLBACK] Using mapped OANDA MTF Timeframe: {oanda_mtf_tf} (from profile setting: {_mtf_setting})")

                    raw_ltf = _fetch_paginated_candles(oanda_exec_tf, start_dt, end_dt)
                    raw_htf = _fetch_paginated_candles(oanda_htf_tf, start_dt, end_dt)

                    # ── MTF (1H) candles: separate fetch for trend invalidation ──
                    # Only fetch if MTF is a different granularity than HTF
                    raw_mtf = []
                    if oanda_mtf_tf != oanda_htf_tf:
                        raw_mtf = _fetch_paginated_candles(oanda_mtf_tf, start_dt, end_dt)
                    else:
                        raw_mtf = raw_htf  # If MTF == HTF, reuse the same data
                    
                    # Process raw_ltf into ltf_candles
                    for c in raw_ltf:
                        mid = c.get("mid")
                        if mid and c.get("complete", True):
                            ts_str = c["time"]
                            # Clean up nanoseconds issue like in provider
                            if "." in ts_str:
                                base, rest = ts_str.split(".", 1)
                                suffix = ""
                                if "Z" in rest:
                                    suffix = "Z"
                                    rest = rest.replace("Z", "")
                                elif "+" in rest:
                                    rest, offset = rest.split("+", 1)
                                    suffix = "+" + offset
                                elif "-" in rest:
                                    rest, offset = rest.split("-", 1)
                                    suffix = "-" + offset
                                ts_str = f"{base}.{rest[:6]}{suffix}"

                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                            ltf_candles.append(Candle(
                                timestamp=ts, open=float(mid["o"]), high=float(mid["h"]),
                                low=float(mid["l"]), close=float(mid["c"]), volume=float(c["volume"])
                            ))

                    def _parse_raw_candles(raw_list, target_list):
                        for c in raw_list:
                            mid = c.get("mid")
                            if mid and c.get("complete", True):
                                ts_str = c["time"]
                                if "." in ts_str:
                                    base, rest = ts_str.split(".", 1)
                                    suffix = ""
                                    if "Z" in rest:
                                        suffix = "Z"
                                        rest = rest.replace("Z", "")
                                    elif "+" in rest:
                                        rest, offset = rest.split("+", 1)
                                        suffix = "+" + offset
                                    elif "-" in rest:
                                        rest, offset = rest.split("-", 1)
                                        suffix = "-" + offset
                                    ts_str = f"{base}.{rest[:6]}{suffix}"
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                                target_list.append(Candle(
                                    timestamp=ts, open=float(mid["o"]), high=float(mid["h"]),
                                    low=float(mid["l"]), close=float(mid["c"]), volume=float(c["volume"])
                                ))

                    _parse_raw_candles(raw_htf, htf_candles)
                    _parse_raw_candles(raw_mtf, mtf_candles)

            except Exception as e:
                logging.getLogger("engine_replay").warning(f"[API-FALLBACK] Failed to fetch {sym}: {e}")

        if ltf_candles:
            ltf_candles.sort(key=lambda c: c.timestamp)
            htf_candles.sort(key=lambda c: c.timestamp)
            mtf_candles.sort(key=lambda c: c.timestamp)

            # ── Price continuity guard ────────────────────────────
            # Drop candles where close jumps beyond asset-class-specific
            # thresholds. Forex rarely moves >2%/day, so 5% is generous
            # for 5-min candles. HTF (H4) gets a wider threshold since
            # bars can gap between sessions/weekends.
            _METALS = {"XAUUSD", "XAGUSD"}
            _OIL = {"WTICOUSD", "BCOUSD"}
            if sym in _METALS:
                MAX_JUMP_LTF = 0.10   # Gold can gap 5-8% on news
                MAX_JUMP_HTF = 0.15
            elif sym in _OIL:
                MAX_JUMP_LTF = 0.15   # Oil can be volatile
                MAX_JUMP_HTF = 0.20
            elif sym.startswith(("BTC", "ETH", "XRP")) or sym.endswith(("BTC", "ETH")):
                MAX_JUMP_LTF = 0.15   # Crypto
                MAX_JUMP_HTF = 0.20
            else:
                MAX_JUMP_LTF = 0.05   # Forex LTF: 5% is already extreme for 5-min bars
                MAX_JUMP_HTF = 0.10   # Forex HTF: 10% allows session gaps
            _log = logging.getLogger("engine_replay")

            def _filter_corrupt(candles, label, max_jump):
                if not candles:
                    return candles
                clean = [candles[0]]
                dropped = 0
                for i in range(1, len(candles)):
                    prev_close = clean[-1].close
                    curr_close = candles[i].close
                    if prev_close > 0 and abs(curr_close - prev_close) / prev_close > max_jump:
                        dropped += 1
                        continue
                    clean.append(candles[i])
                if dropped:
                    _log.warning(
                        f"[DATA-GUARD] {sym} {label}: dropped {dropped} candles with >{max_jump*100:.0f}% price jumps (corrupt data)"
                    )
                return clean

            ltf_candles = _filter_corrupt(ltf_candles, "LTF", MAX_JUMP_LTF)
            htf_candles = _filter_corrupt(htf_candles, "HTF", MAX_JUMP_HTF)
            mtf_candles = _filter_corrupt(mtf_candles, "MTF", MAX_JUMP_HTF)  # MTF uses HTF threshold
        return sym, ltf_candles, htf_candles, mtf_candles

    # Thread pool: load all symbols concurrently
    all_ltf: dict[str, list] = {}
    all_htf: dict[str, list] = {}
    all_mtf: dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as executor:
        results = list(executor.map(_load_symbol, symbols))

    for sym, ltf, htf, mtf in results:
        if ltf:
            all_ltf[sym] = ltf
            all_htf[sym] = htf
            all_mtf[sym] = mtf

    return all_ltf, all_htf, all_mtf


def _write_temp_json(candles_dict: dict) -> tuple[dict[str, str], list[str]]:
    """Write candle dicts to temp JSON files for the Backtester.

    Returns (paths_dict, temp_file_list).
    """
    import json as _json
    import tempfile

    paths: dict[str, str] = {}
    temp_files: list[str] = []

    for sym, candles in candles_dict.items():
        if not candles:
            continue
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{sym}.json", delete=False
        )
        _json.dump(
            [{"timestamp": c.timestamp.isoformat(),
              "open": c.open, "high": c.high,
              "low": c.low, "close": c.close,
              "volume": c.volume} for c in candles],
            tmp,
        )
        tmp.close()
        paths[sym] = tmp.name
        temp_files.append(tmp.name)

    return paths, temp_files


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-DAY WORKER (top-level function for multiprocessing pickle)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_single_day_worker(args: tuple) -> dict:
    """Run one day of backtesting in an isolated process.

    Args is a tuple: (day_str, balance, symbols_filter, api_fallback, strategy_override)
    Returns a dict: {day, trades, pnl, return_pct, initial, final, stats}
    """
    if len(args) == 5:
        day_str, balance, symbols_filter, api_fallback, strategy_override = args
    else:
        day_str, balance, symbols_filter, api_fallback = args
        strategy_override = None

    # Suppress noisy loggers in worker processes
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for _noisy in ("tradebot_sci.market", "tradebot_sci.confluence",
                   "tradebot_sci.strategy.safety_guard",
                   "httpcore", "httpx"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    logging.getLogger("engine_replay").setLevel(logging.INFO)
    logging.getLogger("tradebot_sci.simulation.backtester").setLevel(logging.INFO)

    try:
        from tradebot_sci.config.loader import get_settings
        from tradebot_sci.simulation.backtester import Backtester

        settings = get_settings()
        if strategy_override:
            act_prof = settings.get_active_profile()
            if hasattr(act_prof, "strategy_variant"):
                act_prof.strategy_variant = strategy_override
                act_prof.strategies = None
            settings.profiles[settings.app.profile_name] = act_prof

        candle_dir = _get_candle_dir()
        symbols = _discover_symbols(candle_dir, symbols_filter)
        if not symbols:
            return {"day": day_str, "trades": [], "pnl": 0.0, "return_pct": 0.0,
                    "initial": balance, "final": balance, "stats": {}}

        day_start = parse_cli_date(day_str).replace(tzinfo=timezone.utc)
        day_end = day_start.replace(hour=23, minute=59, second=59)

        # Load candles: include 50 days before for indicator warmup (H4 SMA 200 requires ~47 calendar days accounting for weekends)
        warmup_start = (day_start - timedelta(days=50)).strftime("%Y-%m-%d")
        all_ltf, all_htf, all_mtf = _load_candles_for_range(
            candle_dir, symbols, warmup_start, day_str, api_fallback=api_fallback
        )

        if not all_ltf:
            return {"day": day_str, "trades": [], "pnl": 0.0, "return_pct": 0.0,
                    "initial": balance, "final": balance, "stats": {}}

        # Write temp files
        data_paths, temp_ltf = _write_temp_json(all_ltf)
        htf_paths, temp_htf = _write_temp_json(all_htf)
        mtf_paths, temp_mtf = _write_temp_json(all_mtf)
        temp_files = temp_ltf + temp_htf + temp_mtf

        backtester = Backtester(ib=None, settings=settings, ai_client=None)
        backtester._is_market_hours_utc = lambda ts: True

        # ── Auto-detect actual candle resolution from data ────────
        # Local .jsonl files may contain 5m candles even if the profile
        # says 1m. Detect median bar interval and override the profile
        # so the backtester steps at the correct frequency.
        _first_sym_candles = next(iter(all_ltf.values()), [])
        if len(_first_sym_candles) >= 3:
            _intervals = []
            for _i in range(1, min(20, len(_first_sym_candles))):
                _dt = (_first_sym_candles[_i].timestamp - _first_sym_candles[_i-1].timestamp).total_seconds()
                if 0 < _dt <= 86400:  # Ignore gaps > 1 day
                    _intervals.append(_dt)
            if _intervals:
                _median_interval = sorted(_intervals)[len(_intervals) // 2]
                _tf_map = {60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h", 14400: "4h"}
                _detected_tf = _tf_map.get(int(_median_interval))
                _configured_tf = settings.get_active_profile().candle_timeframe
                if _detected_tf and _detected_tf != _configured_tf:
                    _log = logging.getLogger("engine_replay")
                    _log.info(
                        f"[ENGINE] Auto-detected candle resolution: {_detected_tf} "
                        f"(profile says {_configured_tf}). Overriding for accurate simulation."
                    )
                    settings.get_active_profile().candle_timeframe = _detected_tf

        try:
            result = backtester.run_backtest(
                initial_capital=balance,
                start_date=day_start,
                end_date=day_end,
                symbols=list(all_ltf.keys()),
                data_paths=data_paths,
                htf_data_paths=htf_paths,
                mtf_data_paths=mtf_paths,
            )
        finally:
            for f in temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        # Serialize trades for cross-process transfer
        trades_serialized = []
        for t in result.trades:
            trades_serialized.append({
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size": t.size,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "pnl": t.pnl,
                "exit_reason": t.exit_reason,
                "strategy_name": getattr(t, "strategy_name", "unknown"),
            })

        return {
            "day": day_str,
            "trades": trades_serialized,
            "pnl": result.total_pnl,
            "return_pct": result.total_return_pct,
            "initial": result.initial_capital,
            "final": result.final_capital,
            "stats": {
                "trades_blocked": result.potential_trades_blocked,
            },
        }

    except Exception as e:
        logging.getLogger("engine_replay").error(f"[PARALLEL] Day {day_str} failed: {e}")
        return {"day": day_str, "trades": [], "pnl": 0.0, "return_pct": 0.0,
                "initial": balance, "final": balance, "stats": {}, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# NON-CARTRIDGE MODES
# ═══════════════════════════════════════════════════════════════════════════════

def run_candle_history_mode(
    days: int,
    balance: float,
    symbols_filter=None,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
    api_fallback: bool = False,
    strategy_override: str | None = None,
):
    """Run engine using recorded candle_history data (non-cartridge mode).

    For multi-day ranges (>1 day), automatically parallelizes across CPU cores
    with one day per core. Results are merged with compounding applied.
    """
    candle_dir = _get_candle_dir()

    # Date range: prefer explicit start/end, fall back to --days offset
    if end_date_str:
        end_date = parse_cli_date(end_date_str).replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    else:
        end_date = datetime.now(tz=timezone.utc)

    if start_date_str:
        start_date = parse_cli_date(start_date_str).replace(
            tzinfo=timezone.utc
        )
    else:
        start_date = end_date - timedelta(days=days)

    symbols = _discover_symbols(candle_dir, symbols_filter, api_fallback)
    if not symbols:
        logger.error("No symbols found in candle_history. Use --cartridge instead.")
        import sys; sys.exit(1)

    # Calculate day list
    day_list: list[str] = []
    d = start_date
    while d.date() <= end_date.date():
        day_list.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    num_days = len(day_list)

    # ── Single day: run directly (no multiprocessing overhead) ──
    if num_days <= 1:
        _run_single_day_sequential(
            candle_dir, symbols, start_date, end_date, balance, api_fallback, strategy_override
        )
        return

    # ── Multi-day: parallel across CPU cores ──────────────────────
    import multiprocessing

    num_cores = min(multiprocessing.cpu_count(), 6) # Cap at 6 to prevent OOM on large date ranges
    num_cores = min(num_cores, num_days)
    logger.info(
        f"[PARALLEL] ⚡ Multi-core mode: {num_days} days across {num_cores} cores "
        f"({', '.join(day_list[:3])}{'...' if num_days > 3 else ''})"
    )
    logger.info(
        f"[PARALLEL] Symbols: {', '.join(symbols)} | "
        f"Starting capital: ${balance:.2f}"
    )

    t0 = time.perf_counter()

    worker_args = [(day_str, balance, symbols_filter, api_fallback, strategy_override) for day_str in day_list]

    import sys
    import json as _json
    day_results = []
    completed = 0
    with multiprocessing.Pool(processes=num_cores) as pool:
        for res in pool.imap_unordered(_run_single_day_worker, worker_args):
            day_results.append(res)
            completed += 1
            print(
                _json.dumps({
                    "_type": "progress",
                    "pct": int((completed / num_days) * 100),
                    "symbol": "Engine",
                    "details": f"({completed}/{num_days} Days)"
                }),
                file=sys.stderr,
                flush=True
            )

    elapsed = time.perf_counter() - t0

    # ── Merge results with compounding ────────────────────────────
    _merge_and_print_parallel_results(
        day_results, balance, start_date, end_date, elapsed
    )


def _run_single_day_sequential(
    candle_dir: Path,
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
    balance: float,
    api_fallback: bool = False,
    strategy_override: str | None = None,
):
    """Run a single-day backtest sequentially (no multiprocessing overhead)."""
    from tradebot_sci.config.loader import get_settings
    from tradebot_sci.simulation.backtester import Backtester

    settings = get_settings()
    if strategy_override:
        act_prof = settings.get_active_profile()
        if hasattr(act_prof, "strategy_variant"):
            act_prof.strategy_variant = strategy_override
            act_prof.strategies = None
        settings.profiles[settings.app.profile_name] = act_prof

    # Load candles with warmup (50 days)
    warmup_start = (start_date - timedelta(days=50)).strftime("%Y-%m-%d")
    all_ltf, all_htf, all_mtf = _load_candles_for_range(
        candle_dir, symbols, warmup_start, end_date.strftime("%Y-%m-%d"), api_fallback=api_fallback
    )

    if not all_ltf:
        logger.error("No candle data loaded from candle_history.")
        import sys; sys.exit(1)

    for sym in all_ltf:
        ltf = all_ltf[sym]
        htf = all_htf.get(sym, [])
        logger.info(
            f"[ENGINE] {sym}: {len(ltf)} LTF candles, {len(htf)} HTF candles "
            f"({ltf[0].timestamp.date()} → {ltf[-1].timestamp.date()})"
        )

    data_paths, temp_ltf = _write_temp_json(all_ltf)
    htf_paths, temp_htf = _write_temp_json(all_htf)
    mtf_paths, temp_mtf = _write_temp_json(all_mtf)
    temp_files = temp_ltf + temp_htf + temp_mtf

    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    backtester._is_market_hours_utc = lambda ts: True

    # ── Auto-detect actual candle resolution from data ────────
    _first_sym_candles = next(iter(all_ltf.values()), [])
    if len(_first_sym_candles) >= 3:
        _intervals = []
        for _i in range(1, min(20, len(_first_sym_candles))):
            _dt = (_first_sym_candles[_i].timestamp - _first_sym_candles[_i-1].timestamp).total_seconds()
            if 0 < _dt <= 86400:
                _intervals.append(_dt)
        if _intervals:
            _median_interval = sorted(_intervals)[len(_intervals) // 2]
            _tf_map = {60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h", 14400: "4h"}
            _detected_tf = _tf_map.get(int(_median_interval))
            _configured_tf = settings.get_active_profile().candle_timeframe
            if _detected_tf and _detected_tf != _configured_tf:
                logger.info(
                    f"[ENGINE] Auto-detected candle resolution: {_detected_tf} "
                    f"(profile says {_configured_tf}). Overriding for accurate simulation."
                )
                settings.get_active_profile().candle_timeframe = _detected_tf

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
            htf_data_paths=htf_paths,
            mtf_data_paths=mtf_paths,
        )
    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except OSError:
                pass

    elapsed = time.perf_counter() - t0
    print_results(result, balance, elapsed)


def _merge_and_print_parallel_results(
    day_results: list[dict],
    initial_balance: float,
    start_date: datetime,
    end_date: datetime,
    elapsed: float,
):
    """Merge per-day results with compounding and print final report."""
    from tradebot_sci.simulation.backtester import SimulatedTrade, BacktestResult

    # Sort by date
    day_results.sort(key=lambda r: r["day"])

    # ── Compounding: chain daily returns ──────────────────────────
    compounded_capital = initial_balance
    all_trades: list[SimulatedTrade] = []
    total_blocked = 0
    daily_log_lines: list[str] = []

    for dr in day_results:
        day = dr["day"]
        day_pnl = dr["pnl"]  # Use the raw uncompounded dollar PnL from the day
        daily_return = day_pnl / compounded_capital if compounded_capital > 0 else 0
        compounded_capital += day_pnl
        n_trades = len(dr["trades"])
        total_blocked += dr.get("stats", {}).get("trades_blocked", 0)

        # Log errors if any
        if dr.get("error"):
            daily_log_lines.append(
                f"  {day}  ❌  ERROR: {dr['error']}"
            )
            continue

        emoji = "✅" if day_pnl >= 0 else "❌"
        daily_log_lines.append(
            f"  {day}  {emoji}  {n_trades} trades  "
            f"Day PnL: ${day_pnl:+.2f}  "
            f"Running: ${compounded_capital:.2f}"
        )

        # Reconstruct SimulatedTrade objects
        for t in dr["trades"]:
            all_trades.append(SimulatedTrade(
                symbol=t["symbol"],
                direction=t["direction"],
                entry_price=t["entry_price"],
                exit_price=t["exit_price"],
                size=t["size"],
                entry_time=datetime.fromisoformat(t["entry_time"]) if t["entry_time"] else None,
                exit_time=datetime.fromisoformat(t["exit_time"]) if t["exit_time"] else None,
                pnl=t["pnl"],
                exit_reason=t["exit_reason"],
                strategy_name=t.get("strategy_name", "unknown"),
            ))

    # Sort trades by entry time
    all_trades.sort(key=lambda t: t.entry_time or datetime.min.replace(tzinfo=timezone.utc))

    total_pnl = compounded_capital - initial_balance

    # Build merged result
    result = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_balance,
        final_capital=compounded_capital,
        total_pnl=total_pnl,
        total_return_pct=(total_pnl / initial_balance) * 100,
        trades=all_trades,
        potential_trades_blocked=total_blocked,
    )

    # Recalculate aggregate stats
    wins = [t for t in all_trades if t.pnl > 0]
    losses = [t for t in all_trades if t.pnl <= 0]
    result.win_rate = (len(wins) / len(all_trades) * 100) if all_trades else 0
    result.avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0
    result.avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0

    # Max drawdown from daily equity
    peak = initial_balance
    max_dd = 0.0
    equity = initial_balance
    for dr in day_results:
        day_pnl = dr["pnl"]
        equity += day_pnl
        if equity > peak:
            peak = equity
        dd = ((peak - equity) / peak) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    result.max_drawdown_pct = max_dd

    # ── Print daily breakdown ─────────────────────────────────────
    logger.info("═" * 70)
    logger.info("[PARALLEL] Daily Breakdown (compounded):")
    for line in daily_log_lines:
        logger.info(f"[PARALLEL] {line}")
    logger.info("═" * 70)

    # ── Print final results using standard format ─────────────────
    print_results(result, initial_balance, elapsed)


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
    parser.add_argument(
        "--no-parallel", action="store_true",
        help="Disable multi-core parallelism (force single-threaded)"
    )
    parser.add_argument(
        "--api-fallback", action="store_true",
        help="Fetch missing historical data from OANDA API if local data is unavailable"
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
        # ── Candle-history mode ───────────────────────────────────────
        run_candle_history_mode(
            days=args.days,
            balance=args.balance,
            symbols_filter=syms,
            start_date_str=args.start_date,
            end_date_str=args.end_date,
            api_fallback=args.api_fallback,
            strategy_override=args.strategy,
        )


if __name__ == "__main__":
    main()


