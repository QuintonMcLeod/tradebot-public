#!/usr/bin/env python3
import ccxt
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Target directory for paper_replay.py
DATA_DIR = Path.home() / ".config" / "tradebot-sci" / "data" / "candle_history"
DATA_DIR.mkdir(parents=True, exist_ok=True)

kraken = ccxt.kraken({'enableRateLimit': True})
SYMBOLS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "AUDJPY": "AUD/JPY",
    "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY",
    "NZDUSD": "NZD/USD",
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
            # Don't exceed end_date
            valid = [c for c in candles if c[0] <= end_ms]
            all_candles.extend(valid)
            since = candles[-1][0] + 1
            if since >= end_ms or len(valid) < len(candles): break
        except Exception as e:
            print(f"Error: {e}")
            break
    return all_candles

def main():
    end_date = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=14)  # 14 days for extended backtest
    
    for local_name, ccxt_symbol in SYMBOLS.items():
        candles = download_ohlcv(ccxt_symbol, '5m', start_date, end_date)
        if not candles:
            continue
            
        sym_dir = DATA_DIR / local_name
        sym_dir.mkdir(exist_ok=True)
        
        # Group by day
        from collections import defaultdict
        daily = defaultdict(list)
        for c in candles:
            ts = datetime.fromtimestamp(c[0]/1000, tz=timezone.utc)
            day_str = ts.strftime("%Y-%m-%d")
            # paper_replay format expects: 
            # {"time": "2026-03-08T00:00:27Z", "open": 1.05389, "high": ...
            obs = {
                "time": ts.isoformat().replace("+00:00", "Z"),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5] or 0,
                "complete": True
            }
            daily[day_str].append(obs)
            
        for day_str, obs_list in daily.items():
            out_file = sym_dir / f"{local_name}_{day_str}.jsonl"
            with open(out_file, 'w') as f:
                for obs in obs_list:
                    f.write(json.dumps(obs) + "\n")
            print(f"Saved {len(obs_list)} candles for {local_name} on {day_str}")

if __name__ == "__main__":
    main()
