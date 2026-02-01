#!/usr/bin/env python3
import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

# MOCK AI Client for Sentiment Fusion
class MockAIClient:
    def generate_text(self, messages):
        return "BULLISH"

def run_clash():
    # Force settings
    os.environ["PROFILE_NAME"] = "crypto_247"
    settings = load_settings()
    
    # RELAX THRESHOLDS for the experiment
    profile = settings.get_active_profile()
    profile.icc_entry_score_threshold = 20.0
    profile.icc_auto_entry_min_htf_strength = 0.1
    profile.multi_position_enabled = True
    profile.max_concurrent_positions = 5
    
    # Symbols and Data Paths
    DATA_BASE = Path(__file__).resolve().parents[2] / "data"
    symbols = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"]
    data_paths = {
        "BTCUSD": str(DATA_BASE / "crypto_marathon" / "BTCUSD_5m.json"),
        "ETHUSD": str(DATA_BASE / "crypto_marathon" / "ETHUSD_5m.json"),
        "EURUSD": str(DATA_BASE / "forex_backtest" / "EURUSD_5m.json"),
        "GBPUSD": str(DATA_BASE / "forex_backtest" / "GBPUSD_5m.json")
    }
    
    strategies = ["supply_demand", "robocop", "rubberband_reaper", "quantum", "mean_reversion"]
    modes = [
        "none", "sniper", "regime_sync", "flywheel", "house_money", 
        "kelly", "hydra", "coil", "alpha", "gamma", 
        "smooth", "sentiment", "ghost", "phoenix", "runner"
    ]
    
    start_date = datetime(2026, 1, 24, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 31, tzinfo=timezone.utc)
    initial_capital = 1000.0
    
    all_results = []
    
    print(f"{'Strategy':<18} | {'Mode':<15} | {'Trades':<6} | {'Win %':<8} | {'PNL':<10} | {'Return %':<10}")
    print("-" * 80)
    
    for strat in strategies:
        # Override strategy in profile
        profile.strategy_variant = strat
        
        for mode in modes:
            os.environ["PERFORMANCE_MODE"] = mode
            
            ai_client = MockAIClient() if mode == "sentiment" else None
            backtester = Backtester(ib=None, settings=settings, ai_client=ai_client)
            backtester._is_crypto_backtest = True
            
            try:
                logging.getLogger().setLevel(logging.ERROR)
                result = backtester.run_backtest(
                    initial_capital=initial_capital,
                    start_date=start_date,
                    end_date=end_date,
                    symbols=symbols,
                    data_paths=data_paths
                )
                
                pnl = result.final_capital - initial_capital
                row = {
                    "strategy": strat,
                    "mode": mode,
                    "trades": len(result.trades),
                    "win_rate": result.win_rate,
                    "pnl": pnl,
                    "return_pct": result.total_return_pct
                }
                all_results.append(row)
                
                print(f"{strat:<18} | {mode:<15} | {len(result.trades):<6} | {result.win_rate:>7.1f}% | ${pnl:>9.2f} | {result.total_return_pct:>9.2f}%")
                
            except Exception as e:
                print(f"{strat:<18} | {mode:<15} | ERROR: {e}")

    # Save all results
    with open("clash_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

if __name__ == "__main__":
    run_clash()
