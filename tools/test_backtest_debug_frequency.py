#!/usr/bin/env python3
"""Debug backtest to diagnose low trade frequency issue."""

import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ib_insync import IB
from tradebot_sci.config.loader import load_settings
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.simulation.backtester import Backtester


def main():
    print("=" * 60)
    print("DEBUG BACKTEST: Trade Frequency Investigation")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()

    # Test with just SPY to reduce noise
    test_symbols = ["SPY"]

    # Test parameters - Nov 11, 2024 (first day only for speed)
    initial_capital = 1000.0
    start_date = datetime(2024, 11, 11, 14, 30, tzinfo=ZoneInfo("UTC"))  # Market open
    end_date = datetime(2024, 11, 11, 17, 0, tzinfo=ZoneInfo("UTC"))     # First 2.5 hours

    print(f"Symbols: {', '.join(test_symbols)}")
    print(f"Initial capital: ${initial_capital:,.2f}")
    print(f"Period: {start_date} to {end_date} (2.5 hours)")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(settings.broker.host, settings.broker.port, clientId=999)
        print("  Connected")
        print()
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    try:
        # Initialize AI client
        ai_client = TradeSciAIClient(settings.ai)

        # Create and run backtester
        backtester = Backtester(ib, settings, ai_client)

        print("Running debug backtest...")
        print("  (Watch for DEBUG logs showing decision checks and AI calls)")
        print()

        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=test_symbols,
        )

        # Display results
        print()
        print("=" * 60)
        print("DEBUG RESULTS")
        print("=" * 60)
        print()
        print(f"Total Trades: {len(result.trades)}")
        print(f"Final Capital: ${result.final_capital:,.2f}")
        print(f"P&L: ${result.total_pnl:+,.2f}")
        print()

        if result.trades:
            for trade in result.trades:
                print(f"Trade: {trade.symbol} {trade.direction}")
                print(f"  Entry: {trade.entry_time} @ ${trade.entry_price:.2f}")
                print(f"  Exit: {trade.exit_time} @ ${trade.exit_price:.2f}")
                print(f"  P&L: ${trade.pnl:+,.2f}")
                print()

        return 0

    finally:
        ib.disconnect()
        print()


if __name__ == "__main__":
    sys.exit(main())
