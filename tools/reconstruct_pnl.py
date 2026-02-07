import re
import os
import json
from datetime import datetime
from collections import defaultdict

def reconstruct_pnl(log_dir="logs"):
    entry_pattern = re.compile(r"\[FILL\] (\w+) @ ([\d\.]+)")
    exit_pattern = re.compile(r"\[EXIT\] .*?: (\w+)")
    
    # We also need size to calculate dollar PNL
    size_pattern = re.compile(r"\[ENTRY\] (\w+) side=(\w+) amount=([\d\.]+)")
    
    holdings = defaultdict(list) # symbol -> list of (price, qty)
    closed_trades = []
    
    import glob
    log_files = sorted(glob.glob(os.path.join(log_dir, "tradebot.log*")), key=os.path.getmtime)
    
    print(f"Processing {len(log_files)} logs...")
    
    for log_path in log_files:
        with open(log_path, 'r', errors='ignore') as f:
            for line in f:
                # 1. Track Entry Size
                size_match = size_pattern.search(line)
                if size_match:
                    symbol, side, qty = size_match.groups()
                    # We store the intended size temporarily
                    holdings[symbol + "_pending_size"] = (side, float(qty))
                
                # 2. Track Fill Price
                fill_match = entry_pattern.search(line)
                if fill_match:
                    symbol, price = fill_match.groups()
                    price = float(price)
                    if symbol + "_pending_size" in holdings:
                        side, qty = holdings.pop(symbol + "_pending_size")
                        holdings[symbol].append({"price": price, "qty": qty, "side": side, "time": line[:19]})
                
                # 3. Track Exit
                exit_match = exit_pattern.search(line)
                if exit_match:
                    symbol = exit_match.group(1)
                    if symbol in holdings and holdings[symbol]:
                        # For simplicity, assume FIFO or aggregate
                        # Usually the bot flattens the whole thing
                        entries = holdings.pop(symbol)
                        
                        # We need the exit price. The log usually has it in the [EXIT] line but it was $0.00.
                        # However, we might find a [HOLDINGS] snapshot right before the exit with current_price.
                        # For now, let's look for the next [HOLDINGS] or use a heuristic.
                        # ACTUALLY, if we can't find exit price, we'll mark it as 'Realized (Unknown Price)'
                        # But wait, I can look for "Manual/Signal: SYMBOL +$X.XX" - if it's 0, I'll try to find a price.
                        
                        # Let's try to find if there was a price in the log
                        pnl_match = re.search(r"([+-]\$[\d\.]+) \(Pct=([\d\.\-]+)%\)", line)
                        pnl_usd = 0.0
                        if pnl_match:
                            pnl_usd = float(pnl_match.group(1).replace('$', '').replace('+', ''))
                        
                        for entry in entries:
                            closed_trades.append({
                                "symbol": symbol,
                                "entry_time": entry["time"],
                                "exit_time": line[:19],
                                "entry_price": entry["price"],
                                "qty": entry["qty"],
                                "side": entry["side"],
                                "pnl_reported": pnl_usd
                            })

    return closed_trades

if __name__ == "__main__":
    trades = reconstruct_pnl()
    print(f"\nFound {len(trades)} reconstructed cycles.")
    for t in trades[-10:]:
        print(f"{t['exit_time']} | {t['symbol']} {t['side'].upper()} | Entry: {t['entry_price']} | Reported PNL: ${t['pnl_reported']}")
    
    total_reported = sum(t['pnl_reported'] for t in trades)
    print(f"\nTotal Reported Realized PNL: ${total_reported:.2f}")
