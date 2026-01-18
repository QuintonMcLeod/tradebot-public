#!/usr/bin/env python3
"""Analyze losing trades to find patterns for score filtering.

Runs backtest and captures detailed entry conditions for each trade.
"""

import sys
import os
import logging
import json
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import load_settings

# Configure logging
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,  # Reduce noise
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)

# Enable info for our analysis
logger = logging.getLogger("trade_analyzer")
logger.setLevel(logging.INFO)

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
print("TRADE PATTERN ANALYSIS")
print("=" * 80)

# Run backtest
backtester = Backtester(None, settings, None)
result = backtester.run_backtest(
    start_date=START_DATE,
    end_date=END_DATE,
    initial_capital=INITIAL_CAPITAL,
)

print(f"\nTotal Trades: {len(result.trades)}")
print(f"Final Capital: ${result.final_capital:.2f}")
print(f"Return: {result.total_return_pct:.2f}%")

# Categorize trades
winners = [t for t in result.trades if t.pnl > 0]
losers = [t for t in result.trades if t.pnl < 0]
breakeven = [t for t in result.trades if t.pnl == 0]

print(f"\nWinners: {len(winners)} (${sum(t.pnl for t in winners):.2f})")
print(f"Losers: {len(losers)} (${sum(t.pnl for t in losers):.2f})")
print(f"Breakeven: {len(breakeven)}")

# Analyze by symbol
print("\n" + "=" * 80)
print("BY SYMBOL")
print("=" * 80)
symbols = set(t.symbol for t in result.trades)
for symbol in sorted(symbols):
    sym_trades = [t for t in result.trades if t.symbol == symbol]
    sym_winners = [t for t in sym_trades if t.pnl > 0]
    sym_losers = [t for t in sym_trades if t.pnl < 0]
    win_rate = len(sym_winners) / len(sym_trades) * 100 if sym_trades else 0
    total_pnl = sum(t.pnl for t in sym_trades)
    print(f"  {symbol}: {len(sym_trades)} trades, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}")

# Analyze by direction
print("\n" + "=" * 80)
print("BY DIRECTION")
print("=" * 80)
for direction in ["long", "short"]:
    dir_trades = [t for t in result.trades if t.direction == direction]
    dir_winners = [t for t in dir_trades if t.pnl > 0]
    win_rate = len(dir_winners) / len(dir_trades) * 100 if dir_trades else 0
    total_pnl = sum(t.pnl for t in dir_trades)
    print(f"  {direction.upper()}: {len(dir_trades)} trades, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}")

# Analyze biggest winners and losers
print("\n" + "=" * 80)
print("TOP 10 WINNERS")
print("=" * 80)
for t in sorted(winners, key=lambda x: x.pnl, reverse=True)[:10]:
    print(f"  {t.symbol} {t.direction}: ${t.pnl:.2f}")

print("\n" + "=" * 80)
print("TOP 10 LOSERS")
print("=" * 80)
for t in sorted(losers, key=lambda x: x.pnl)[:10]:
    print(f"  {t.symbol} {t.direction}: ${t.pnl:.2f}")

# Look for patterns in entry time
print("\n" + "=" * 80)
print("BY HOUR OF DAY (UTC)")
print("=" * 80)
hour_stats = {}
for t in result.trades:
    if hasattr(t, 'entry_time') and t.entry_time:
        hour = t.entry_time.hour
        if hour not in hour_stats:
            hour_stats[hour] = {"wins": 0, "losses": 0, "pnl": 0.0}
        if t.pnl > 0:
            hour_stats[hour]["wins"] += 1
        else:
            hour_stats[hour]["losses"] += 1
        hour_stats[hour]["pnl"] += t.pnl

for hour in sorted(hour_stats.keys()):
    s = hour_stats[hour]
    total = s["wins"] + s["losses"]
    wr = s["wins"] / total * 100 if total > 0 else 0
    print(f"  {hour:02d}:00 UTC: {total} trades, WR: {wr:.1f}%, PnL: ${s['pnl']:.2f}")

# Summary recommendations
print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

# Check if long or short is clearly worse
long_trades = [t for t in result.trades if t.direction == "long"]
short_trades = [t for t in result.trades if t.direction == "short"]
long_pnl = sum(t.pnl for t in long_trades)
short_pnl = sum(t.pnl for t in short_trades)

if long_pnl < 0 and short_pnl > 0:
    print("  [!] LONG trades are net negative. Consider disabling or filtering longs more aggressively.")
elif short_pnl < 0 and long_pnl > 0:
    print("  [!] SHORT trades are net negative. Consider disabling or filtering shorts more aggressively.")
else:
    print("  Both directions have similar performance. No directional filter recommended.")

# Check if certain symbols should be avoided
worst_symbol = None
worst_pnl = 0
for symbol in symbols:
    sym_pnl = sum(t.pnl for t in result.trades if t.symbol == symbol)
    if sym_pnl < worst_pnl:
        worst_pnl = sym_pnl
        worst_symbol = symbol

if worst_symbol and worst_pnl < -5:
    print(f"  [!] {worst_symbol} has the worst performance (${worst_pnl:.2f}). Consider removing from symbol list.")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
