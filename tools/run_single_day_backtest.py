#!/usr/bin/env python3
"""Quick single-day backtest for Nov 2025."""

import sys
import os
import logging

import logging
from datetime import datetime, timezone

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import load_settings

# Configure logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)

# Set environment
os.environ['PROFILE_NAME'] = 'coinbase_futures'
os.environ['CCXT_EXCHANGE'] = 'coinbase'

# Load settings
settings = load_settings()

# Test 5 days: Nov 1-5
START_DATE = datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)
INITIAL_CAPITAL = 150.0

print("=" * 80)
print(f"QUICK BACKTEST: {START_DATE.date()} (1 day)")
print("=" * 80)

# Run backtest
# Backtester(ib, settings, ai_client)
backtester = Backtester(None, settings, None)
result = backtester.run_backtest(
    start_date=START_DATE,
    end_date=END_DATE,
    initial_capital=INITIAL_CAPITAL,
)

print("\n" + "=" * 80)
print("RESULTS")
print("=" * 80)
print(f"Trades: {len(result.trades)}")
print(f"Final Capital: ${result.final_capital:.2f}")
print(f"Total PnL: ${result.total_pnl:.2f}")
print(f"Return: {result.total_return_pct:.2f}%")

if result.trades:
    print("\nTrade History:")
    for trade in result.trades:
        symbol = trade.symbol
        direction = trade.direction
        pnl = trade.pnl
        print(f"  {symbol} {direction}: ${pnl:.2f}")
