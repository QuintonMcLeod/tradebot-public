#!/usr/bin/env python3
"""1-week backtest with parameter overrides."""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from ib_insync import IB
except ImportError:
    IB = None
from tradebot_sci.config.loader import load_settings
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.simulation.backtester import Backtester


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 1-week backtest with optional overrides.")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial capital for the backtest.")
    parser.add_argument("--days", type=int, default=7, help="Number of days for the test window.")
    parser.add_argument(
        "--symbols",
        type=str,
        default="SPY,QQQ,IWM,XLF,XLK",
        help="Comma-separated symbol list (e.g. BTC/USD,ETH/USD).",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    print("=" * 60)
    print(f"1-WEEK BACKTEST: ${args.capital:,.2f} CAPITAL")
    print("Trade by SCI Preferred Markets")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()
    # [ANTIGRAVITY ATTACHMENT] Force the fixed profile
    settings.app.profile_name = "coinbase_futures"

    # Default to Trade by SCI preferred markets - major equity ETFs with good liquidity.
    test_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not test_symbols:
        test_symbols = ["SPY", "QQQ", "IWM", "XLF", "XLK"]

    # Test parameters - Nov 11-15, 2024 (post-election rally, S&P 500 crossed 6000)
    initial_capital = float(args.capital)
    end_date = datetime.now(tz=ZoneInfo("UTC"))
    start_date = end_date - timedelta(days=max(1, args.days))

    context_line = "Post-election rally week, S&P 500 crossed 6000 for first time"
    if IB is None:
        # Fallback to crypto backtest when IBKR is unavailable.
        test_symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "ADA/USD", "LINK/USD"]
        end_date = datetime.now(tz=ZoneInfo("UTC"))
        start_date = end_date - timedelta(days=max(1, args.days))
        context_line = "CCXT crypto fallback (rolling 7-day window)"

    print(f"Symbols: {', '.join(test_symbols)}")
    print(f"Initial capital: ${initial_capital:,.2f}")
    duration_days = (end_date - start_date).days
    print(f"Period: {start_date.date()} to {end_date.date()} ({duration_days} days)")
    print(f"Context: {context_line}")
    print()

    # Connect to IBKR when available
    ib = None
    if IB is not None:
        print("Connecting to IBKR...")
        ib = IB()
        try:
            ib.connect(settings.broker.host, settings.broker.port, clientId=999)
            print("  Connected")
            print()
        except Exception as e:
            print(f"  ERROR: {e}")
            return 1
    else:
        print("Skipping IBKR connection: ib_insync not installed.")
        print()

    try:
        # Initialize AI client (disable for offline CCXT backtests)
        ai_client = TradeSciAIClient(settings.ai)
        if ib is None:
            ai_client = None

        # Create and run backtester
        backtester = Backtester(ib, settings, ai_client)

        print("Running 1-week backtest...")
        print("  (This will take a few minutes)")
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
        print("BACKTEST RESULTS")
        print("=" * 60)
        print()
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Duration: {duration_days} days ({context_line})")
        print()
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Capital: ${result.final_capital:,.2f}")
        print(f"Total P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.2f}%)")
        print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
        print()
        total_trades = len(result.trades)
        winning_trades = sum(1 for t in result.trades if t.pnl > 0)
        losing_trades = sum(1 for t in result.trades if t.pnl < 0)

        print(f"Total Trades: {total_trades}")
        print(f"Winning: {winning_trades} | Losing: {losing_trades}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print()

        if result.trades:
            print("=" * 60)
            print(f"TRADE DETAILS ({len(result.trades)} trades)")
            print("=" * 60)
            print()
            for i, trade in enumerate(result.trades, 1):
                pnl_pct = (trade.pnl / abs(trade.entry_price * trade.size)) * 100
                duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
                print(f"{i}. {trade.symbol}")
                print(f"   Entry: {trade.entry_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.entry_price:.2f}")
                print(f"   Exit:  {trade.exit_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.exit_price:.2f}")
                print(f"   Duration: {duration:.1f} hours")
                print(f"   Size: {trade.size:+.2f} shares")
                print(f"   P&L: ${trade.pnl:+,.2f} ({pnl_pct:+.2f}%)")
                print(f"   Exit reason: {trade.exit_reason}")
                print()
        else:
            print("No trades executed during this period.")
            print("(This is normal for a selective ICC strategy - waiting for high-quality setups)")
            print()

        print("=" * 60)
        print("WEEKLY EQUITY")
        print("=" * 60)
        print()

        for week, equity in sorted(result.weekly_equity.items()):
            pnl = equity - initial_capital
            pct = (pnl / initial_capital) * 100
            print(f"{week}: ${equity:,.2f} (P&L: ${pnl:+,.2f}, {pct:+.2f}%)")

        print()
        print("=" * 60)
        print("TEST COMPLETED")
        print("=" * 60)

        return 0

    finally:
        if ib is not None:
            ib.disconnect()
            print()


if __name__ == "__main__":
    sys.exit(main())
