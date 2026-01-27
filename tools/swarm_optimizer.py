#!/usr/bin/env python3
import os
import random
import subprocess
import time
import re

# SWARM CONFIGURATION
ITERATIONS = 10
OUTPUT_DIR = "swarm_results"
CMD = ["python3", "tools/mega_backtester.py", "january_marathon"]

# PARAMETER RANGES (Refined)
RANGES = {
    "RR_RISK_PCT": (0.02, 0.08),      # 2% to 8% (Sweet spot?)
    "RR_LEV_CAP": (30.0, 100.0),      # 30x to 100x
    "RR_RSI_PERIOD": (5, 14),         # Faster RSI
    "RR_BB_PERIOD": (14, 25),         # Tighter Bands
    "RR_BB_STD": (2.0, 3.0),          # Standard Devs
    "RR_RSI_OB": (65, 80),            # More triggers
    "RR_RSI_OS": (20, 35)             # More triggers
}

best_config = None
best_capital = -99999.0

print(f"[*] Starting Swarm Optimization: {ITERATIONS} iterations...")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

for i in range(ITERATIONS):
    # 1. Generate Random Config
    env = os.environ.copy()
    config = {}
    
    config["RR_RISK_PCT"] = f"{random.uniform(*RANGES['RR_RISK_PCT']):.3f}"
    config["RR_LEV_CAP"] = f"{random.uniform(*RANGES['RR_LEV_CAP']):.1f}"
    config["RR_RSI_PERIOD"] = str(random.randint(*RANGES['RR_RSI_PERIOD']))
    config["RR_BB_PERIOD"] = str(random.randint(*RANGES['RR_BB_PERIOD']))
    config["RR_BB_STD"] = f"{random.uniform(*RANGES['RR_BB_STD']):.1f}"
    config["RR_RSI_OB"] = str(random.randint(*RANGES['RR_RSI_OB']))
    config["RR_RSI_OS"] = str(random.randint(*RANGES['RR_RSI_OS']))
    
    # Update Env
    env.update(config)
    
    # 2. Run Backtest
    log_file = f"{OUTPUT_DIR}/run_{i}.txt"
    print(f"[{i+1}/{ITERATIONS}] Testing: Risk={config['RR_RISK_PCT']}, Lev={config['RR_LEV_CAP']}, RSI={config['RR_RSI_PERIOD']}...", end=" ", flush=True)
    
    try:
        with open(log_file, "w") as f:
            subprocess.run(CMD, env=env, stdout=f, stderr=f, timeout=120) # 2 min timeout per run
            
        # 3. Parse Result
        with open(log_file, "r") as f:
            content = f.read()
            
        # Extract Final Capital
        match = re.search(r"Final Capital: \$([-0-9\.]+)", content)
        if match:
            final_cap = float(match.group(1))
            print(f"-> Result: ${final_cap:.2f}")
            
            if final_cap > best_capital:
                best_capital = final_cap
                best_config = config
                print(f"   >>> NEW KING! ${best_capital:.2f} <<<")
        else:
             print("-> Failed (No Result)")

    except Exception as e:
        print(f"-> Error: {e}")

print("-" * 50)
print("SWARM COMPLETE.")
if best_config:
    print(f"Top Config Found: ${best_capital:.2f}")
    for k, v in best_config.items():
        print(f"  {k}: {v}")
    
    # Write to a file for easy reading
    with open("best_swarm_config.txt", "w") as f:
        f.write(f"Capital: {best_capital}\n")
        for k, v in best_config.items():
            f.write(f"{k}={v}\n")
else:
    print("No valid results found.")
