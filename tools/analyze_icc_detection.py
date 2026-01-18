#!/usr/bin/env python3
"""Analyze ICC signal detection to debug why signals aren't being found."""

from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
from tradebot_sci.config.loader import load_settings
from tradebot_sci.strategy.icc_signals import (
    detect_indication,
    detect_correction,
    detect_continuation,
    detect_liquidity_sweep,
    swing_points_close,
)
import os
from datetime import datetime, timezone

os.environ['PROFILE_NAME'] = 'coinbase_futures'
os.environ['CCXT_EXCHANGE'] = 'coinbase'

settings = load_settings()
provider = CCXTHistoricalDataProvider(settings)

# Analyze Nov 3, 2025 - the day we saw "Continuation detected" messages
symbol = 'BTC/USD'
start = datetime(2025, 11, 3, 12, 0, tzinfo=timezone.utc)
end = datetime(2025, 11, 3, 20, 0, tzinfo=timezone.utc)

print("=" * 80)
print(f"Analyzing {symbol} from {start} to {end}")
print("=" * 80)

# Get 15m candles (for indication detection on HTF)
candles_15m = provider.fetch_historical_candles(symbol, '15m', start, end)
print(f"\n15m Candles ({len(candles_15m)} total):")
for i, c in enumerate(candles_15m):
    print(f"  [{i:2d}] {c.timestamp} O:{c.open:8.2f} H:{c.high:8.2f} L:{c.low:8.2f} C:{c.close:8.2f}")

# Detect swings on 15m
swing_highs, swing_lows = swing_points_close(candles_15m, lookback=1)
print(f"\nSwing Points (lookback=1):")
print(f"  Swing Highs at indices: {swing_highs}")
print(f"  Swing Lows at indices: {swing_lows}")

if swing_highs:
    for idx in swing_highs:
        c = candles_15m[idx]
        print(f"    High[{idx}]: {c.timestamp} = {c.close:.2f}")
if swing_lows:
    for idx in swing_lows:
        c = candles_15m[idx]
        print(f"    Low[{idx}]: {c.timestamp} = {c.close:.2f}")

# Try indication detection
indication = detect_indication(candles_15m, swing_lookback=1)
print(f"\nIndication Detection (swing_lookback=1): {indication}")

# Get 5m candles
candles_5m = provider.fetch_historical_candles(symbol, '5m', start, end)
print(f"\n5m Candles (showing last 30 of {len(candles_5m)}):")
for i, c in enumerate(candles_5m[-30:], start=len(candles_5m)-30):
    print(f"  [{i:3d}] {c.timestamp} O:{c.open:8.2f} H:{c.high:8.2f} L:{c.low:8.2f} C:{c.close:8.2f}")

# Manual analysis: Look for ICC pattern
print("\n" + "=" * 80)
print("MANUAL ANALYSIS:")
print("=" * 80)

# Looking at the data, identify what SHOULD be detected
print("\nLooking at 15m data:")
print("  - 15:45: Close at 105,727 (potential low)")
print("  - 16:00-18:00: Rally from 105,729 to 107,447")
print("  - This looks like a LONG indication (break above previous high)")

print("\nLet's check if there's a swing high that gets broken:")
if swing_highs:
    last_high_idx = swing_highs[-1]
    last_high = candles_15m[last_high_idx].close
    print(f"  Last swing high: index {last_high_idx}, price {last_high:.2f}")
    
    # Check if any subsequent candle closes above it
    for i in range(last_high_idx + 1, len(candles_15m)):
        if candles_15m[i].close > last_high:
            print(f"  ✓ Candle {i} ({candles_15m[i].timestamp}) closed at {candles_15m[i].close:.2f} > {last_high:.2f}")
            print(f"    This SHOULD trigger a LONG indication!")
            break
    else:
        print(f"  ✗ No candle closed above {last_high:.2f}")
else:
    print("  No swing highs detected!")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("If indication is None but we see a clear break of structure,")
print("then the swing detection or indication logic is too strict.")
