import json, os
from pathlib import Path

state_file = os.path.expanduser("~/.config/tradebot-sci/data/paper_state.json")

start_cap = 10000.0
current_balance = start_cap

if os.path.exists(state_file):
    with open(state_file, "r") as f:
        state = json.load(f)
        current_balance = float(state.get("balance", start_cap))

pnl = current_balance - start_cap

velocity = (pnl / start_cap) * 100 if start_cap > 0 else 0
pct = 0.75 if velocity >= 2.5 else 0.50

payout = pnl * pct if pnl > 0 else 0
new_balance = start_cap + pnl - payout

print(f"Current Equity: {current_balance:.2f}")
print(f"PnL: {pnl:.2f}")
print(f"Payout ({pct * 100}%): {payout:.2f}")
print(f"New Balance: {new_balance:.2f}")

if os.path.exists(state_file):
    state["balance"] = new_balance
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
    print("Updated paper_state.json")


print(f"PnL: {pnl}")
print(f"Payout: {payout}")
print(f"New Balance: {new_balance}")

state = {
    "balance": new_balance,
    "positions": {},
    "updated_at": "2026-03-13T19:30:00.000Z"
}

with open(state_file, "w") as f:
    json.dump(state, f, indent=2)

print("Updated paper_state.json")
