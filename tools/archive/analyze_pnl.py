import re
from datetime import datetime, timedelta
import sys

LOG_FILE = "logs/tradebot.log"

def analyze_logs():
    print(f"Analyzing {LOG_FILE}...")
    
    total_pnl = 0.0
    crypto_decisions = []
    
    now = datetime.now()
    cutoff = now - timedelta(hours=24)
    
    # Regex for PnL: "unrealized_pnl": 1.2856, "reason": "heartbeat", "total_unrealized_pnl": 1.6559
    # Actually user wants REALIZED PnL.
    # Looking for: [INFO] ... [EXECUTION] Sell Order Filled ... PnL: $1.50
    # Or strict log entries for realized pnl.
    
    # Let's simple grep for "REALIZED_PNL" or similar structure if it exists
    # Based on previous logs, we saw: "unrealized_pnl" in heartbeat.
    # Let's update search to look for CLOSED trades.
    
    count_filled = 0
    
    try:
        with open(LOG_FILE, 'r') as f:
            for line in f:
                # 1. Parse Timestamp
                # Log format: 2026-02-03 03:52:11 [INFO] ...
                try:
                    ts_str = line[:19]
                    log_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if log_time < cutoff:
                        continue
                except ValueError:
                    continue

                # 2. Track Realized PnL
                # Assuming format: "Realized PnL: $X.XX" or similar. 
                # Since I don't have the exact "Closed" log format handy, I will look for common patterns from this codebase's history if recallable, 
                # or generically search for "Realized" and value.
                if "Realized PnL" in line or "REALIZED_PNL" in line:
                    # Try extract number
                    match = re.search(r"Realized PnL[:\s]+\$?([-\d\.]+)", line, re.IGNORECASE)
                    if match:
                        val = float(match.group(1))
                        total_pnl += val
                        count_filled += 1
                        print(f"[{ts_str}] Trade Closed: ${val}")

                # 3. Track Crypto Decisions (Why is it skipping?)
                if "SOLUSD" in line or "BTCUSD" in line:
                    if "[DECISION]" in line or "Ensemble Pulse" in line or "Validation" in line:
                         crypto_decisions.append(f"[{ts_str}] {line.strip()}")

    except FileNotFoundError:
        print("Log file not found.")
        return

    print("-" * 40)
    print(f"Start Time (24h ago): {cutoff}")
    print(f"Trades Closed: {count_filled}")
    print(f"Total Realized PnL (est): ${total_pnl:.2f}")
    print("-" * 40)
    print("Recent Crypto Activity (Last 10 lines):")
    for d in crypto_decisions[-10:]:
        print(d)

if __name__ == "__main__":
    analyze_logs()
