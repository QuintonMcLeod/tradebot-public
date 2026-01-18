#!/usr/bin/env python3
"""Verbose backtest test with full logging."""

import sys
import logging
import statistics
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

from ib_insync import IB
from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

def main():
    print("=" * 60)
    print("VERBOSE BACKTEST TEST")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()

    # Test single symbol for speed
    test_symbols = ["SPY"]

    # Test parameters - Nov 11-12, 2024 (just 2 days)
    initial_capital = 1000.0
    start_date = datetime(2024, 11, 11, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2024, 11, 16, tzinfo=ZoneInfo("UTC"))

    print(f"Symbol: {test_symbols[0]}")
    print(f"Capital: ${initial_capital:,.2f}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    try:
        ib.connect(settings.broker.host, settings.broker.port, clientId=997)
        print("  Connected")
        print()
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    try:
        # Initialize AI client (disabled for deterministic backtest)
        ai_client = None

        # Create and run backtester
        backtester = Backtester(ib, settings, ai_client)

        print("Running backtest with full logging...")
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
        if hasattr(result, "potential_trades_blocked"):
            print(f"Potential Trades Blocked: {result.potential_trades_blocked}")
            if result.potential_trade_block_reasons:
                print("Potential Trade Blocks by Reason:")
                for reason, count in sorted(result.potential_trade_block_reasons.items()):
                    print(f"  {reason}: {count}")
        print(f"Total P&L: ${result.total_pnl:+,.2f}")
        print()

        if result.trades:
            winners = [t for t in result.trades if t.pnl > 0]
            losers = [t for t in result.trades if t.pnl <= 0]

            print(f"Winners: {len(winners)} ({len(winners)/len(result.trades)*100:.1f}%)")
            print(f"Losers: {len(losers)} ({len(losers)/len(result.trades)*100:.1f}%)")

            if winners:
                avg_win = sum(t.pnl for t in winners) / len(winners)
                print(f"Average Win: ${avg_win:+.2f}")

            if losers:
                avg_loss = sum(t.pnl for t in losers) / len(losers)
                print(f"Average Loss: ${avg_loss:+.2f}")

            if winners and losers:
                rr_ratio = abs(avg_win / avg_loss)
                print(f"Risk/Reward Ratio: {rr_ratio:.2f}:1")
                print(f"Breakeven Win Rate: {1/(1+rr_ratio)*100:.1f}%")

            hold_hours = [
                (trade.exit_time - trade.entry_time).total_seconds() / 3600.0
                for trade in result.trades
            ]
            if hold_hours:
                hold_min = min(hold_hours)
                hold_max = max(hold_hours)
                hold_avg = sum(hold_hours) / len(hold_hours)
                hold_median = statistics.median(hold_hours)
                under_24 = sum(1 for h in hold_hours if h < 24.0)
                print()
                print("Hold Durations (hours):")
                print(f"Min: {hold_min:.2f} | Avg: {hold_avg:.2f} | Median: {hold_median:.2f} | Max: {hold_max:.2f}")
                print(f"Trades < 24h: {under_24}/{len(hold_hours)}")

            print()
            print("Individual Trades:")
            for i, trade in enumerate(result.trades, 1):
                print(
                    f"{i}. {trade.symbol} {trade.entry_time} -> {trade.exit_time}: "
                    f"${trade.pnl:+,.2f} ({trade.exit_reason})"
                )
        else:
            print("No trades executed.")

        return 0

    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
