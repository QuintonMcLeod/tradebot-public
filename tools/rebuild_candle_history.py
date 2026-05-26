#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

def fetch_candles(client, pair, granularity, count):
    print(f"Fetching {pair} {granularity} (count={count})...")
    params = {"granularity": granularity, "count": str(min(count, 5000))}
    try:
        r = InstrumentsCandles(instrument=pair, params=params)
        client.request(r)
        candles = []
        for c in r.response.get("candles", []):
            if c.get("complete", True):
                mid = c.get("mid", {})
                ts_str = c["time"].replace(".000000000Z", "+00:00").replace("Z", "+00:00")
                candles.append({
                    "t": ts_str,
                    "o": float(mid.get("o", 0)),
                    "h": float(mid.get("h", 0)),
                    "l": float(mid.get("l", 0)),
                    "c": float(mid.get("c", 0)),
                    "v": int(c.get("volume", 0)),
                })
        return candles
    except Exception as e:
        print(f"Error fetching {pair} {granularity}: {e}")
        return []

def main():
    api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        print("ERROR: Set OANDA_API_KEY env var")
        sys.exit(1)

    # Use live environment for this key
    environment = "live"
    client = API(access_token=api_key, environment=environment)
    print(f"OANDA {environment} connected.")

    gui_data_dir = Path.home() / ".config" / "tradebot-sci-gui" / "local" / "data" / "candle_history"
    gui_data_dir.mkdir(parents=True, exist_ok=True)

    pair = "EUR_USD"
    sym = "EURUSD"
    
    raw_m1 = fetch_candles(client, pair, "M1", 5000)
    raw_m5 = fetch_candles(client, pair, "M5", 5000)
    raw_h1 = fetch_candles(client, pair, "H1", 5000)
    raw_h4 = fetch_candles(client, pair, "H4", 5000)

    if not raw_m5:
        print("Failed to fetch M5 data.")
        sys.exit(1)

    obs = []
    for c_m5 in raw_m5:
        c_ts = c_m5["t"]
        # Find matching HTF (<= c_ts)
        valid_m1 = [c for c in raw_m1 if c["t"] >= c_ts and c["t"] < c_ts.replace("00+00:00", "05+00:00")]
        valid_h1 = [c for c in raw_h1 if c["t"] <= c_ts]
        valid_h4 = [c for c in raw_h4 if c["t"] <= c_ts]

        synth_obs = {
            "sym": sym,
            "tf": "5m",
            "htf_tf": "4h",
            "ltf_tf": "5m",
            "ltf": [c_m5],
            "htf": valid_h4[-1:] if valid_h4 else [],
            "mtf": valid_h1[-1:] if valid_h1 else [],
            "xtf": valid_m1,
            "ts": c_ts
        }
        obs.append(synth_obs)

    by_day = {}
    for snap in obs:
        day_str = snap["ts"].split("T")[0]
        by_day.setdefault(day_str, []).append(snap)

    sym_dir = gui_data_dir / sym
    if sym_dir.exists():
        for f in sym_dir.glob("*.jsonl"):
            f.unlink()
    sym_dir.mkdir(parents=True, exist_ok=True)

    for day_str, snaps in by_day.items():
        out_path = sym_dir / f"{sym}_{day_str}.jsonl"
        with open(out_path, "w") as f:
            for s in snaps:
                f.write(json.dumps(s) + "\n")
    print(f"[{sym}] wrote {len(obs)} obs across {len(by_day)} days to {sym_dir}.")

if __name__ == "__main__":
    main()
