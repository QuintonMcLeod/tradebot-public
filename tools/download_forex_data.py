#!/usr/bin/env python3
"""Download Forex/Crypto data from Coinbase for backtesting."""

import ccxt
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"

# Coinbase symbols - expanded to match bot's 11 asset scan
# Crypto + tokenized commodities available on Coinbase
SYMBOLS = {
    # Crypto (direct)
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    "AVAXUSD": "AVAX/USD",
    "ADAUSD": "ADA/USD",
    "DOGEUSD": "DOGE/USD",
    "LINKUSD": "LINK/USD",
    "LTCUSD": "LTC/USD",
    "SHIBUSD": "SHIB/USD",
    # Tokenized Gold (proxy for XAUUSD)
    "PAXGUSD": "PAXG/USD",
    "XAUUSD": "PAXG/USD",  # Alias for gold
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
            print(f"  Fetched {len(all_candles)} candles so far...")
        except Exception as e:
            print(f"  Error: {e}")
            break

    return all_candles

def save_candles(candles, filename, symbol):
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
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Date range: First 3 weeks of January 2026
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 19, tzinfo=timezone.utc)

    # Initialize Coinbase exchange for crypto
    coinbase = ccxt.coinbase({
        'enableRateLimit': True,
    })

    print("=" * 60)
    print("DOWNLOADING CRYPTO DATA FROM COINBASE")
    print("=" * 60)
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Symbols: {list(SYMBOLS.keys())}")
    print()

    for local_name, ccxt_symbol in SYMBOLS.items():
        try:
            # Download 15m candles
            candles_15m = download_ohlcv(coinbase, ccxt_symbol, '15m', start_date, end_date)
            if candles_15m:
                save_candles(candles_15m, f"{local_name}_15m.json", local_name)

            # Download 5m candles
            candles_5m = download_ohlcv(coinbase, ccxt_symbol, '5m', start_date, end_date)
            if candles_5m:
                save_candles(candles_5m, f"{local_name}_5m.json", local_name)

        except Exception as e:
            print(f"Failed to download {local_name}: {e}")

    # Try Kraken for Forex pairs
    print("\n" + "=" * 60)
    print("DOWNLOADING FOREX DATA FROM KRAKEN")
    print("=" * 60)

    kraken = ccxt.kraken({
        'enableRateLimit': True,
    })

    # Kraken forex pairs (they have EUR/USD, GBP/USD, etc.)
    FOREX_SYMBOLS = {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "AUDUSD": "AUD/USD",
    }

    print(f"Symbols: {list(FOREX_SYMBOLS.keys())}")
    print()

    for local_name, ccxt_symbol in FOREX_SYMBOLS.items():
        try:
            # Download 15m candles
            candles_15m = download_ohlcv(kraken, ccxt_symbol, '15m', start_date, end_date)
            if candles_15m:
                save_candles(candles_15m, f"{local_name}_15m.json", local_name)

            # Download 5m candles
            candles_5m = download_ohlcv(kraken, ccxt_symbol, '5m', start_date, end_date)
            if candles_5m:
                save_candles(candles_5m, f"{local_name}_5m.json", local_name)

        except Exception as e:
            print(f"Failed to download {local_name}: {e}")

    print("\nDone!")

if __name__ == "__main__":
    main()
