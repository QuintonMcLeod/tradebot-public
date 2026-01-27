
import os
import re
import subprocess
import sys

SETTINGS_FILE = "src/tradebot_sci/strategy/variants/rubberband_reaper.py"
BACKTEST_CMD = ["python3", "tools/mega_backtester.py", "january_sprint"] # Use Sprint for speed (1 week)

PARAMETERS = [
    # Risk 60%, varying Stops (Attempting to find the 'Safety' width)
    {"risk": 0.60, "stop_atr": 2.0},
    {"risk": 0.60, "stop_atr": 3.0},
    {"risk": 0.60, "stop_atr": 4.0},
    {"risk": 0.60, "stop_atr": 5.0},
    # Risk 40% (Safer scaling)
    {"risk": 0.40, "stop_atr": 3.0},
    {"risk": 0.40, "stop_atr": 4.0},
    # Risk 80% (Insane mode, wide stop)
    {"risk": 0.80, "stop_atr": 5.0},
]

def update_strategy(risk, stop_atr):
    with open(SETTINGS_FILE, 'r') as f:
        content = f.read()
    
    # Update Risk Logic (Tiered Risk function)
    # Regex to replace "return 0.XX" inside get_tiered_risk for capital < 1000
    # Pattern: if capital < 1000:\n\s+return [\d\.]+
    content = re.sub(
        r'(if capital < 1000:\n\s+return )[\d\.]+',
        f'\\g<1>{risk}',
        content
    )
    
    # Update Init Base Risk
    content = re.sub(
        r'base_risk_pct=[\d\.]+',
        f'base_risk_pct={risk}',
        content
    )

    # Update Stop Loss ATR Multiplier
    # Pattern: atr * [\d\.]+
    content = re.sub(
        r'stop_loss = last_close ([+-]) \(atr \* [\d\.]+\)',
        f'stop_loss = last_close \\1 (atr * {stop_atr})',
        content
    )
    
    # Update Note/Summary for confirmation
    content = re.sub(
        r'Reaper GodMode .*?\(',
        f'Reaper Opt ({risk*100}% Risk, {stop_atr} ATR) (',
        content
    )

    with open(SETTINGS_FILE, 'w') as f:
        f.write(content)

def parse_result(output):
    # Extract Final Capital and Returns
    # "Final Capital: $100.91"
    cap_match = re.search(r'Final Capital: \$([\d\.]+)', output)
    pnl_match = re.search(r'Return: ([\d\.\-]+)%', output)
    
    if cap_match and pnl_match:
        return float(cap_match.group(1)), float(pnl_match.group(1))
    return 0.0, -100.0

def main():
    best_pnl = -999.0
    best_config = None
    
    print("Starting Optimization Loop...")
    
    for params in PARAMETERS:
        print(f"\nTesting Config: Risk={params['risk']}, Stop={params['stop_atr']} ATR")
        update_strategy(params['risk'], params['stop_atr'])
        
        try:
            result = subprocess.run(BACKTEST_CMD, capture_output=True, text=True, timeout=60)
            output = result.stdout
            
            final_cap, pnl = parse_result(output)
            print(f"  -> Result: ${final_cap:.2f} ({pnl:.2f}%)")
            
            if pnl > best_pnl:
                best_pnl = pnl
                best_config = params
                
            # Early Exit if goal met
            if pnl > 300.0: # Close to 400%
                print("  -> TARGET MET! Stopping loop.")
                break
                
        except Exception as e:
            print(f"  -> Error: {e}")

    print("\n=== OPTIMIZATION COMPLETE ===")
    print(f"Best Config: {best_config}")
    print(f"Best Return: {best_pnl:.2f}%")
    
    # Apply Best Config Final
    if best_config:
        update_strategy(best_config['risk'], best_config['stop_atr'])
        print("Restored strategy to best config.")

if __name__ == "__main__":
    main()
