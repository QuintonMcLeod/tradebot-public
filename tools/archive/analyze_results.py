
import re

try:
    with open('backtest_pnl.txt', 'r') as f:
        pnl_lines = f.readlines()
except FileNotFoundError:
    print("backtest_pnl.txt not found")
    exit(1)

total_pnl = 0.0
wins = 0
losses = 0
capital = 100.0
pnls = []

for line in pnl_lines:
    match = re.search(r'PnL:\s*\$(-?\d+\.\d+)', line)
    if match:
        val = float(match.group(1))
        total_pnl += val
        capital += val
        pnls.append(val)
        if val > 0: wins += 1
        else: losses += 1

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
    print(f"Max Win: ${max(pnls):.2f}")
    avg_win = sum([p for p in pnls if p > 0]) / wins if wins else 0
    avg_loss = sum([p for p in pnls if p <= 0]) / losses if losses else 0
    print(f"Avg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
else:
    print("No trades found")
