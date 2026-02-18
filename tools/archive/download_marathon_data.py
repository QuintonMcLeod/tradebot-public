#!/usr/bin/env python3
"""Download the last 2 weeks of Forex and Crypto data for marathon backtesting."""

import os
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import ccxt
import oandapyV20
import oandapyV20.endpoints.instruments as instruments

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("marathon_down")

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "marathon"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 1. Crypto Symbols (Coinbase/Kraken via CCXT)
CRYPTO_SYMBOLS = {
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    "XRPUSD": "XRP/USD",
    "ZECUSD": "ZEC/USD",
    "BCHUSD": "BCH/USD"
}

# 2. Forex Symbols (OANDA)
FOREX_SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]

def download_ohlcv_ccxt(exchange, symbol, timeframe, start_date, end_date):
    all_candles = []
    since = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)

    print(f"Downloading {symbol} {timeframe} from {start_date} to {end_date} (CCXT)...")

    while since < end_ms:
        try:
            time.sleep(1.2)
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles:
                break
            
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            print(f"  Fetched {len(all_candles)} candles... Last: {datetime.fromtimestamp(candles[-1][0]/1000, tz=timezone.utc)}")
            
            if since >= end_ms:
                break
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
            continue
    return all_candles

def download_ohlcv_oanda(client, symbol, granularity, start_date, end_date):
    print(f"Downloading {symbol} {granularity} from {start_date} to {end_date} (OANDA)...")
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    params = {
        "from": start_str,
        "to": end_str,
        "granularity": granularity,
        "price": "M"
    }
    
    try:
        r = instruments.InstrumentsCandles(instrument=symbol, params=params)
        client.request(r)
        candles = r.response.get("candles", [])
        
        data = []
        for c in candles:
            if not c.get("complete"): continue
            mid = c.get("mid")
            ts_str = c["time"].split(".")[0] + "Z"
            
            data.append({
                "timestamp": ts_str,
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": float(c["volume"])
            })
        return data
    except Exception as e:
        print(f"  Failed {symbol}: {e}")
        return []

def save_to_json(data, filename):
    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} items to {filepath}")

def main():
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=14)
    
    print(f"Marathon Window: {start_date} -> {end_date}")

    # --- FOREX (OANDA) ---
    api_key = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENVIRONMENT", "practice")
    
    if api_key and account_id:
        print("\n--- FETCHING FOREX (OANDA) ---")
        client = oandapyV20.API(access_token=api_key, environment=env)
        for sym in FOREX_SYMBOLS:
            # 5m data for backtest
            data = download_ohlcv_oanda(client, sym, "M5", start_date, end_date)
            if data:
                save_to_json(data, f"{sym.replace('_', '')}_5m.json")
            
            # 15m data for HTF
            data_15 = download_ohlcv_oanda(client, sym, "M15", start_date, end_date)
            if data_15:
                save_to_json(data_15, f"{sym.replace('_', '')}_15m.json")

    # --- CRYPTO (KRAKEN) ---
    print("\n--- FETCHING CRYPTO (KRAKEN) ---")
    kraken = ccxt.kraken({'enableRateLimit': True})
    for local_name, ccxt_symbol in CRYPTO_SYMBOLS.items():
        # 5m candles
        candles = download_ohlcv_ccxt(kraken, ccxt_symbol, '5m', start_date, end_date)
        if candles:
            formatted = []
            for c in candles:
                ts = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc)
                formatted.append({
                    "timestamp": ts.isoformat(),
                    "open": c[1],
                    "high": c[2],
                    "low": c[3],
                    "close": c[4],
                    "volume": c[5] or 0,
                })
            save_to_json(formatted, f"{local_name}_5m.json")

    print("\nMarathon Data Download Complete!")

if __name__ == "__main__":
    main()
