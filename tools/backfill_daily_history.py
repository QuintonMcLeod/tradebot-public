#!/usr/bin/env python3
"""Fetch deep daily (and 4h) history from OANDA for research.

One request returns up to 5000 daily candles — more than thirteen years — which
is enough history to test calendar and momentum effects with real statistical
power. The M5 store covers twelve months; that is plenty for intraday work but
far too short to establish a daily effect, where roughly 250 observations a year
across correlated pairs still collapses to a few hundred independent days.

Writes one file per symbol per granularity:
    <data>/candle_history_daily/<SYMBOL>_D.jsonl
    <data>/candle_history_daily/<SYMBOL>_H4.jsonl
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


def credentials() -> tuple[str, str]:
    from dotenv import dotenv_values
    from tradebot_sci import paths
    from tradebot_sci.config.loader import load_config_json

    cfg = load_config_json()
    oanda = cfg.get("brokers", {}).get("oanda", {}) or {}
    secrets = dotenv_values(paths.SECRETS_FILE) if paths.SECRETS_FILE.exists() else {}
    key = secrets.get("OANDA_API_KEY") or secrets.get("OANDA_API_TOKEN")
    if not key:
        raise SystemExit("No OANDA_API_KEY")
    env = str(oanda.get("environment", "practice")).lower()
    base = "https://api-fxtrade.oanda.com" if "live" in env else "https://api-fxpractice.oanda.com"
    return key, base


def instrument(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("_", "")
    return f"{s[:3]}_{s[3:]}" if len(s) == 6 else s


def fetch(key: str, base: str, instr: str, granularity: str, session: requests.Session,
          start: datetime, end: datetime) -> list[dict]:
    out: list[dict] = []
    cursor = start
    step = {"D": 1, "H4": 1}.get(granularity, 1)
    for _ in range(20):
        if cursor >= end:
            break
        for attempt in range(4):
            r = session.get(f"{base}/v3/instruments/{instr}/candles",
                            params={"granularity": granularity, "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "count": 5000, "price": "M"},
                            headers={"Authorization": f"Bearer {key}"}, timeout=40)
            if r.status_code == 200:
                break
            time.sleep(2.0 * (attempt + 1))
        else:
            break
        candles = r.json().get("candles", [])
        if not candles:
            break
        for c in candles:
            mid = c.get("mid") or {}
            if not mid or not c.get("complete", True):
                continue
            out.append({"t": c["time"].split(".")[0] + "+00:00",
                        "o": float(mid["o"]), "h": float(mid["h"]),
                        "l": float(mid["l"]), "c": float(mid["c"]),
                        "v": float(c.get("volume", 0) or 0)})
        last = datetime.fromisoformat(candles[-1]["time"].split(".")[0] + "+00:00")
        nxt = last + (timedelta(days=1) if granularity == "D" else timedelta(hours=4))
        if nxt <= cursor:
            break
        cursor = nxt
        time.sleep(0.25)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=13)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--out", default="candle_history_daily")
    ap.add_argument("--granularities", default="D,H4")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        from tradebot_sci.config.loader import get_settings
        symbols = list(getattr(get_settings().get_active_profile(), "symbols", None) or ["EURUSD"])

    key, base = credentials()
    out_dir = DATA_DIR / args.out
    (out_dir / "_raw").mkdir(parents=True, exist_ok=True)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * args.years)

    session = requests.Session()
    print(f"[DAILY] {len(symbols)} symbols | {args.granularities} | since {start.date()}", flush=True)
    for i, sym in enumerate(symbols, 1):
        for g in args.granularities.split(","):
            rows = fetch(key, base, instrument(sym), g.strip(), session, start, end)
            if not rows:
                print(f"[DAILY] {sym} {g}: nothing", flush=True)
                continue
            path = out_dir / f"{sym}_{g.strip()}.jsonl"
            with open(path, "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            print(f"[DAILY] {i}/{len(symbols)} {sym} {g}: {len(rows)} candles "
                  f"({rows[0]['t'][:10]} to {rows[-1]['t'][:10]})", flush=True)
    print("[DAILY] complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
