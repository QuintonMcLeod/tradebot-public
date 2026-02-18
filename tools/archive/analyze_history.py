import re
from datetime import datetime, timedelta

LOG_FILE = "logs/tradebot.log"

def analyze_history():
    print(f"Analyzing {LOG_FILE} for deep history...")
    
    balance_history = []
    trades_found = []
    crypto_logs = []
    oanda_history = []
    ccxt_history = []
    
    with open(LOG_FILE, 'r') as f:
        for line in f:
            try:
                # 1. Track Balance by Source
                if "[TOTAL] Liquidity available: $" in line:
                    match = re.search(r"available: \$([\d\.]+)", line)
                    if match:
                        ts = line[:19]
                        val = float(match.group(1))
                        balance_history.append((ts, val))

                # Track Components
                if "[OANDA] Account Summary:" in line:
                    match = re.search(r"Balance=([\d\.]+)", line) 
                    nav_match = re.search(r"NAV=([\d\.]+)", line)
                    if match and nav_match:
                         # We use NAV (Net Asset Value) as true equity
                         oanda_nav = float(nav_match.group(1))
                         oanda_history.append((line[:19], oanda_nav))
                
                if "[CCXT] get_liquid_capital" in line:
                    match = re.search(r"Cash=\$([\d\.]+)", line)
                    if match:
                         ccxt_val = float(match.group(1))
                         ccxt_history.append((line[:19], ccxt_val))

                # 2. Track TRADES (Broad search)
                if ("FILLED" in line.upper() or "SOLD" in line.upper() or "BOUGHT" in line.upper()) and ("order" in line.lower() or "execution" in line.lower()):
                    trades_found.append(line.strip())

            except Exception:
                continue

    print(f"Balance Data Points: {len(balance_history)}")
    
    if oanda_history:
        print(f"OANDA Start: ${oanda_history[0][1]:.2f}")
        print(f"OANDA End:   ${oanda_history[-1][1]:.2f}")
        print(f"OANDA Delta: ${oanda_history[-1][1] - oanda_history[0][1]:.2f}")
        
    if ccxt_history:
        print(f"CCXT Start:  ${ccxt_history[0][1]:.2f}")
        print(f"CCXT End:    ${ccxt_history[-1][1]:.2f}")
        print(f"CCXT Delta:  ${ccxt_history[-1][1] - ccxt_history[0][1]:.2f}")

    if balance_history:
        start = balance_history[0]
        end = balance_history[-1]
        print(f"Total Start: ${start[1]:.2f}")
        print(f"Total End:   ${end[1]:.2f}")
        print(f"Total Delta: ${end[1] - start[1]:.2f}")
        
    print("-" * 40)
    print(f"Potential Trades Found: {len(trades_found)}")
    for t in trades_found[-10:]:
        print(t)

if __name__ == "__main__":
    analyze_history()
