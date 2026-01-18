#!/usr/bin/env python3
"""Run a 30-day crypto backtest and generate a P&L report."""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# Silence verbose libs
logging.getLogger("ib_insync").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def main():
    print("=" * 60)
    print("CRYPTO BACKTEST (30 DAYS)")
    print("=" * 60)

    # Load settings
    settings = load_settings()
    
    # Force settings for backtest if needed
    # We want robust protections
    settings.app.profile_name = "auto_schedule" # Use the AI schedule profile
    
    # 3-day validation window
    end_date = datetime.now(ZoneInfo("UTC"))
    start_date = end_date - timedelta(days=3)
    initial_capital = 10000.0
    
    # Major liquid pairs
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "ADA/USD", "LINK/USD"]

    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Capital: ${initial_capital:,.2f}")
    print("-" * 60)

    # Initialize components
    # Note: We pass None for IB because we are using CCXT provider
    ai_client = TradeSciAIClient(settings.ai)
    backtester = Backtester(None, settings, ai_client) 

    # Run
    try:
        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )
    except Exception as e:
        logging.exception("Backtest failed")
        return 1

    # Generate Report
    print("\n" + "=" * 60)
    print("BACKTEST REPORT")
    print("=" * 60)
    
    print(f"\nFinal Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:+.2f}%)")
    print(f"Total Trades: {len(result.trades)}")
    print(f"Win Rate: {result.win_rate:.1f}%")
    
    if result.trades:
        total_fees = sum(t.fees_paid for t in result.trades)
        total_slippage = sum(t.slippage for t in result.trades)
        print(f"Total Fees Paid: ${total_fees:,.2f}")
        print(f"Total Slippage: ${total_slippage:,.2f}")

    print("\n--- Weekly P&L ---")
    sorted_weeks = sorted(result.weekly_equity.items())
    # Calculate weekly deltas
    prev_equity = initial_capital
    for week, equity in sorted_weeks:
        pnl = equity - prev_equity
        pct = (pnl / prev_equity) * 100 if prev_equity > 0 else 0
        print(f"Week {week}: ${equity:,.2f} (P&L: ${pnl:+,.2f}, {pct:+.2f}%)")
        prev_equity = equity

    print("\n--- Daily P&L (Last 10 Days) ---")
    # Group trades by day
    daily_pnl = {}
    for t in result.trades:
        day = t.exit_time.strftime("%Y-%m-%d")
        daily_pnl[day] = daily_pnl.get(day, 0.0) + t.pnl
    
    for day in sorted(daily_pnl.keys())[-10:]:
        print(f"{day}: ${daily_pnl[day]:+,.2f}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
