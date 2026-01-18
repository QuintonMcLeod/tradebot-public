#!/usr/bin/env python3
import ccxt
import json
import os
import time
from datetime import datetime, timezone

# Kraken Symbols Mapping
# Kraken uses "Xbt/Usd" or "EUR/USD" format.
# We map our internal symbol to CCXT symbol.
SYMBOL_MAP = {
    # Forex
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    # "NZDUSD": "NZD/USD", # Kraken might check if listed. usually is.
    
    # Commodities (Crypto Proxies found on Kraken?)
    "XAUUSD": "XAUT/USD", # Tether Gold as proxy for Spot Gold
    # "XAGUSD": "XAG/USD", # Checking...
    "PAXGUSD": "PAXG/USD", # Paxos Gold
}

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')

def fetch_kraken_data():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    print("Initializing Kraken via CCXT...")
    exchange = ccxt.kraken()
    
    try:
        markets = exchange.load_markets()
        print(f"Markets loaded: {len(markets)}")
    except Exception as e:
        print(f"Error loading markets: {e}")
        return

    for internal_sym, kraken_sym in SYMBOL_MAP.items():
        if kraken_sym not in markets:
            print(f"[{internal_sym}] Skipping (Not found on Kraken: {kraken_sym})")
            continue
            
        print(f"[{internal_sym}] Fetching {kraken_sym}...", end=" ", flush=True)
        try:
            # Fetch 15m candles
            # Kraken limit is usually 720 candles. 15m * 720 = 180 hours = 7.5 days. Perfect.
            ohlcv = exchange.fetch_ohlcv(kraken_sym, timeframe='15m', limit=720)
            
            if not ohlcv:
                print("No data.")
                continue
                
            candles = []
            for bar in ohlcv:
                # CCXT structure: [timestamp, open, high, low, close, volume]
                # timestamp is ms
                ts_ms = bar[0]
                dt = datetime.fromtimestamp(ts_ms/1000.0, tz=timezone.utc)
                
                candles.append({
                    "timestamp": dt.isoformat(),
                    "open": bar[1],
                    "high": bar[2],
                    "low": bar[3],
                    "close": bar[4],
                    "volume": bar[5]
                })
                
            outfile = os.path.join(DATA_DIR, f"{internal_sym}_15m.json")
            with open(outfile, 'w') as f:
                json.dump(candles, f, indent=2)
                
            print(f"SUCCESS ({len(candles)} bars)")
            time.sleep(1) # Rate limit
            
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    fetch_kraken_data()
