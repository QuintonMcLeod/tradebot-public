#!/usr/bin/env python3
"""Download Jan 1-15 Forex data from OANDA to extend existing 14-day dataset to 30 days."""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env.secrets manually
env_path = Path("/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/.env.secrets")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            if key.strip() not in os.environ:
                os.environ[key.strip()] = val.strip()

import oandapyV20
import oandapyV20.endpoints.instruments as instruments

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "marathon_30d"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FOREX_SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]

def download_chunk(client, symbol, granularity, start_date, end_date):
    all_data = []
    chunk_start = start_date
    
    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=7), end_date)
        params = {
            "from": chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "granularity": granularity,
            "price": "M"
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            client.request(r)
            candles = r.response.get("candles", [])
            
            for c in candles:
                if not c.get("complete"):
                    continue
                mid = c.get("mid")
                ts_str = c["time"].split(".")[0] + "Z"
                all_data.append({
                    "timestamp": ts_str,
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": float(c["volume"])
                })
            
            print(f"  {symbol} {granularity}: {chunk_start.date()} -> {chunk_end.date()} = {len(candles)} (total: {len(all_data)})")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ERROR {symbol} {granularity}: {e}")
            time.sleep(2)
        
        chunk_start = chunk_end
    
    return all_data

def main():
    api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        print("ERROR: No OANDA_API_KEY found in .env.secrets")
        return 1
    
    print(f"API Key: {api_key[:10]}...")
    client = oandapyV20.API(access_token=api_key, environment="live")
    
    # STEP 1: Download Jan 1-15 (the new chunk)
    new_start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    new_end = datetime(2026, 1, 15, 22, 30, 0, tzinfo=timezone.utc)
    
    print(f"\n=== STEP 1: Downloading Jan 1-15 from OANDA ===")
    
    for sym in FOREX_SYMBOLS:
        for gran, label in [("M5", "5m"), ("M15", "15m")]:
            data = download_chunk(client, sym, gran, new_start, new_end)
            if data:
                fname = f"{sym.replace('_', '')}_{label}_jan1_15.json"
                with open(DATA_DIR / fname, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"  -> Saved {len(data)} candles to {fname}")
    
    # STEP 2: Merge with existing marathon data (Jan 15-29)
    print(f"\n=== STEP 2: Merging with existing marathon data (Jan 15-29) ===")
    marathon_dir = Path(__file__).resolve().parents[1] / "data" / "marathon"
    
    for sym in FOREX_SYMBOLS:
        clean_sym = sym.replace('_', '')
        for label in ["5m", "15m"]:
            # Load new Jan 1-15 data
            new_path = DATA_DIR / f"{clean_sym}_{label}_jan1_15.json"
            if not new_path.exists():
                print(f"  SKIP {clean_sym}_{label} - no new data")
                continue
            
            with open(new_path) as f:
                new_data = json.load(f)
            
            # Load existing Jan 15-29 data
            old_path = marathon_dir / f"{clean_sym}_{label}.json"
            if not old_path.exists():
                print(f"  SKIP {clean_sym}_{label} - no old marathon data")
                continue
            
            with open(old_path) as f:
                old_data = json.load(f)
            
            # Merge and deduplicate by timestamp
            combined = {d["timestamp"]: d for d in new_data}
            for d in old_data:
                combined[d["timestamp"]] = d  # Old data overwrites on overlap
            
            merged = sorted(combined.values(), key=lambda x: x["timestamp"])
            
            # Save merged file
            merged_path = DATA_DIR / f"{clean_sym}_{label}.json"
            with open(merged_path, "w") as f:
                json.dump(merged, f, indent=2)
            
            first_ts = merged[0]["timestamp"][:19]
            last_ts = merged[-1]["timestamp"][:19]
            print(f"  {clean_sym}_{label}: {len(new_data)} + {len(old_data)} = {len(merged)} merged | {first_ts} -> {last_ts}")
    
    print("\n=== DONE ===")

if __name__ == "__main__":
    main()
