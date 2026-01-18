#!/usr/bin/env python3
"""
High Risk Simulation: Risks $100 per trade (10% of $1000).
Tests the "Risk of Ruin" hypothesis.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

def main():
    print("=" * 60)
    print("HIGH RISK SIMULATION ($100/Trade)")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()
    settings.app.profile_name = "coinbase_futures"
    
    # [ANTIGRAVITY OVERRIDE] Set Risk to 10% ($100 on $1000)
    profile = settings.profiles["coinbase_futures"]
    profile.risk_per_trade_pct = 0.10
    profile.reversal_risk_per_trade = 0.10
    profile.max_exposure_pct = 0.50 # Allow up to 5 open trades
    
    # Use the Extended Period (Nov 1-14)
    start_date = datetime(2024, 11, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2024, 11, 14, 23, 59, 59, tzinfo=ZoneInfo("UTC"))

    test_symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    initial_capital = 1000.0

    print(f"Symbols: {', '.join(test_symbols)}")
    print(f"Initial capital: ${initial_capital:,.2f}")
    print(f"Risk per Trade: 10% (~$100)")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print("-" * 60)

    # Create and run backtester
    backtester = Backtester(None, settings, None)

    print("Running backtest...")
    result = backtester.run_backtest(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        symbols=test_symbols,
    )

    # Display results
    print()
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Final Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.2f}%)")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Win Rate: {result.win_rate:.1f}%")
    print(f"Total Trades: {len(result.trades)}")
    
    # Warning check
    if result.final_capital < 500:
        print("\n[CRITICAL] Account value dropped below 50%!")
    if result.final_capital <= 0:  
        print("\n[GAME OVER] Account Bankrupted.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
