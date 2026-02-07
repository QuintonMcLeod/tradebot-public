import re
import os
import json
from datetime import datetime
from typing import List, Dict

def parse_advanced_pnl(log_path: str) -> Dict:
    """
    Reconstructs PNL by tracking entries and exits.
    """
    trades = []
    active_positions = {}
    total_realized = 0.0
    
    if not os.path.exists(log_path):
        return {"error": "Log not found"}

    # Patterns
    # [HOLDINGS] snapshots provide ground truth for active positions
    holdings_pattern = re.compile(r"\[HOLDINGS\] (\{.*\})")
    # [EXIT] patterns for realized PNL
    exit_pattern = re.compile(r"\[EXIT\] .*? (\w+)\s*([\+\-]\$[\d\.]+) \(Pct=([\d\.\-]+)%\)")
    
    with open(log_path, 'r') as f:
        for line in f:
            # 1. Update active holdings from heartbeats
            holdings_match = holdings_pattern.search(line)
            if holdings_match:
                try:
                    data = json.loads(holdings_match.group(1))
                    for pos in data.get('positions', []):
                        sym = pos['symbol']
                        active_positions[sym] = {
                            "entry": pos['entry_price'],
                            "size": pos['size'],
                            "unrealized": pos['unrealized_pnl']
                        }
                except: pass

            # 2. Capture realized exits
            exit_match = exit_pattern.search(line)
            if exit_match:
                symbol = exit_match.group(1)
                pnl_str = exit_match.group(2).replace('$', '').replace('+', '')
                pnl_val = float(pnl_str)
                pct_val = float(exit_match.group(3))
                
                total_realized += pnl_val
                trades.append({
                    "symbol": symbol,
                    "realized_pnl": pnl_val,
                    "pnl_pct": pct_val,
                    "timestamp": line[:19]
                })
                
                if symbol in active_positions:
                    del active_positions[symbol]

    return {
        "realized_pnl": round(total_realized, 2),
        "active_unrealized": round(sum(p['unrealized'] for p in active_positions.values()), 2),
        "trade_count": len(trades),
        "trades": trades,
        "positions": active_positions
    }

if __name__ == "__main__":
    import glob
    all_logs = sorted(glob.glob("logs/tradebot.log*"), reverse=True)
    
    final_results = {
        "total_realized": 0.0,
        "active_unrealized": 0.0,
        "trades": []
    }
    
    print(f"Analyzing {len(all_logs)} log files...")
    
    # Process newest first to get latest unrealized, but accumulate realized
    for log in all_logs:
        res = parse_advanced_pnl(log)
        if "error" in res: continue
        
        final_results["total_realized"] += res["realized_pnl"]
        final_results["trades"].extend(res["trades"])
        # Only take unrealized from the newest log (tradebot.log)
        if log == "logs/tradebot.log":
            final_results["active_unrealized"] = res["active_unrealized"]

    print("\n=== SYSTEM OVERVIEW ===")
    print(f"Total Realized PNL: ${final_results['total_realized']:.2f}")
    print(f"Total Unrealized PNL: ${final_results['active_unrealized']:.2f}")
    print(f"Total Combined PNL: ${final_results['total_realized'] + final_results['active_unrealized']:.2f}")
    print(f"Closed Trades: {len(final_results['trades'])}")
    
    if final_results['trades']:
        print("\nLast 5 Exits:")
        for t in sorted(final_results['trades'], key=lambda x: x['timestamp'])[-5:]:
            print(f"  {t['timestamp']} | {t['symbol']}: ${t['realized_pnl']} ({t['pnl_pct']}%)")
            
    with open("pnl_audit_final.json", "w") as f:
        json.dump(final_results, f, indent=2)
