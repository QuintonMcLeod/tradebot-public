import re
import os
import json
import glob
from datetime import datetime
from collections import defaultdict

def parse_iso_time(line):
    try:
        return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
    except:
        return None

def reconstruct_pnl(log_dir="logs"):
    fill_pattern = re.compile(r"\[FILL\] (\w+) @ ([\d\.]+)")
    entry_pattern = re.compile(r"\[ENTRY\] (\w+) side=(\w+) amount=([\d\.]+)")
    exit_pattern = re.compile(r"\[EXIT\] .*?: (\w+) ([+-]\$[\d\.]+) \(Pct=([\d\.\-]+)%\)")
    holdings_pattern = re.compile(r"\[HOLDINGS\] (\{.*\})")
    snapshot_pattern = re.compile(r"\[(CCXT|OANDA)\] Snapshot (\w+) \| .*? \| Last=([\d\.]+)")
    
    events = [] # List of (time, type, data)
    
    log_files = glob.glob(os.path.join(log_dir, "tradebot.log*"))
    log_files += glob.glob(os.path.join(log_dir, "tradebot_manual.log*"))
    log_files += glob.glob(os.path.join(log_dir, "tradebot_restart*.log*"))
    log_files = sorted(list(set(log_files)), key=os.path.getmtime)
    
    print(f"Parsing {len(log_files)} logs for forensic events...")
    
    for log_path in log_files:
        with open(log_path, 'r', errors='ignore') as f:
            for line in f:
                dt = parse_iso_time(line)
                if not dt: continue
                ts = int(dt.timestamp())
                
                # Fills
                f_match = fill_pattern.search(line)
                if f_match:
                    events.append((ts, "fill", {"symbol": f_match.group(1), "price": float(f_match.group(2))}))
                
                # Entries (Qty)
                e_match = entry_pattern.search(line)
                if e_match:
                    events.append((ts, "entry", {"symbol": e_match.group(1), "qty": float(e_match.group(3)), "side": e_match.group(2)}))
                
                # Exits (Definitive)
                x_match = exit_pattern.search(line)
                if x_match:
                    events.append((ts, "exit_log", {"symbol": x_match.group(1), "pnl": float(x_match.group(2).replace('$', '').replace('+', ''))}))
                
                # Snapshots (Price tracking)
                s_match = snapshot_pattern.search(line)
                if s_match:
                    events.append((ts, "price", {"symbol": s_match.group(2), "price": float(s_match.group(3))}))
                
                # Holdings (Delta tracking)
                h_match = holdings_pattern.search(line)
                if h_match:
                    try:
                        data = json.loads(h_match.group(1))
                        events.append((ts, "holdings", data))
                    except: pass

    # Sort all events chronologically
    events.sort(key=lambda x: x[0])
    
    active_holdings = {} # sym -> {entry_p, qty, side, opened_at, last_p}
    closed_trades = []
    
    for ts, etype, data in events:
        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        
        if etype == "fill":
            sym = data["symbol"]
            if sym in active_holdings:
                active_holdings[sym]["entry_p"] = data["price"]
            else:
                active_holdings[sym] = {"entry_p": data["price"], "qty": 0.0, "side": "buy", "opened_at": time_str, "last_p": data["price"]}
        
        elif etype == "entry":
            sym = data["symbol"]
            if sym in active_holdings:
                active_holdings[sym]["qty"] = data["qty"]
                active_holdings[sym]["side"] = data["side"]
            else:
                active_holdings[sym] = {"entry_p": 0.0, "qty": data["qty"], "side": data["side"], "opened_at": time_str, "last_p": 0.0}
        
        elif etype == "price":
            sym = data["symbol"]
            if sym in active_holdings:
                active_holdings[sym]["last_p"] = data["price"]
        
        elif etype == "holdings":
            current_syms = {p["symbol"] for p in data.get("positions", [])}
            # Identify new positions appearing in holdings but not in active_holdings
            for p in data.get("positions", []):
                sym = p["symbol"]
                cur_p = float(p.get("current_price") or p.get("last") or p.get("avg_price") or 0.0)
                if sym not in active_holdings:
                    active_holdings[sym] = {
                        "entry_p": float(p.get("entry_price") or p.get("avg_price") or cur_p),
                        "qty": float(p.get("size") or 0.0),
                        "side": p.get("side") or ("long" if (p.get("size") or 0) > 0 else "short"),
                        "opened_at": time_str,
                        "last_p": cur_p
                    }
                else:
                    active_holdings[sym]["last_p"] = cur_p
            
            # Identify missing positions (Closed)
            to_remove = []
            for sym in active_holdings:
                if sym not in current_syms:
                    to_remove.append(sym)
            
            for sym in to_remove:
                pos = active_holdings.pop(sym)
                exit_p = pos["last_p"]
                pnl = 0.0
                if exit_p and pos["entry_p"]:
                    if pos["side"] in ("long", "buy", "enter_long") or pos["qty"] > 0:
                        pnl = (exit_p - pos["entry_p"]) * abs(pos["qty"])
                    else:
                        pnl = (pos["entry_p"] - exit_p) * abs(pos["qty"])
                
                closed_trades.append({
                    "symbol": sym,
                    "entry_time": pos["opened_at"],
                    "exit_time": time_str,
                    "pnl": pnl,
                    "entry_p": pos["entry_p"],
                    "exit_p": exit_p,
                    "qty": pos["qty"]
                })
        
        elif etype == "exit_log":
            sym = data["symbol"]
            pnl_val = data["pnl"]
            if pnl_val != 0:
                # Update last closed trade for this symbol within 5 mins
                for trade in reversed(closed_trades):
                    if trade["symbol"] == sym:
                        trade["pnl"] = pnl_val
                        break
                # Also remove from active just in case holdings didn't catch it yet
                if sym in active_holdings:
                    active_holdings.pop(sym)

    return closed_trades

if __name__ == "__main__":
    trades = reconstruct_pnl()
    
    results = []
    for t in trades:
        results.append({
            "symbol": t["symbol"],
            "closed_at": datetime.strptime(t["exit_time"], "%Y-%m-%d %H:%M:%S").isoformat() + "Z",
            "pnl_usd": round(t["pnl"], 4),
            "pnl_pct": round((t["pnl"] / (t["entry_p"] * abs(t["qty"]))) * 100, 2) if t["entry_p"] and t["qty"] else 0.0,
            "is_win": t["pnl"] > 0,
            "tier": "100%",
            "forensic": True
        })
    
    results = sorted(results, key=lambda x: x["closed_at"])
    with open("data/trade_results.json", "w") as f:
        json.dump(results, f, indent=4)
        
    print(f"\nForensic Reconstruction Complete: {len(results)} trades.")
    print(f"Total Reconstructed PNL: ${sum(r['pnl_usd'] for r in results):.2f}")
