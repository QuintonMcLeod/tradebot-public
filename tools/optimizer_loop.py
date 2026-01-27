
import os
import subprocess
import re
import sys

# Combinations to test: (Risk%, Leverage Cap)
# Focused range based on previous failures (40% bust, 15% safe)
scenarios = [
    # Safe Control
    {"risk": 0.15, "lev": 5.0, "desc": "Baseline Safe"},
    
    # Aggressive but Capped Leverage
    {"risk": 0.20, "lev": 20.0, "desc": "Mid Risk/Lev"},
    {"risk": 0.25, "lev": 20.0, "desc": "High Risk/Mid Lev"},
    
    # Higher Leverage, Moderate Risk
    {"risk": 0.15, "lev": 50.0, "desc": "Mid Risk/High Lev"},
    {"risk": 0.20, "lev": 50.0, "desc": "High Risk/High Lev"},
]

results = []

def parse_last_run(log_file):
    total_pnl = 0.0
    capital = 100.0
    wins = 0
    losses = 0
    max_dd_val = 0.0 # simplified tracking
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = re.search(r'PnL[=:]\s*\$(-?\d+\.\d+)', line)
                if match:
                    val = float(match.group(1))
                    capital += val
                    if val > 0: wins += 1
                    else: losses += 1
    except Exception:
        pass
        
    return capital, wins, losses

print(f"{'Desc':<20} | {'Risk':<6} | {'Lev':<6} | {'Final Cap':<10} | {'Return %':<10} | {'Win Rate':<10}")
print("-" * 80)

for i, scen in enumerate(scenarios):
    env = os.environ.copy()
    env["RR_BASE_RISK"] = str(scen["risk"])
    env["ENGINE_LEVERAGE_CAP"] = str(scen["lev"])
    env["RR_FEET_WET_RISK"] = "0.0025" # Keep scout small
    
    log_name = f"results_optim_{i}.txt"
    
    # Run Backtest
    # print(f"Running {scen['desc']}...")
    try:
        subprocess.run(
            ["python3", "tools/mega_backtester.py", "january_marathon"],
            stdout=open(log_name, "w"),
            stderr=subprocess.STDOUT,
            env=env,
            timeout=300 # 5 min timeout per run
        )
    except subprocess.TimeoutExpired:
        print(f"Scenario {i} timed out")
        continue

    # Analyze
    final_cap, w, l = parse_last_run(log_name)
    ret_pct = (final_cap - 100.0)
    wr = (w / (w + l) * 100) if (w+l) > 0 else 0
    
    print(f"{scen['desc']:<20} | {scen['risk']:<6.2f} | {scen['lev']:<6.1f} | ${final_cap:<9.2f} | {ret_pct:<9.1f}% | {wr:<9.1f}%")
    results.append({**scen, "final_cap": final_cap})

best = max(results, key=lambda x: x["final_cap"])
print("-" * 80)
print(f"Optimal Config: {best['desc']} (Risk={best['risk']}, Lev={best['lev']}) -> ${best['final_cap']:.2f}")
