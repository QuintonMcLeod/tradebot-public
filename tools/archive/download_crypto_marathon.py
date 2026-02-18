#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.utils.downloader import ensure_data_exists

def main():
    symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"]
    timeframe = "5m"
    
    # Range: Last 30 days
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 31, tzinfo=timezone.utc)
    
    data_dir = Path(__file__).resolve().parents[1] / "data" / "crypto_marathon"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"=== DOWNLOADING 30-DAY CRYPTO DATA ===")
    print(f"Range: {start_date} to {end_date}")
    print(f"Target: {data_dir}")
    
    for symbol in symbols:
        print(f"\nProcessing {symbol}...")
        # ensure_data_exists handles the download if missing
        success = ensure_data_exists(symbol, timeframe, start_date, end_date, str(data_dir))
        if success:
            print(f"  [SUCCESS] {symbol} ready.")
        else:
            print(f"  [FAILURE] {symbol} failed.")

if __name__ == "__main__":
    main()
