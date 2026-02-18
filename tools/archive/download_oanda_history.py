
#!/usr/bin/env python3
"""Download Forex data from OANDA for backtesting."""

import os
import json
import logging
import sys
from datetime import datetime, timezone

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv not found, assuming env vars are set")

import oandapyV20
import oandapyV20.endpoints.instruments as instruments

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data/forex_backtest")

SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "USD_CHF"]

def main():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    account_id = os.getenv("OANDA_ACCOUNT_ID")
    api_key = os.getenv("OANDA_API_KEY")
    env = os.getenv("OANDA_ENVIRONMENT", "practice")

    if not api_key or not account_id:
        print("Error: OANDA credentials missing. Check .env file.")
        print(f"OANDA_ACCOUNT_ID={account_id}")
        return

    print(f"Connecting to OANDA ({env})...")
    client = oandapyV20.API(access_token=api_key, environment=env)

    # Date Range: Jan 19 08:00 EST is 13:00 UTC.
    # We want data covering this.
    # Start Fetch: Jan 18 to Jan 20.
    start_str = "2026-01-18T00:00:00Z"
    end_str = "2026-01-20T00:00:00Z"

    print("=" * 60)
    print("DOWNLOADING FOREX DATA FROM OANDA (Jan 19)")
    print("=" * 60)

    for sym in SYMBOLS:
        print(f"Fetching {sym}...")
        params = {
            "from": start_str,
            "to": end_str,
            "granularity": "M5",
            "price": "M"
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=sym, params=params)
            client.request(r)
            candles = r.response.get("candles", [])
            print(f"  Fetched {len(candles)} candles.")
            
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
            
            # Save as 'EURUSD_5m.json'
            filename = sym.replace("_", "") + "_5m.json"
            filepath = os.path.join(DATA_DIR, filename)
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  Saved to {filepath}")

        except Exception as e:
            print(f"  Failed: {e}")

    print("Done.")

if __name__ == "__main__":
    main()
