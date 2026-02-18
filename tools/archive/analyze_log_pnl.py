import re
import sys

log_file = sys.argv[1] if len(sys.argv) > 1 else "results_final_jackpot.txt"
total_pnl = 0.0
wins = 0
losses = 0
capital = 100.0
pnls = []

try:
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Look for PnL entries: "  PnL: $0.3398" (Summary) OR "PnL=$0.33" (Runtime)
            match = re.search(r'PnL[=:]\s*\$(-?\d+\.\d+)', line)
            if match:
                val = float(match.group(1))
                total_pnl += val
                capital += val
                pnls.append(val)
                if val > 0: wins += 1
                else: losses += 1
except FileNotFoundError:
    print("Log file not found.")
    sys.exit(1)

print(f"Total PnL: ${total_pnl:.2f}")
print(f"Final Capital: ${capital:.2f}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
if (wins + losses) > 0:
    print(f"Win Rate: {wins/(wins+losses)*100:.1f}%")
else:
    print("Win Rate: 0%")

if pnls:
    print(f"Max Loss: ${min(pnls):.2f}")
    print(f"Avg PnL: ${sum(pnls)/len(pnls):.2f}")
