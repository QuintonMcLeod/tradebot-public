
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

def run_nov_backtest_strict():
    # Force settings to Strict ICC mode
    os.environ["PROFILE_NAME"] = "coinbase_futures"
    os.environ["CCXT_EXCHANGE"] = "coinbase"
    os.environ["DEBUG_TRENDS"] = "0"
    
    settings = load_settings()
    profile = settings.get_active_profile()
    
    # [STRICT SETTINGS]
    profile.icc_auto_entry_enabled = True
    profile.icc_auto_entry_min_htf_strength = 0.5   # Tight trend filter
    profile.icc_auto_entry_require_sweep = True     # Require liquidity sweep
    profile.icc_auto_entry_allow_chop = False       # BLOCK trades in chop phase
    profile.risk_per_trade_pct = 1.0                # Enable Ratchet starting at 100%
    profile.ratchet_risk_enabled = True             # Scale risk dynamically
    profile.max_open_positions = 1                  # High quality focus
    profile.icc_entry_score_threshold = 60.0        # Strict score gate
    
    # Symbols (Spot for historical data)
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
    
    print(f"--- STARTING STRICT SIMULATION (NOV 2025) ---")
    print(f"Period: {start_date} to {end_date}")
    print(f"Capital: ${initial_capital}")
    print(f"HTF Strength Min: {profile.icc_auto_entry_min_htf_strength}")
    print(f"Chop Allowed: {profile.icc_auto_entry_allow_chop}")
    print(f"Sweep Required: {profile.icc_auto_entry_require_sweep}")
    
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
        else:
            print("\nNO TRADES TAKEN (Strategy successfully stood aside during bad conditions)")
                
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_nov_backtest_strict()
