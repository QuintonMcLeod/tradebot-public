
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.ai.client import TradeSciAIClient

def run_jan_backtest():
    # Force settings
    os.environ["PROFILE_NAME"] = "coinbase_futures"
    os.environ["CCXT_EXCHANGE"] = "coinbase"
    
    settings = load_settings()
    
    # [ANTIGRAVITY] User Request: "Use all coins" + "$182 Capital"
    # Full universe from settings_profiles.yaml
    symbols = [
        "AVAX/USD:USD-260130",
        "SHIB/USD:USD-260130",
        "ETH/USD:USD-260130",
        "ADA/USD:USD-260130",
        "SOL/USD:USD-260130",
        "DOGE/USD:USD-260130",
        "LINK/USD:USD-260130",
        "LTC/USD:USD-260130",
        "BTC/USD:USD-260130"
    ]
    
    # Date Range: Jan 1 2026 to Jan 14 2026
    start_date = datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2026, 1, 14, tzinfo=ZoneInfo("UTC"))
    initial_capital = 182.00
    
    print(f"--- STARTING SIMULATION ---")
    print(f"Period: {start_date} to {end_date}")
    print(f"Capital: ${initial_capital}")
    print(f"Symbols: {len(symbols)}")
    print(f"Risk: 100% (with Ratchet to 50% > $500)")
    
    # Initialize components
    # (No IB needed for pure crypto backtest mode via CCXT provider, but we pass None)
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
    run_jan_backtest()
