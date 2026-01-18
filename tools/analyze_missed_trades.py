
import re
from datetime import datetime, timedelta
import sys

LOG_FILE = "logs/tradebot.log"
# Current time is roughly 2026-01-13T18:20:00
# User asks for last 16 hours -> since approx 02:20 AM
HOURS_BACK = 16
BALANCE = 88.0
RISK_PCT = 0.05
RISK_AMOUNT = BALANCE * RISK_PCT # $4.40

def parse_logs():
    now = datetime.now()
    cutoff = now - timedelta(hours=HOURS_BACK)
    
    # Regex for timestamp: 2026-01-13 18:09:57
    ts_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    
    # Regex for Decision
    # Use a simpler approach to capture kv pairs
    # entry=78.29 sl=77.67 tp=78.33
    entry_pattern = re.compile(r"entry=([\d.]+)")
    sl_pattern = re.compile(r"sl=([\d.]+)")
    tp_pattern = re.compile(r"tp=([\d.]+)")
    action_pattern = re.compile(r"action=(enter_long|enter_short)")
    symbol_pattern = re.compile(r"Decision:.* ([\w\-\./:]+) \d+m \|")

    blocked_pattern = re.compile(r"\[EXEC\] ([^ ]+) outcome=(blocked_guard|error|risk_suppressed)")

    missed_trades = []
    
    print(f"Analyzing logs since {cutoff}...")
    
    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()

    # We need to correlate Decision with subsequent Execution/Block
    # Since logs are sequential, we can just look ahead or assume if we see a decision 
    # and then a block block for that symbol, it's a miss.
    
    # Actually, simpler: finding ALL entry decisions. 
    # Then checking if they were executed or blocked.
    # The user asks for "misses", so we specifically want blocked/failed ones.
    
    # Let's iterate
    
    candidates = {} # symbol -> {timestamp, data}
    
    count = 0
    
    for i, line in enumerate(lines):
        # 1. Check Timestamp
        match = ts_pattern.match(line)
        if not match:
            continue
            
        try:
            log_ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
            
        if log_ts < cutoff:
            continue
            
        # 2. Check for Decision
        if "Decision:" in line and "action=enter" in line:
            # print(f"DEBUG found decision line: {line.strip()}")
            
            s_m = symbol_pattern.search(line)
            a_m = action_pattern.search(line)
            e_m = entry_pattern.search(line)
            sl_m = sl_pattern.search(line)
            tp_m = tp_pattern.search(line)
            
            if s_m and a_m and e_m and sl_m and tp_m:
                sym = s_m.group(1)
                action = a_m.group(1)
                entry = float(e_m.group(1))
                sl = float(sl_m.group(1))
                tp = float(tp_m.group(1))
                
                print(f"DEBUG MATCHED: {sym} {action} {entry} {sl} {tp}")
                
                # Calculate R
                risk_dist = abs(entry - sl)
                reward_dist = abs(tp - entry)
                if risk_dist == 0: continue
                
                r_multiple = reward_dist / risk_dist
                potential_profit = RISK_AMOUNT * r_multiple
                
                # Store candidate
                candidates[sym] = {
                    "ts": log_ts,
                    "symbol": sym,
                    "action": action,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "r": r_multiple,
                    "profit": potential_profit,
                    "line_idx": i
                }
            else:
                print(f"DEBUG NO MATCH: {line.strip()}")

        # 3. Check for Block/Error
        if "[EXEC]" in line:
             # print(f"DEBUG found exec line: {line.strip()}")
             m_block = blocked_pattern.search(line)
             if m_block:
                 print(f"DEBUG BLOCK MATCH: {m_block.groups()}")
                 sym = m_block.group(1)
                 reason = m_block.group(2)
                 
                 # clear match from candidates if it exists and is recent
                 if sym in candidates:
                     cand = candidates[sym]
                     time_diff = (log_ts - cand['ts']).total_seconds()
                     if time_diff < 30: # If decision was within 30s
                         missed_trades.append(cand)
                         del candidates[sym] # Consumed


    return missed_trades

def report(trades):
    if not trades:
        print("No missed trades found in the last 16 hours.")
        return

    print(f"\nFound {len(trades)} missed setups in the last 16 hours.")
    print("-" * 60)
    print(f"{'Time':<20} | {'Symbol':<20} | {'Action':<12} | {'R':<5} | {'Pot. Profit':<10}")
    print("-" * 60)
    
    total_r = 0.0
    total_profit_100 = 0.0
    
    for t in trades:
        print(f"{t['ts']} | {t['symbol']:<20} | {t['action']:<12} | {t['r']:.2f} | ${t['profit']:.2f}")
        total_r += t['r']
        total_profit_100 += t['profit']
        
    print("-" * 60)
    print(f"Total Theoretical Profit (100% Win Rate): ${total_profit_100:.2f}")
    
    # 55% Win Rate Calculation
    # EV = (Win% * Avg_Win) - (Loss% * Risk)
    # Total = Num_Trades * EV
    
    # Wait, the user might mean: "Of these specific trades, if 55% won and 45% lost".
    # Since we can't know WHICH won, we use Expected Value.
    
    avg_win = total_profit_100 / len(trades)
    ev_per_trade = (0.55 * avg_win) - (0.45 * RISK_AMOUNT)
    total_ev_55 = len(trades) * ev_per_trade
    
    print(f"Total Expected Profit (55% Win Rate):     ${total_ev_55:.2f}")
    print(f"  (Assumes avg win of ${avg_win:.2f} and fixed risk of ${RISK_AMOUNT:.2f} per loss)")

if __name__ == "__main__":
    trades = parse_logs()
    report(trades)
