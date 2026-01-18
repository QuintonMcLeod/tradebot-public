
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import logging
from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

# Configure logging at the entry point
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

def run_nov_backtest():
    # Force settings
    os.environ["PROFILE_NAME"] = "coinbase_futures"
    os.environ["CCXT_EXCHANGE"] = "coinbase"
    
    settings = load_settings()
    
    # Override with our optimized scoring
    profile = settings.get_active_profile()
    profile.icc_entry_score_threshold = 40.0
    profile.icc_score_continuation_points = 60.0
    profile.icc_score_sweep_points = 30.0
    profile.icc_auto_entry_require_sweep = False
    
    # [ANTIGRAVITY] User Request: "Use all coins" + "$150 Capital"
    # Note: Using SPOT symbols for historical backtest as '260130' futures didn't exist in Nov 2025.
    symbols = [
        "AVAX/USD",
        "SHIB/USD",
        "ETH/USD",
        "ADA/USD",
        "SOL/USD",
        "DOGE/USD",
        "LINK/USD",
        "LTC/USD",
        "BTC/USD"
    ]
    
    # Date Range: Nov 1 2025 to Nov 30 2025
    start_date = datetime(2025, 11, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2025, 11, 30, tzinfo=ZoneInfo("UTC"))
    initial_capital = 150.00
    
    print(f"--- STARTING SIMULATION (NOV 2025) ---")
    print(f"Period: {start_date} to {end_date}")
    print(f"Capital: ${initial_capital}")
    print(f"Symbols: {len(symbols)}")
    print(f"Risk: 100% (with Ratchet to 50% > $500)")
    
    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    
    try:
        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )
        
        print("\n--- RESULTS ---")
        print(f"Final Capital: ${result.final_capital:.2f}")
        print(f"Total PnL: ${result.total_pnl:.2f}")
        print(f"Return: {result.total_return_pct:.2f}%")
        print(f"Trades: {len(result.trades)}")
        
        if result.trades:
            print("\nTrade History:")
            for t in result.trades:
                print(f"{t.exit_time.date()} {t.symbol} {t.direction.upper()} PnL=${t.pnl:.2f} (Reason: {t.exit_reason})")
                
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_nov_backtest()
