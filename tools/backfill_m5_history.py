#!/usr/bin/env python3
"""Backfill deep M5 history for the replay harness.

The older backfill_history.py stores a rolling 30-candle window inside every
single tick observation, which costs roughly thirty times the space for data the
replay never reads — the replay builds its timeline straight from the candle
arrays. This stores one record per symbol per day instead:

    {"sym": "EURUSD", "tf": "5m", "ltf_tf": "5m",
     "ltf": [{"t": "...", "o": .., "h": .., "l": .., "c": .., "v": .., "sp": ..}, ...],
     "ts": "<last candle time>"}

Requests ask for mid + bid + ask in one call, so the spread actually quoted at
each candle is kept. tools/paper_replay.py resamples the higher timeframes from
the M5 series itself, so M5 is the only granularity that needs fetching.

Usage:
    python3 tools/backfill_m5_history.py --months 12
    python3 tools/backfill_m5_history.py --start 2025-09-01 --end 2026-09-01 --symbols EURUSD,GBPUSD
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

GRANULARITY = "M5"
STEP_MINUTES = 5
MAX_CANDLES = 5000        # OANDA's per-request ceiling
REQUEST_PAUSE = 0.25      # conservative; OANDA permits far more
MAX_BATCHES_PER_SYMBOL = 400


def _credentials() -> tuple[str, str]:
    """Return (api_key, base_url) using the same sources as the bot."""
    from dotenv import dotenv_values
    from tradebot_sci import paths
    from tradebot_sci.config.loader import load_config_json

    cfg = load_config_json()
    oanda = cfg.get("brokers", {}).get("oanda", {}) or {}
    secrets = dotenv_values(paths.SECRETS_FILE) if paths.SECRETS_FILE.exists() else {}
    key = secrets.get("OANDA_API_KEY") or secrets.get("OANDA_API_TOKEN")
    if not key:
        raise SystemExit("No OANDA_API_KEY in the secrets file")
    env = str(oanda.get("environment", "practice")).lower()
    base = "https://api-fxtrade.oanda.com" if "live" in env else "https://api-fxpractice.oanda.com"
    return key, base


def _instrument(symbol: str) -> str:
    """EURUSD -> EUR_USD."""
    s = symbol.upper().replace("/", "").replace("_", "")
    return f"{s[:3]}_{s[3:]}" if len(s) == 6 else s


def _clean_time(raw: str) -> str:
    """OANDA returns nanosecond precision; keep a plain ISO string."""
    return raw.split(".")[0] + "+00:00"


def fetch_symbol(key: str, base: str, instrument: str, start: datetime,
                 end: datetime, session: requests.Session) -> list[dict]:
    """Page M5 candles through [start, end]."""
    out: list[dict] = []
    cursor = start
    for _ in range(MAX_BATCHES_PER_SYMBOL):
        if cursor >= end:
            break
        try:
            r = session.get(
                f"{base}/v3/instruments/{instrument}/candles",
                params={
                    "granularity": GRANULARITY,
                    "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "count": MAX_CANDLES,
                    "price": "MBA",
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"    transient error at {cursor}: {exc}", flush=True)
            time.sleep(2.0)
            continue
        if r.status_code != 200:
            print(f"    HTTP {r.status_code} at {cursor}: {r.text[:160]}", flush=True)
            break
        candles = r.json().get("candles", [])
        if not candles:
            break
        for c in candles:
            if not c.get("complete"):
                continue
            mid = c.get("mid") or {}
            if not mid:
                continue
            bid, ask = c.get("bid") or {}, c.get("ask") or {}
            spread = None
            if bid.get("c") is not None and ask.get("c") is not None:
                spread = round(float(ask["c"]) - float(bid["c"]), 6)
            out.append({
                "t": _clean_time(c["time"]),
                "o": float(mid["o"]), "h": float(mid["h"]),
                "l": float(mid["l"]), "c": float(mid["c"]),
                "v": float(c.get("volume", 0) or 0),
                "sp": spread,
            })
        last = datetime.fromisoformat(_clean_time(candles[-1]["time"]))
        nxt = last + timedelta(minutes=STEP_MINUTES)
        if nxt <= cursor:
            break
        cursor = nxt
        time.sleep(REQUEST_PAUSE)
    return out


def write_days(out_dir: Path, symbol: str, candles: list[dict], force: bool) -> int:
    """Write one file per day in the recorder's schema."""
    by_day: dict[str, list[dict]] = {}
    for c in candles:
        by_day.setdefault(c["t"][:10], []).append(c)

    sym_dir = out_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for day, rows in sorted(by_day.items()):
        path = sym_dir / f"{symbol}_{day}.jsonl"
        if path.exists() and not force and path.stat().st_size > 0:
            continue
        rows.sort(key=lambda r: r["t"])
        with open(path, "w") as fh:
            fh.write(json.dumps({
                "sym": symbol, "tf": "5m", "ltf_tf": "5m",
                "ltf": rows, "ts": rows[-1]["t"],
            }) + "\n")
        written += 1
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill M5 history for paper_replay.")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD, overrides --months")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD, default today")
    ap.add_argument("--symbols", type=str, default=None, help="Comma list; default active profile")
    ap.add_argument("--out", type=str, default="candle_history_backfill",
                    help="Directory under the bot's data dir")
    ap.add_argument("--force", action="store_true", help="Rewrite existing days")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR

    end = (datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
           if args.end else datetime.now(timezone.utc))
    start = (datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
             if args.start else end - timedelta(days=30 * args.months))

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        from tradebot_sci.config.loader import get_settings
        profile = get_settings().get_active_profile()
        symbols = list(getattr(profile, "symbols", None) or ["EURUSD"])

    key, base = _credentials()
    out_dir = DATA_DIR / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[BACKFILL] {len(symbols)} symbols | M5 | {start.date()} to {end.date()}", flush=True)
    print(f"[BACKFILL] writing to {out_dir}", flush=True)

    session = requests.Session()
    total_candles = total_files = 0
    for i, sym in enumerate(symbols, 1):
        t0 = time.time()
        candles = fetch_symbol(key, base, _instrument(sym), start, end, session)
        if not candles:
            print(f"[BACKFILL] {i}/{len(symbols)} {sym}: nothing returned", flush=True)
            continue
        files = write_days(out_dir, sym, candles, args.force)
        total_candles += len(candles)
        total_files += files
        spreads = sorted(c["sp"] for c in candles if c.get("sp"))
        med = f"{spreads[len(spreads) // 2]:.5f}" if spreads else "n/a"
        print(f"[BACKFILL] {i}/{len(symbols)} {sym}: {len(candles)} candles, "
              f"{files} files, median spread {med}, {time.time() - t0:.0f}s", flush=True)

    print(f"[BACKFILL] complete: {total_candles} candles, {total_files} files", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
