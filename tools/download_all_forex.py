#!/usr/bin/env python3
"""Download all OANDA forex pairs into data/audit/ for backtesting.

Uses OANDA's 'count' parameter for reliable fetching.
"""
import json, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

DATA_DIR = PROJECT_ROOT / "data" / "audit"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FOREX_PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CHF", "NZD_USD", "USD_CAD",
    "EUR_GBP", "EUR_JPY", "GBP_JPY", "EUR_AUD", "EUR_CAD", "EUR_CHF", "EUR_NZD",
    "GBP_AUD", "GBP_CAD", "GBP_CHF", "GBP_NZD",
    "AUD_CAD", "AUD_CHF", "AUD_JPY", "AUD_NZD",
    "CAD_CHF", "CAD_JPY", "CHF_JPY",
    "NZD_CAD", "NZD_CHF", "NZD_JPY",
]

TIMEFRAMES = {"5m": ("M5", 4000), "15m": ("M15", 1500), "1h": ("H1", 400), "4h": ("H4", 100)}


def fetch_candles(client, pair, granularity, count):
    """Fetch candles using count parameter (most reliable)."""
    params = {"granularity": granularity, "count": str(min(count, 5000))}
    try:
        r = InstrumentsCandles(instrument=pair, params=params)
        client.request(r)
        candles = []
        for c in r.response.get("candles", []):
            if c.get("complete", True):
                mid = c.get("mid", {})
                candles.append({
                    "timestamp": c["time"].replace(".000000000Z", "+00:00").replace("Z", "+00:00"),
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0)),
                })
        return candles
    except Exception as e:
        if "Invalid value" in str(e) or "is not" in str(e):
            return None  # Pair not available
        print(f"    Error: {e}", flush=True)
        return []


def main():
    api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        print("ERROR: Set OANDA_API_KEY env var")
        sys.exit(1)

    cfg_path = Path.home() / ".config" / "tradebot-sci" / "config.json"
    environment = "practice"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        environment = cfg.get("brokers", {}).get("oanda", {}).get("environment", "practice")

    client = API(access_token=api_key, environment=environment)
    print(f"OANDA {environment} connected", flush=True)
    print(f"\n═══ Downloading {len(FOREX_PAIRS)} forex pairs ═══", flush=True)
    print(f"Timeframes: {', '.join(TIMEFRAMES.keys())}", flush=True)
    print(f"Output: {DATA_DIR}\n", flush=True)

    success = 0
    skipped = 0

    for pair in FOREX_PAIRS:
        local_name = pair.replace("_", "")
        pair_ok = False

        for tf_local, (tf_oanda, count) in TIMEFRAMES.items():
            out_file = DATA_DIR / f"{local_name}_{tf_local}.json"
            candles = fetch_candles(client, pair, tf_oanda, count)

            if candles is None:
                print(f"  ⏭️  {local_name}: Not available", flush=True)
                skipped += 1
                break

            if candles:
                with open(out_file, "w") as f:
                    json.dump(candles, f, indent=2)
                print(f"  ✅ {local_name} {tf_local}: {len(candles)} candles", flush=True)
                pair_ok = True

            time.sleep(0.15)

        if pair_ok:
            success += 1

    print(f"\n═══ Done ═══", flush=True)
    print(f"  Downloaded: {success} pairs", flush=True)
    print(f"  Skipped:    {skipped} pairs", flush=True)
    total = sum(1 for _ in DATA_DIR.glob("*_*.json"))
    print(f"  Total files: {total}", flush=True)


if __name__ == "__main__":
    main()
