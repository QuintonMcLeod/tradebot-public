
import re

def parse_backtest(file_path):
    trades = []
    capital = 200.0
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the VERY LAST "Trade History:" section
    sections = re.findall(r"Trade History:(.*?)(?:===|$)", content, re.DOTALL)
    if not sections:
        return []
    
    last_section = sections[-1]
    lines = last_section.strip().split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Format: [DATE] SYMBOL SIDE OUTCOME
        match = re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] (\w+) (\w+) (\w+)", line)
        if match:
            symbol = match.group(1)
            outcome = match.group(3)
            # Look at next line for PnL
            if i + 1 < len(lines):
                pnl_line = lines[i+1].strip()
                pnl_match = re.search(r"PnL: \$(-?[\d\.]+)", pnl_line)
                if pnl_match:
                    pnl = float(pnl_match.group(1))
                    capital += pnl
                    trades.append({
                        "symbol": symbol,
                        "outcome": outcome,
                        "pnl": pnl,
                        "capital": capital
                    })
                    i += 2
                    continue
        i += 1
    
    return trades

trades = parse_backtest("rent_metrics_data.txt")

print("# Performance Metrics Report")
print(f"**Final Capital**: ${trades[-1]['capital']:.2f}" if trades else "**No trades found**")
print("| # | Symbol | Outcome | PnL | Capital |")
print("|---|---|---|---|---|")
for i, t in enumerate(trades, 1):
    print(f"| {i} | {t['symbol']} | {t['outcome']} | {t['pnl']:.2f} | {t['capital']:.2f} |")

print("\n## Mermaid Capital Curve")
print("```mermaid")
print("xychart-beta")
print("    title \"Recovery Martingale Curve ($200 -> $970)\"")
print("    x-axis [\"Start\", " + ", ".join([f"\"{i}\"" for i in range(1, len(trades) + 1)]) + "]")
print("    y-axis \"Capital ($)\" 0 -> 1000")
print("    line [200, " + ", ".join([f"{t['capital']:.2f}" for t in trades]) + "]")
print("```")
