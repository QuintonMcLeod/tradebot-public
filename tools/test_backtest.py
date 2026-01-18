#!/usr/bin/env python3
"""Standalone test script for the backtester.

This script validates the backtest functionality without requiring the GUI.
Run it to ensure the backtester works before testing through the GUI.

Usage:
    poetry run python tools/test_backtest.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester


def main():
    """Run a simple backtest to validate the system."""
    print("=" * 60)
    print("BACKTEST TEST SCRIPT")
    print("=" * 60)
    print()

    # Load settings
    print("Loading settings...")
    settings = load_settings()
    print(f"  Profile: {settings.app.profile_name}")
    print(f"  Broker host: {settings.broker.host if settings.broker else 'N/A'}")
    print(f"  Broker port: {settings.broker.port if settings.broker else 'N/A'}")
    print()

    # Setup test parameters
    initial_capital = 10000.0
    end_date = datetime.now(ZoneInfo("UTC"))
    start_date = end_date - timedelta(days=30)  # 1 month test
    symbols = []  # Filled after we know if IBKR is available

    print("Test parameters:")
    print(f"  Initial capital: ${initial_capital:,.2f}")
    print(f"  Start date: {start_date.date()}")
    print(f"  End date: {end_date.date()}")
    print(f"  Symbols: (pending)")
    print()

    # Connect to IBKR (optional)
    print("Connecting to IBKR...")
    try:
        from ib_insync import IB
        ib = IB()
        host = settings.broker.host if settings.broker else "127.0.0.1"
        port = settings.broker.port if settings.broker else 7497
        ib.connect(host, port, clientId=999)
        print(f"  Connected to {host}:{port}")
    except Exception as e:
        print(f"  Skipping IBKR connection: {e}")
        ib = None
    print()

    if ib is None:
        # Use CCXT crypto symbols when IBKR isn't available.
        # Prefer an existing market symbol with '/' if present.
        market_symbols = list(settings.market.symbols or [])
        symbols = [s for s in market_symbols if "/" in s]
        if not symbols:
            symbols = ["BTC/USD"]
        # Shorten window to reduce CCXT rate limits.
        start_date = end_date - timedelta(days=2)
    else:
        symbols = ["SPY"]

    print(f"  Symbols: {symbols}")

    try:
        # Initialize AI client
        print("Initializing AI client...")
        if ib is None:
            ai_client = None
            print("  AI client disabled (offline backtest)")
        else:
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
        print("  (This may take several minutes)")
        print()

        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )

        # Display results
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print()
        print(f"Period: {result.start_date.date()} to {result.end_date.date()}")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Capital: ${result.final_capital:,.2f}")
        print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:+.2f}%)")
        print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
        print()
        print(f"Total Trades: {len(result.trades)}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        if result.avg_win > 0:
            print(f"Avg Win: ${result.avg_win:.2f}")
        if result.avg_loss < 0:
            print(f"Avg Loss: ${result.avg_loss:.2f}")
        print()

        if result.weekly_equity:
            print("=" * 60)
            print("WEEKLY EQUITY CURVE")
            print("=" * 60)
            print()
            sorted_weeks = sorted(result.weekly_equity.items())
            for week, equity in sorted_weeks:
                pnl = equity - result.initial_capital
                pct = (pnl / result.initial_capital) * 100
                print(f"{week}: ${equity:,.2f} (P&L: ${pnl:+.2f}, {pct:+.2f}%)")
            print()

        if result.trades:
            print("=" * 60)
            print(f"TRADE LOG (showing {min(10, len(result.trades))} trades)")
            print("=" * 60)
            print()
            for trade in result.trades[-10:]:
                print(
                    f"{trade.entry_time.date()} {trade.symbol} {trade.direction.upper()}: "
                    f"Entry=${trade.entry_price:.2f} Exit=${trade.exit_price:.2f} "
                    f"P&L=${trade.pnl:+.2f} ({trade.exit_reason})"
                )
            print()

        print("=" * 60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 60)
        return 0

    except Exception as e:
        print()
        print("=" * 60)
        print("ERROR")
        print("=" * 60)
        print(f"\n{type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if ib and ib.isConnected():
            ib.disconnect()
            print("\nDisconnected from IBKR")


if __name__ == "__main__":
    sys.exit(main())
