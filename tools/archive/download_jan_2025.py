#!/usr/bin/env python3
"""Download Jan 2025 Commodity Data for "Wet Feet" Benchmark.

Assets: Gold, Silver, Platinum, Oil, Palladium.
Source: YFinance (Futures Data)
Period: Jan 1, 2025 - Feb 1, 2025
Interval: 1h (Due to YFinance 60-day limit for 15m data)
"""

import yfinance as yf
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Save to "jan_2025" directory
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "jan_2025"

# Commodities (Futures)
SYMBOLS = {
    "PAXGUSD": "GC=F",   # Gold
    "XAGUSD": "SI=F",    # Silver
    "XPTUSD": "PL=F",    # Platinum
    "XPDUSD": "PA=F",    # Palladium
    "USOIL": "CL=F",     # Crude Oil
}

def save_candles(df, filename):
    """Save DataFrame to JSON in the expected format."""
    data = []
    
    for index, row in df.iterrows():
        # index is Timestamp
        data.append({
            "timestamp": index.isoformat(),
            "open": float(row['Open']),
            "high": float(row['High']),
            "low": float(row['Low']),
            "close": float(row['Close']),
            "volume": float(row['Volume']),
        })

    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} candles to {filepath}")

def main():
    # Create distinct directory for Jan 2025
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DOWNLOADING JAN 2025 COMMODITIES (YFINANCE) - 1H INTERVAL")
    print("=" * 60)
    
    start_date = "2025-01-01"
    end_date = "2025-02-01" 
    
    for local_name, yf_symbol in SYMBOLS.items():
        try:
            print(f"Downloading {yf_symbol} ({local_name})...")
            # 1h interval, max 730 days allowed by YF
            df = yf.download(yf_symbol, start=start_date, end=end_date, interval="1h", progress=False)
            
            if not df.empty:
                save_candles(df, f"{local_name}_1h.json")
            else:
                print(f"  [WARNING] No data found for {yf_symbol}")

        except Exception as e:
            print(f"Failed to download {local_name}: {e}")

    print("\nDone!")

if __name__ == "__main__":
    main()
