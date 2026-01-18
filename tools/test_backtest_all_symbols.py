#!/usr/bin/env python3
"""Test backtest with $1,000 capital across all symbols for a profitable month."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
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
    print("BACKTEST: ALL SYMBOLS - $1,000 CAPITAL")
    print("=" * 60)
    print()

    # Load settings
    print("Loading settings...")
    settings = load_settings()
    profile = settings.get_active_profile()
    print(f"  Broker host: {settings.broker.host}")
    print(f"  Broker port: {settings.broker.port}")
    print()

    # Get all symbols from profile
    all_symbols = list(profile.symbols)
    print(f"Symbols to test ({len(all_symbols)}): {', '.join(all_symbols)}")
    print()

    # Test parameters - use November 2025 (recent month with market volatility)
    initial_capital = 1000.0
    end_date = datetime(2025, 12, 1, tzinfo=ZoneInfo("UTC"))
    start_date = datetime(2025, 11, 1, tzinfo=ZoneInfo("UTC"))

    print("Test parameters:")
    print(f"  Initial capital: ${initial_capital:,.2f}")
    print(f"  Start date: {start_date.date()}")
    print(f"  End date: {end_date.date()}")
    print(f"  Period: {(end_date - start_date).days} days")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(settings.broker.host, settings.broker.port, clientId=999)
        print(f"  Connected to {settings.broker.host}:{settings.broker.port}")
        print()
    except Exception as e:
        print(f"  ERROR: Failed to connect to IBKR: {e}")
        return 1

    try:
        # Initialize AI client
        print("Initializing AI client...")
        ai_client = TradeSciAIClient(settings.ai)
        print("  AI client ready")
        print()

        # Create backtester
        print("Creating backtester...")
        backtester = Backtester(ib, settings, ai_client)
        print("  Backtester ready")
        print()

        # Run backtest
        print("Running backtest...")
        print("  (This may take several minutes for all symbols)")
        print()

        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=all_symbols,
        )

        # Display results
        print()
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print()
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Capital: ${result.final_capital:,.2f}")
        print(f"Total P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.2f}%)")
        print(f"Max Drawdown: {result.max_drawdown:.2f}%")
        print()
        print(f"Total Trades: {result.total_trades}")
        print(f"Winning Trades: {result.winning_trades}")
        print(f"Losing Trades: {result.losing_trades}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print()

        if result.completed_trades:
            print("=" * 60)
            print(f"TRADE DETAILS ({len(result.completed_trades)} trades)")
            print("=" * 60)
            print()
            for i, trade in enumerate(result.completed_trades, 1):
                pnl_pct = (trade.pnl / (abs(trade.entry_price * trade.size))) * 100
                print(f"{i}. {trade.symbol}")
                print(f"   Entry: {trade.entry_time.date()} @ ${trade.entry_price:.2f}")
                print(f"   Exit:  {trade.exit_time.date()} @ ${trade.exit_price:.2f}")
                print(f"   Size:  {trade.size:+.2f} shares")
                print(f"   P&L:   ${trade.pnl:+,.2f} ({pnl_pct:+.2f}%)")
                print(f"   Reason: {trade.exit_reason}")
                print()

        print("=" * 60)
        print("WEEKLY EQUITY CURVE")
        print("=" * 60)
        print()

        for week, equity in sorted(result.weekly_equity.items()):
            week_pnl = equity - initial_capital
            week_pct = (week_pnl / initial_capital) * 100
            print(f"{week}: ${equity:,.2f} (P&L: ${week_pnl:+,.2f}, {week_pct:+.2f}%)")

        print()
        print("=" * 60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()

        return 0

    finally:
        print("Disconnecting from IBKR...")
        ib.disconnect()
        print("  Disconnected")
        print()


if __name__ == "__main__":
    sys.exit(main())
