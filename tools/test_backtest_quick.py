#!/usr/bin/env python3
"""Quick backtest test with $1,000 capital and crypto symbols."""

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
    print("QUICK BACKTEST: $1,000 CAPITAL - CRYPTO SYMBOLS")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()

    # Test with crypto symbols only (faster)
    test_symbols = ["BTCUSD", "ETHUSD", "SOLUSD"]

    # Test parameters - November 2025
    initial_capital = 1000.0
    end_date = datetime(2025, 12, 1, tzinfo=ZoneInfo("UTC"))
    start_date = datetime(2025, 11, 1, tzinfo=ZoneInfo("UTC"))

    print(f"Symbols: {', '.join(test_symbols)}")
    print(f"Initial capital: ${initial_capital:,.2f}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(settings.broker.host, settings.broker.port, clientId=999)
        print(f"  Connected")
        print()
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    try:
        # Initialize AI client
        ai_client = TradeSciAIClient(settings.ai)

        # Create and run backtester
        backtester = Backtester(ib, settings, ai_client)

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
        print("RESULTS")
        print("=" * 60)
        print()
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Capital: ${result.final_capital:,.2f}")
        print(f"Total P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.2f}%)")
        print(f"Max Drawdown: {result.max_drawdown:.2f}%")
        print()
        print(f"Total Trades: {result.total_trades}")
        print(f"Winning: {result.winning_trades} | Losing: {result.losing_trades}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print()

        if result.completed_trades:
            print("Trades:")
            for i, trade in enumerate(result.completed_trades, 1):
                pnl_pct = (trade.pnl / abs(trade.entry_price * trade.size)) * 100
                print(f"  {i}. {trade.symbol}: ${trade.pnl:+,.2f} ({pnl_pct:+.2f}%) - {trade.exit_reason}")

            print()

        print("Weekly Equity:")
        for week, equity in sorted(result.weekly_equity.items()):
            pnl = equity - initial_capital
            pct = (pnl / initial_capital) * 100
            print(f"  {week}: ${equity:,.2f} ({pct:+.2f}%)")

        print()
        print("=" * 60)
        print("DONE")
        print("=" * 60)

        return 0

    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
