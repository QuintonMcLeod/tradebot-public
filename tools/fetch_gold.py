#!/usr/bin/env python3
import ccxt
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Kraken has PAXG/USD
kraken = ccxt.kraken({'enableRateLimit': True})
SYMBOLS = {
    "PAXGUSD": "PAXG/USD",
    "EURUSD": "EUR/USD",
}

def download_ohlcv(symbol, timeframe, start_date, end_date):
    all_candles = []
    since = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    print(f"Downloading {symbol} {timeframe} until {end_date}...")
    while since < end_ms:
        try:
            candles = kraken.fetch_ohlcv(symbol, timeframe, since=since, limit=1440)
            if not candles: break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            if since >= end_ms: break
            import time
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            break
    return [c for c in all_candles if c[0] < end_ms]

def main():
    end_date = datetime(2026, 1, 30, 0, 0, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=21)
    for local_name, ccxt_symbol in SYMBOLS.items():
        candles = download_ohlcv(ccxt_symbol, '15m', start_date, end_date)
        if candles:
            data = [{"timestamp": datetime.fromtimestamp(c[0]/1000, tz=timezone.utc).isoformat(),
                     "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5] or 0} for c in candles]
            with open(DATA_DIR / f"{local_name}_15m.json", 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Saved {len(data)} candles (15m) for {local_name}")

if __name__ == "__main__":
    main()
