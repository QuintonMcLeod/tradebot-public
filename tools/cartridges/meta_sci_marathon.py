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
        return "BULLISH" # Always bullish for the January upturn

def run_marathon():
    # Force settings
    os.environ["PROFILE_NAME"] = "crypto_247"
    # FORCE META-SCI VARIANT
    os.environ["STRATEGY_VARIANT"] = "meta_sci"
    
    settings = load_settings()
    
    # RELAX THRESHOLDS for the experiment to get volume
    profile = settings.get_active_profile()
    profile.strategy_variant = "meta_sci" # Ensure profile reflects it
    profile.icc_entry_score_threshold = 20.0
    profile.icc_auto_entry_min_htf_strength = 0.1
    profile.multi_position_enabled = True
    profile.max_concurrent_positions = 5
    
    # Symbols and Data Paths
    DATA_BASE = Path(__file__).resolve().parents[2] / "data"
    
    # Mix of Crypto and Forex for a broad test
    symbols = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"]
    data_paths = {
        "BTCUSD": str(DATA_BASE / "crypto_marathon" / "BTCUSD_5m.json"),
        "ETHUSD": str(DATA_BASE / "crypto_marathon" / "ETHUSD_5m.json"),
        "EURUSD": str(DATA_BASE / "forex_backtest" / "EURUSD_5m.json"),
        "GBPUSD": str(DATA_BASE / "forex_backtest" / "GBPUSD_5m.json")
    }
    
    modes = [
        "none", "sniper", "regime_sync", "flywheel", "house_money", 
        "kelly", "hydra", "coil", "alpha", "gamma", 
        "smooth", "sentiment", "ghost", "phoenix", "runner"
    ]
    
    # Date Range: Last week of January 2026 (The "Favorite Week")
    start_date = datetime(2026, 1, 24, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 31, tzinfo=timezone.utc)
    initial_capital = 1000.0
    
    results = []
    
    print(f"\n🏆 META-SCI MARATHON (Jan 24-31) 🏆")
    print(f"{'Mode':<15} | {'Trades':<6} | {'Win %':<8} | {'PNL':<10} | {'Return %':<10}")
    print("-" * 65)
    
    for mode in modes:
        os.environ["PERFORMANCE_MODE"] = mode
        
        # Initialize backtester
        ai_client = MockAIClient() if mode == "sentiment" else None
        backtester = Backtester(ib=None, settings=settings, ai_client=ai_client)
        backtester._is_crypto_backtest = True # Handle 24/7
        
        try:
            # Silence logging during backtest
            logging.getLogger().setLevel(logging.ERROR)
            
            result = backtester.run_backtest(
                initial_capital=initial_capital,
                start_date=start_date,
                end_date=end_date,
                symbols=symbols,
                data_paths=data_paths
            )
            
            pnl = result.final_capital - initial_capital
            results.append({
                "mode": mode,
                "trades": len(result.trades),
                "win_rate": result.win_rate,
                "pnl": pnl,
                "return_pct": result.total_return_pct
            })
            
            print(f"{mode:<15} | {len(result.trades):<6} | {result.win_rate:>7.1f}% | ${pnl:>9.2f} | {result.total_return_pct:>9.2f}%")
            
        except Exception as e:
            print(f"{mode:<15} | ERROR: {e}")

    # Save results
    with open("meta_sci_marathon_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_marathon()
