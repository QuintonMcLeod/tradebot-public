import os
import json
from pathlib import Path
from datetime import datetime, timezone

def _fmt(c):
    ts_str = c["timestamp"]
    if "+00:00" in ts_str:
        ts_str = ts_str.replace("+00:00", ".000000Z")
    elif not ts_str.endswith("Z"):
        ts_str += ".000000Z"
    return {"t": ts_str, "o": c["open"], "h": c["high"], "l": c["low"], "c": c["close"], "v": c["volume"]}

def main():
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tradebot-sci"
    source_dir = config_dir / "data" / "crypto_backtest"
    dest_dir = config_dir / "data" / "candle_history"
    dest_dir.mkdir(parents=True, exist_ok=True)

    symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"]
    
    for sym in symbols:
        ltf_path = source_dir / f"{sym}_5m.json"
        htf_path = source_dir / f"{sym}_1h.json"
        if not ltf_path.exists(): 
            print(f"Skipping {sym}, no LTF data.")
            continue
        
        with open(ltf_path) as f: ltf_data = json.load(f)
        ltf_fmt = [_fmt(c) for c in ltf_data]
        
        # Resample 5m to 1h
        htf_fmt = []
        current_hour = None
        current_htf = {}
        for c in ltf_fmt:
            # c["t"] is like "2026-01-24T00:05:00.000000Z"
            hour_str = c["t"][:13] # "2026-01-24T00"
            if hour_str != current_hour:
                if current_htf:
                    htf_fmt.append(current_htf)
                current_hour = hour_str
                current_htf = {"t": hour_str + ":00:00.000000Z", "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"]}
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
                "tf": "5m",
                "htf_tf": "1h",
                "ltf_tf": "5m",
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
