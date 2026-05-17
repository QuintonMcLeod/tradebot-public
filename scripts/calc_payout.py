import json, os
from pathlib import Path

instance_id = os.environ.get("TRADEBOT_INSTANCE_ID", "local")
td = os.environ.get("TRADEBOT_DATA_DIR")
if td:
    base_dir = Path(td)
    if base_dir.name != instance_id:
        base_dir = base_dir / instance_id
else:
    base_dir = Path.home() / ".config" / "tradebot-sci-gui" / instance_id

state_file = base_dir / "data" / "paper_state.json"

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
