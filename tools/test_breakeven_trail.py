#!/usr/bin/env python3
"""Test breakeven trail feature by comparing with and without.

Uses the coinbase_futures profile with crypto data for testing.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

def run_comparison():
    # Use coinbase_futures for crypto testing (has data available)
    os.environ["PROFILE_NAME"] = "coinbase_futures"
    os.environ["CCXT_EXCHANGE"] = "coinbase"

    # Date range for testing
    start_date = datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2026, 1, 14, tzinfo=ZoneInfo("UTC"))
    initial_capital = 500.0

    # Test symbols - crypto that has data
    symbols = ["ETH/USD:USD-260130", "BTC/USD:USD-260130"]

    print("=" * 80)
    print("BREAKEVEN TRAIL FEATURE TEST")
    print("=" * 80)
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Capital: ${initial_capital}")
    print(f"Symbols: {symbols}")

    # Load settings
    settings = load_settings()
    profile = settings.profiles.get("coinbase_futures")

    # Enable breakeven trail for test
    print("\n--- TEST 1: WITH Breakeven Trail (3 pyramids, 1% trail) ---")

    # Set breakeven trail params
    if hasattr(profile, 'breakeven_trail_after_pyramids'):
        original_trail_after = profile.breakeven_trail_after_pyramids
        original_trail_pct = profile.breakeven_trail_pct
    else:
        original_trail_after = 0
        original_trail_pct = 0.01

    profile.breakeven_trail_after_pyramids = 3
    profile.breakeven_trail_pct = 0.01  # 1% for crypto

    backtester = Backtester(ib=None, settings=settings, ai_client=None)

    try:
        result_with = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )

        print(f"Final Capital: ${result_with.final_capital:.2f}")
        print(f"Total PnL: ${result_with.total_pnl:.2f}")
        print(f"Return: {result_with.total_return_pct:.2f}%")
        print(f"Trades: {len(result_with.trades)}")

        # Count trades that hit 3+ pyramids
        pyramid_trades = [t for t in result_with.trades if getattr(t, 'pyramid_count', 1) >= 3]
        print(f"Trades with 3+ pyramids: {len(pyramid_trades)}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        result_with = None

    # Test WITHOUT breakeven trail
    print("\n--- TEST 2: WITHOUT Breakeven Trail (disabled) ---")

    # Disable breakeven trail
    profile.breakeven_trail_after_pyramids = 0

    backtester2 = Backtester(ib=None, settings=settings, ai_client=None)

    try:
        result_without = backtester2.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )

        print(f"Final Capital: ${result_without.final_capital:.2f}")
        print(f"Total PnL: ${result_without.total_pnl:.2f}")
        print(f"Return: {result_without.total_return_pct:.2f}%")
        print(f"Trades: {len(result_without.trades)}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        result_without = None

    # Restore original settings
    profile.breakeven_trail_after_pyramids = original_trail_after
    profile.breakeven_trail_pct = original_trail_pct

    # Comparison
    if result_with and result_without:
        print("\n" + "=" * 80)
        print("COMPARISON")
        print("=" * 80)
        print(f"{'Metric':<30} {'With Trail':<20} {'Without Trail':<20} {'Diff':<15}")
        print("-" * 80)
        print(f"{'Final Capital':<30} ${result_with.final_capital:<19.2f} ${result_without.final_capital:<19.2f} ${result_with.final_capital - result_without.final_capital:<14.2f}")
        print(f"{'Total Return %':<30} {result_with.total_return_pct:<19.2f}% {result_without.total_return_pct:<19.2f}% {result_with.total_return_pct - result_without.total_return_pct:<14.2f}%")
        print(f"{'Trade Count':<30} {len(result_with.trades):<20} {len(result_without.trades):<20}")

        if result_with.total_return_pct > result_without.total_return_pct:
            print("\n✅ Breakeven trail IMPROVED returns!")
        elif result_with.total_return_pct < result_without.total_return_pct:
            print("\n⚠️ Breakeven trail REDUCED returns (may lock in profits too early)")
        else:
            print("\n➡️ No difference (feature may not have triggered)")

if __name__ == "__main__":
    run_comparison()
