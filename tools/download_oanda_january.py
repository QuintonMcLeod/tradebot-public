
#!/usr/bin/env python3
"""Download Full January 2026 Forex data from OANDA."""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta
import dateutil.parser

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import oandapyV20
import oandapyV20.endpoints.instruments as instruments

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data/forex_backtest")
SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "USD_CHF"]

def datetime_to_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

def main():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    account_id = os.getenv("OANDA_ACCOUNT_ID")
    api_key = os.getenv("OANDA_API_KEY")
    env = os.getenv("OANDA_ENVIRONMENT", "practice")

    if not api_key or not account_id:
        print("Error: OANDA credentials missing.")
        return

    client = oandapyV20.API(access_token=api_key, environment=env)

    # Full January Range
    start_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 1, 26, tzinfo=timezone.utc) # Up to 26th to cover full 25th

    print("=" * 60)
    print("DOWNLOADING JAN 1 - JAN 25 FOREX DATA (OANDA)")
    print("=" * 60)

    for sym in SYMBOLS:
        print(f"Fetching {sym}...")
        all_candles = []
        current_start = start_dt
        
        while current_start < end_dt:
            # Request in chunks of 4 days to stay well under 5000 candle limit (4 * 288 = 1152)
            # OANDA limit is 5000. 10 days is 2880. Let's do 7 days.
            chunk_end = min(current_start + timedelta(days=7), end_dt)
            
            params = {
                "from": datetime_to_iso(current_start),
                "to": datetime_to_iso(chunk_end),
                "granularity": "M5",
                "price": "M"
            }
            
            try:
                r = instruments.InstrumentsCandles(instrument=sym, params=params)
                client.request(r)
                chunk = r.response.get("candles", [])
                
                if not chunk:
                    print(f"  No data for chunk {params['from']} -> {params['to']}")
                else:
                    print(f"  Fetched {len(chunk)} candles ({params['from']} -> {params['to']})")
                    all_candles.extend(chunk)
                
            except Exception as e:
                print(f"  Failed chunk: {e}")
            
            current_start = chunk_end
            time.sleep(0.5) # Rate limit courtesy
            
        # Process and Save
        data = []
        for c in all_candles:
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
        
        # Deduplicate by timestamp (just in case of overlap)
        unique_data = {d["timestamp"]: d for d in data}
        sorted_data = sorted(unique_data.values(), key=lambda x: x["timestamp"])
        
        filename = sym.replace("_", "") + "_5m.json"
        filepath = os.path.join(DATA_DIR, filename)
        
        with open(filepath, 'w') as f:
            json.dump(sorted_data, f, indent=2)
        print(f"  Saved {len(sorted_data)} total candles to {filepath}")

    print("Done.")

if __name__ == "__main__":
    main()
