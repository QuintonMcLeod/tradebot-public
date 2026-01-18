#!/usr/bin/env python3
"""Backtest for a Random Week (March 10-17, 2025) to verify strategy generalization."""

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
    print("RANDOM WEEK CHECK: MARCH 10-17, 2025")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()
    settings.app.profile_name = "coinbase_futures"
    
    # BTC, ETH, SOL
    test_symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    initial_capital = 1000.0
    
    # Random week: March 10-17, 2025
    start_date = datetime(2025, 3, 10, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2025, 3, 17, 23, 59, 59, tzinfo=ZoneInfo("UTC"))

    print(f"Symbols: {', '.join(test_symbols)}")
    print(f"Initial capital: ${initial_capital:,.2f}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print()

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
    
    print()
    if result.trades:
        print("=" * 60)
        print("TRADE DETAILS")
        print("=" * 60)
        for i, trade in enumerate(result.trades, 1):
            print(f"{i}. {trade.exit_time.strftime('%Y-%m-%d %H:%M')} | {trade.symbol} {trade.direction} | P&L: ${trade.pnl:+,.2f} | Reason: {trade.exit_reason}")
    else:
        print("No trades executed.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
