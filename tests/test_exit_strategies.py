import os
import sys
import json
import subprocess
from pathlib import Path

def run_exit_tests():
    print("==================================================")
    print("🚀 INITIATING 11-PRONGED EXIT STRATEGY BACKTEST")
    print("==================================================")

    strategies = [
        ("fixed_rr", "The Sniper (Fixed R:R)"),
        ("chandelier", "Chandelier Trailing"),
        ("scale_breakeven", "Scale & Breakeven"),
        ("parabolic_sar", "Parabolic SAR"),
        ("ma_crossover", "MA Crossover"),
        ("time_decay", "Time-Decay"),
        ("swing_trailing", "Swing Trailing"),
        ("rsi_exhaustion", "RSI Exhaustion"),
        ("bollinger_snap", "Bollinger Band Snap-Back"),
        ("ratchet_milestone", "Ratchet Scaling"),
        ("adx_death", "ADX Death")
    ]

    results = []
    config_path = Path.home() / ".config" / "tradebot-sci" / "config.json"
    
    # Backup original config
    with open(config_path, "r") as f:
        original_config = json.load(f)

    try:
        for strat_key, strat_name in strategies:
            print(f"\n[TEST] Booting engine for: {strat_name} ({strat_key})...")
            
            # Prepare config
            with open(config_path, "r") as f:
                cfg = json.load(f)
                
            cfg["active_profile"] = "evaluation"
            cfg["global"]["universal_exit_strategies"] = [strat_key]
            cfg["global"]["chandelier_atr_mult"] = 2.0
            cfg["global"]["time_decay_bars"] = 24
            cfg["global"]["target_r"] = 100.0
            cfg["global"]["block_ranging_regime"] = False
            
            if "evaluation" not in cfg["profiles"]:
                cfg["profiles"]["evaluation"] = {}
                
            cfg["profiles"]["evaluation"]["strategy_variant"] = "forex_conductor"
            cfg["profiles"]["evaluation"]["strategies"] = {"forex": "forex_conductor"}
            cfg["profiles"]["evaluation"]["htf_timeframe"] = "4h"
            
            # Disable Safeties
            cfg["safety"]["safety_atr_shield_enabled"] = False
            cfg["safety"]["safety_drawdown_breaker_enabled"] = False
            cfg["safety"]["safety_session_lockout_enabled"] = False
            cfg["safety"]["safety_rollover_deadzone_enabled"] = False
            
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2)

            print(f"Debug Evaluation Profile: {json.dumps(cfg['profiles']['evaluation'], indent=2)}")

            # Execution
            cmd = ["python3", "tools/engine/engine_replay.py", "--days", "84", "--symbols", "EURUSD", "--balance", "1000", "--no-parallel", "--api-fallback"]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug")
                output = res.stdout + "\n" + res.stderr
                
                # The engine outputs a single line JSON string starting with {"total_pnl": at the end
                summary = None
                for line in reversed(output.splitlines()):
                    if line.startswith('{"total_pnl"'):
                        summary = json.loads(line)
                        break
                        
                if not summary:
                    raise Exception("No JSON summary found in output")
                
                pnl = summary.get("total_pnl", 0)
                win_rate = summary.get("win_rate", 0)
                trades = summary.get("total_trades", 0)
                
                if trades == 0:
                    print("!!! ZERO TRADES DEBUG !!!")
                    print("\n".join(output.splitlines()[-50:]))
                
                
                # avg hold calc
                t_list = summary.get("trades", [])
                total_mins = 0
                for t in t_list:
                    dur = t.get("duration", "0m")
                    if "h" in dur:
                        parts = dur.split("h")
                        total_mins += int(parts[0]) * 60
                        if "m" in parts[1]:
                            total_mins += int(parts[1].replace("m", "").strip())
                    elif "m" in dur:
                        total_mins += int(dur.replace("m", "").strip())
                
                avg_duration = (total_mins / 60) / max(1, trades)
                
                res_str = f"{strat_name} | Trades: {trades} | Win Rate: {win_rate:.1f}% | PnL: ${pnl:.2f} | Avg Hold: {avg_duration:.1f}h"
                print(f"✅ [DONE] {res_str}")
                
                results.append({
                    "Strategy": strat_name,
                    "PnL_USD": pnl,
                    "Win_Rate": win_rate,
                    "Trades": trades,
                    "Avg_Hold_Hrs": avg_duration
                })
                
            except Exception as e:
                print(f"❌ [FAILED] Engine crashed for {strat_name}: {e}")
                
                # Dump actual engine crash trace to see WHY there's no JSON
                if 'output' in locals():
                    print("\n--- ENGINE CRASH TRACE ---")
                    print("\n".join(output.splitlines()[-50:]))
                    print("--------------------------\n")
                    
                results.append({
                    "Strategy": strat_name,
                    "PnL_USD": 0,
                    "Win_Rate": 0,
                    "Trades": 0,
                    "Avg_Hold_Hrs": 0,
                    "Error": str(e)
                })

    finally:
        # Restore config
        with open(config_path, "w") as f:
            json.dump(original_config, f, indent=2)

        # Sort results
        results.sort(key=lambda x: x["PnL_USD"], reverse=True)
        
        print("\n\n==================================================")
        print("🏆 EXIT STRATEGY RANKINGS (EURUSD - 84 DAYS)")
        print("==================================================")
        print(f"{'Rank':<5} | {'Strategy Name':<25} | {'Total PnL':<10} | {'Win Rate':<10} | {'Trades':<8} | {'Avg Hold':<10}")
        print("-" * 75)
        
        for i, r in enumerate(results):
            print(f"{i+1:<5} | {r['Strategy']:<25} | ${r['PnL_USD']:<9.2f} | {r['Win_Rate']:<9.1f}% | {r['Trades']:<8} | {r['Avg_Hold_Hrs']:<8.1f}h")

        # Dump JSON
        with open('/tmp/exit_rankings.json', 'w') as f:
            json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_exit_tests()
