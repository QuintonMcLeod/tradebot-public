import os
import json
from pathlib import Path
from datetime import datetime, timezone

def _fmt(c):
    # c format: {'timestamp': '2026-02-13T00:00:00+00:00', 'open': 1.1869, ...}
    ts_str = c["timestamp"]
    if "+00:00" in ts_str:
        ts_str = ts_str.replace("+00:00", ".000000Z")
    elif not ts_str.endswith("Z"):
        ts_str += ".000000Z"
    return {"t": ts_str, "o": c["open"], "h": c["high"], "l": c["low"], "c": c["close"], "v": c["volume"]}

def main():
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tradebot-sci"
    source_dir = config_dir / "data" / "oanda_14day"
    dest_dir = config_dir / "data" / "candle_history_forex"
    dest_dir.mkdir(parents=True, exist_ok=True)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY"]
    
    for sym in symbols:
        ltf_path = source_dir / f"{sym}_15m.json"
        if not ltf_path.exists(): 
            print(f"Skipping {sym}, no LTF data.")
            continue
        
        with open(ltf_path) as f: ltf_data = json.load(f)
        ltf_fmt = [_fmt(c) for c in ltf_data]
        
        # Resample 15m to 4h
        htf_fmt = []
        current_4h_block = None
        current_htf = {}
        for c in ltf_fmt:
            # c["t"] is "2026-02-13T00:15:00.000000Z"
            dt = datetime.fromisoformat(c["t"].replace("Z", "+00:00"))
            hour = dt.hour
            block = hour - (hour % 4)
            block_str = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}T{block:02d}"
            
            if block_str != current_4h_block:
                if current_htf:
                    htf_fmt.append(current_htf)
                current_4h_block = block_str
                current_htf = {"t": block_str + ":00:00.000000Z", "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"]}
            else:
                current_htf["h"] = max(current_htf["h"], c["h"])
                current_htf["l"] = min(current_htf["l"], c["l"])
                current_htf["c"] = c["c"]
                current_htf["v"] += c["v"]
        if current_htf:
            htf_fmt.append(current_htf)
        
        obs = []
        for ltf_c in ltf_fmt:
            c_ts = ltf_c["t"]
            valid_htf = [h for h in htf_fmt if h["t"] <= c_ts]
            synth_obs = {
                "sym": sym,
                "tf": "15m",
                "htf_tf": "4h",
                "ltf_tf": "15m",
                "ltf": [ltf_c],
                "htf": valid_htf[-1:] if valid_htf else [],
                "ts": c_ts.replace("Z", "+00:00")
            }
            obs.append(synth_obs)
            
        by_day = {}
        for snap in obs:
            day_str = snap["ts"].split("T")[0]
            by_day.setdefault(day_str, []).append(snap)
            
        sym_dir = dest_dir / sym
        sym_dir.mkdir(exist_ok=True)
        for day_str, snaps in by_day.items():
            out_path = sym_dir / f"{sym}_{day_str}.jsonl"
            with open(out_path, "w") as f:
                for s in snaps:
                    f.write(json.dumps(s) + "\n")
        print(f"[{sym}] wrote {len(obs)} obs across {len(by_day)} days.")

if __name__ == "__main__":
    main()
