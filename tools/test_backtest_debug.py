#!/usr/bin/env python3
"""Debug script to see what AI decisions are being made during backtest."""

import sys
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Set logging to DEBUG to see all decision reasoning
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

from ib_insync import IB
from tradebot_sci.config.loader import load_settings
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.simulation.backtester import Backtester

def main():
    print("=" * 60)
    print("DEBUG: AI DECISION ANALYSIS")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()

    # Test a single symbol for faster results
    test_symbols = ["SPY"]

    # Test parameters - Nov 11-12, 2024 (just 2 days for speed)
    initial_capital = 1000.0
    start_date = datetime(2024, 11, 11, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2024, 11, 12, tzinfo=ZoneInfo("UTC"))

    print(f"Symbol: {test_symbols[0]}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"This will show all AI decisions made during the period")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(settings.broker.host, settings.broker.port, clientId=998)
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

        print("Running backtest with full decision logging...")
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
        print("RESULTS")
        print("=" * 60)
        print()
        print(f"Total Trades: {len(result.trades)}")
        print(f"Total P&L: ${result.total_pnl:+,.2f}")
        print()

        if result.trades:
            for i, trade in enumerate(result.trades, 1):
                print(f"{i}. {trade.symbol}: ${trade.pnl:+,.2f} ({trade.exit_reason})")
        else:
            print("No trades executed.")
            print()
            print("Check the log output above to see what the AI decided.")

        return 0

    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
