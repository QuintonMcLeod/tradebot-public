#!/usr/bin/env python3
"""
backfill_history.py — Historical Candle Backfill for paper_replay.py

Fetches N days of 5m + 4h Oanda candle data for all active symbols and
writes them into the candle_history JSONL format that paper_replay reads.

After running this, paper_replay will have months of data to work with,
producing statistically meaningful trade counts instead of ~1/symbol.

Usage:
    python tools/backfill_history.py [--days 90] [--symbols EURUSD,GBPUSD]
    python tools/backfill_history.py --days 90   # all forex symbols
    python tools/backfill_history.py --days 30 --symbols EURUSD,XAUUSD
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_repo = Path(__file__).resolve().parents[1]
_src  = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")

# ── Config ────────────────────────────────────────────────────────────────────
_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tradebot-sci"
_CANDLE_DIR = _CONFIG_DIR / "data" / "candle_history"

# Oanda API limits: max 5000 candles per request for M5
_BATCH_SIZE  = 5000
_LTF_TF      = "M5"
_HTF_TF      = "H4"
_LTF_KEY     = "5m"
_HTF_KEY     = "4h"

# Default symbols (matches live forex_continuous profile)
_DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY",
    "XAUUSD",
]

# Rate limiting — Oanda allows 100 req/s but be conservative
_SLEEP_BETWEEN_BATCHES = 0.3   # seconds


def _normalize_symbol(symbol: str) -> str:
    sym = symbol.upper().replace("/", "").replace("-", "")
    if len(sym) == 6:
        return f"{sym[:3]}_{sym[3:]}"
    if sym.endswith("USD") and len(sym) > 3:
        return f"{sym[:-3]}_{sym[-3:]}"
    return sym


def _parse_oanda_time(raw_time: str) -> datetime:
    if "." in raw_time:
        base, rest = raw_time.split(".", 1)
        suffix = ""
        if "Z" in rest:
            suffix = "Z"; rest = rest.replace("Z", "")
        elif "+" in rest:
            rest, offset = rest.split("+", 1); suffix = "+" + offset
        elif rest.count("-") > 0:
            parts = rest.split("-"); rest = parts[0]; suffix = "-" + parts[1]
        raw_time = f"{base}.{rest[:6]}{suffix}"
    if raw_time.endswith("Z"):
        raw_time = raw_time[:-1] + "+00:00"
    return datetime.fromisoformat(raw_time).astimezone(timezone.utc)


def fetch_candles_range(
    client,
    oanda_sym: str,
    granularity: str,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    """Paginate Oanda to fetch all candles in [from_dt, to_dt].
    Uses from+to params only (count cannot coexist with from+to on Oanda API).
    """
    import oandapyV20.endpoints.instruments as instruments

    # Batch window: 5000 candles × granularity duration
    granularity_minutes = {"M5": 5, "H4": 240}.get(granularity, 5)
    batch_delta = timedelta(minutes=granularity_minutes * _BATCH_SIZE)

    all_candles = []
    cursor = from_dt

    while cursor < to_dt:
        batch_to = min(to_dt, cursor + batch_delta)
        params = {
            "granularity": granularity,
            "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":   batch_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": "M",
            # NOTE: do NOT include 'count' — Oanda rejects it when from+to are set
        }
        try:
            r = instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
            client.request(r)
            raw = r.response.get("candles", [])
        except Exception as exc:
            logger.warning(f"  Fetch error for {oanda_sym} {granularity} at {cursor}: {exc}")
            time.sleep(2)
            break

        if not raw:
            cursor = batch_to
            continue

        for c in raw:
            mid = c.get("mid")
            if not mid or not c.get("complete", True):
                continue
            ts = _parse_oanda_time(c["time"])
            all_candles.append({
                "t": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "o": float(mid["o"]),
                "h": float(mid["h"]),
                "l": float(mid["l"]),
                "c": float(mid["c"]),
                "v": float(c.get("volume", 0)),
            })

        # Advance cursor past the last received candle
        last_ts = _parse_oanda_time(raw[-1]["time"])
        cursor = last_ts + timedelta(minutes=granularity_minutes)
        time.sleep(_SLEEP_BETWEEN_BATCHES)

    return all_candles


def build_observations(
    sym: str,
    ltf_candles: list[dict],
    htf_candles: list[dict],
) -> dict[str, list[dict]]:
    """
    Convert a flat list of LTF candles into per-date observations (one per LTF candle).
    Each observation carries the LAST 30 LTF + last 10 HTF candles visible at that tick.
    Groups by date for file writing (one JSONL file per date).
    """
    import bisect

    htf_times = [c["t"] for c in htf_candles]

    by_date: dict[str, list[dict]] = {}
    for i, candle in enumerate(ltf_candles):
        ts_str = candle["t"]
        date_str = ts_str[:10]  # YYYY-MM-DD

        # Rolling window: last 30 LTF visible at this tick
        ltf_window = ltf_candles[max(0, i - 29): i + 1]

        # HTF: all 4h candles up to this tick's timestamp
        idx = bisect.bisect_right(htf_times, ts_str)
        htf_window = htf_candles[max(0, idx - 10): idx]

        obs = {
            "ts":     ts_str,
            "sym":    sym,
            "tf":     _LTF_KEY,
            "htf_tf": _HTF_KEY,
            "ltf_tf": _LTF_KEY,
            "ltf":    ltf_window,
            "htf":    htf_window,
        }

        by_date.setdefault(date_str, []).append(obs)

    return by_date


def write_observations(sym: str, by_date: dict[str, list[dict]]) -> int:
    """Write per-date JSONL files. Returns total observations written."""
    sym_dir = _CANDLE_DIR / sym
    sym_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for date_str, obs_list in sorted(by_date.items()):
        path = sym_dir / f"{sym}_{date_str}.jsonl"
        with open(path, "w") as f:
            for obs in obs_list:
                f.write(json.dumps(obs) + "\n")
        total += len(obs_list)

    return total


def backfill_symbol(client, sym: str, days: int) -> int:
    oanda_sym = _normalize_symbol(sym)
    to_dt   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    from_dt = to_dt - timedelta(days=days)

    logger.info(f"[{sym}] Fetching LTF {_LTF_TF} from {from_dt.date()} → {to_dt.date()}")
    ltf = fetch_candles_range(client, oanda_sym, _LTF_TF, from_dt, to_dt)
    logger.info(f"[{sym}] Got {len(ltf)} LTF candles")

    if not ltf:
        logger.warning(f"[{sym}] No LTF data — skipping")
        return 0

    logger.info(f"[{sym}] Fetching HTF {_HTF_TF}")
    htf = fetch_candles_range(client, oanda_sym, _HTF_TF, from_dt, to_dt)
    logger.info(f"[{sym}] Got {len(htf)} HTF candles")

    by_date = build_observations(sym, ltf, htf)
    total   = write_observations(sym, by_date)
    logger.info(f"[{sym}] ✅ Wrote {total} observations across {len(by_date)} days")
    return total


def main():
    parser = argparse.ArgumentParser(description="Backfill candle_history for paper_replay.py")
    parser.add_argument("--days",    type=int, default=90,
                        help="Days of history to fetch (default: 90)")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbols (default: all forex pairs)")
    args = parser.parse_args()

    syms = ([s.strip().upper() for s in args.symbols.split(",")]
            if args.symbols else _DEFAULT_SYMBOLS)

    logger.info(f"[BACKFILL] Starting — {args.days} days for {len(syms)} symbols: {syms}")
    logger.info(f"[BACKFILL] Output: {_CANDLE_DIR}")

    # Load credentials from tradebot settings
    from tradebot_sci.config.loader import get_settings
    import oandapyV20
    settings = get_settings()
    oanda_cfg = getattr(settings, "oanda", None)
    if oanda_cfg:
        api_key    = oanda_cfg.api_key
        account_id = oanda_cfg.account_id
        env        = oanda_cfg.environment
    else:
        api_key    = getattr(settings, "api_key", "")
        account_id = getattr(settings, "account_id", "")
        env        = getattr(settings, "environment", "practice")

    if not api_key:
        logger.error("[BACKFILL] No API key found in settings. Aborting.")
        sys.exit(1)

    client = oandapyV20.API(access_token=api_key, environment=env)
    logger.info(f"[BACKFILL] Connected to Oanda ({env}) account {account_id}")

    start_real = time.time()
    grand_total = 0
    for sym in syms:
        try:
            n = backfill_symbol(client, sym, args.days)
            grand_total += n
        except Exception as exc:
            logger.error(f"[{sym}] FAILED: {exc}")

    elapsed = time.time() - start_real
    logger.info(f"[BACKFILL] Done in {elapsed:.1f}s — {grand_total:,} total observations written")
    logger.info(f"[BACKFILL] Run `python tools/paper_replay.py --days {args.days}` to replay")


if __name__ == "__main__":
    main()
