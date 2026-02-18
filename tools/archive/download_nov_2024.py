#!/usr/bin/env python3
"""Download Nov 2024 Crypto/Gold data for backtest comparison.

Downloads 15m candles from Coinbase for major crypto/gold assets:
Nov 1, 2024 - Dec 1, 2024 (The "Election Pump" Month)
"""

import ccxt
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Save to same directory as Jan 2026 data
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "nov_2024"

# Only major assets as requested
SYMBOLS = {
    # Crypto
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    # Gold (PAXG as proxy on Coinbase)
    "PAXGUSD": "PAXG/USD",
    "XAUUSD": "PAXG/USD",  # Alias
}

def download_ohlcv(exchange, symbol, timeframe, start_date, end_date):
    """Download OHLCV data from exchange."""
    all_candles = []
    since = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)

    print(f"Downloading {symbol} {timeframe} from {start_date} to {end_date}...")

    while since < end_ms:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=300)
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            print(f"  Fetched {len(all_candles)} candles so far...", end='\r')
        except Exception as e:
            print(f"  Error: {e}")
            break
            
    print() # Newline
    return all_candles

def save_candles(candles, filename):
    """Save candles to JSON file."""
    data = []
    for c in candles:
        ts = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc)
        data.append({
            "timestamp": ts.isoformat(),
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5] or 0,
        })

    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} candles to {filepath}")

def main():
    # Create distinct directory for Nov 2024
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Date range: Nov 2024 (Election Month)
    start_date = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 12, 1, tzinfo=timezone.utc)

    # Initialize Coinbase
    coinbase = ccxt.coinbase({
        'enableRateLimit': True,
    })

    print("=" * 60)
    print("DOWNLOADING NOV 2024 DATA (TRENDING)")
    print("=" * 60)
    
    for local_name, ccxt_symbol in SYMBOLS.items():
        try:
            # Download 15m candles (Standard backtest timeframe)
            candles_15m = download_ohlcv(coinbase, ccxt_symbol, '15m', start_date, end_date)
            if candles_15m:
                save_candles(candles_15m, f"{local_name}_15m.json")

        except Exception as e:
            print(f"Failed to download {local_name}: {e}")

    print("\nDone!")

if __name__ == "__main__":
    main()
