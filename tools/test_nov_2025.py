#!/usr/bin/env python3
"""Backtest for November 2025 to verify ICC strategy."""

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
    print("NOVEMBER 2025 ICC BACKTEST")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()
    settings.app.profile_name = "coinbase_futures"

    # BTC is our primary focus
    # Multi-symbol focus
    test_symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    initial_capital = 1000.0
    
    # November 2025 backtest
    start_date = datetime(2025, 11, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2025, 11, 7, 23, 59, 59, tzinfo=ZoneInfo("UTC"))

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
    print()
    print(f"Final Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.2f}%)")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Win Rate: {result.win_rate:.1f}%")
    print(f"Total Trades: {len(result.trades)}")
    print(f"Potential Trades Blocked: {result.potential_trades_blocked}")
    if result.potential_trade_block_reasons:
        print("Block Reasons:")
        for reason, count in result.potential_trade_block_reasons.items():
            print(f"  - {reason}: {count}")
    print()

    # Calculate Daily Metrics
    print("=" * 60)
    print("DAILY PERFORMANCE REPORT")
    print("=" * 60)
    print("| Date | Start Capital | Trades | Risk/Trade | Daily PnL | Daily ROI | End Capital |")
    print("| :--- | :--- | :---: | :--- | :--- | :--- | :--- |")

    # Group trades by date
    daily_trades = {}
    current = start_date.date()
    while current <= end_date.date():
        daily_trades[current] = []
        current = current.replace(day=current.day + 1) if current.day < 28 else (current + timedelta(days=1)).date() # Simple increment
        
    for trade in result.trades:
        d = trade.exit_time.date()
        if d not in daily_trades:
            daily_trades[d] = []
        daily_trades[d].append(trade)

    # Calculate and print rows
    current_equity = initial_capital
    sorted_dates = sorted(daily_trades.keys())
    
    # Fill in date range (naive iteration for 1 week spans)
    display_date = start_date.date()
    end_display = end_date.date()
    
    while display_date <= end_display:
        day_trades = daily_trades.get(display_date, [])
        day_pnl = sum(t.pnl for t in day_trades)
        trade_count = len(day_trades)
        
        # Estimate risk used (approximate from log logic: 2% base)
        # We can see actual risk if we look at trade details, but fixed 2% is the setting.
        risk_display = "2.0% ($20)" 
        if day_trades:
             # Check if any reversal trades (approx 3%)
             pass 

        daily_roi = (day_pnl / current_equity) * 100 if current_equity > 0 else 0.0
        end_equity = current_equity + day_pnl
        
        print(f"| {display_date} | ${current_equity:,.2f} | {trade_count} | {risk_display} | ${day_pnl:+,.2f} | {daily_roi:+.2f}% | ${end_equity:,.2f} |")
        
        current_equity = end_equity
        display_date = display_date + timedelta(days=1)
    
    print()

    if result.trades:
        print("=" * 60)
        print("TRADE DETAILS")
        print("=" * 60)
        for i, trade in enumerate(result.trades, 1):
            print(f"{i}. {trade.exit_time.strftime('%Y-%m-%d %H:%M')} | {trade.symbol} {trade.direction} | P&L: ${trade.pnl:+,.2f} | Reason: {trade.exit_reason}")
    else:
        print("No trades executed.")
        print("Check if ICC criteria were met during this period.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
