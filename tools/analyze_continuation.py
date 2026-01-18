#!/usr/bin/env python3
"""Analyze Continuation detection logic with debug logging."""

from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
from tradebot_sci.config.loader import load_settings
from tradebot_sci.strategy.icc_signals import (
    detect_indication,
    detect_correction,
    detect_continuation,
    swing_points_close,
)
import os
from datetime import datetime, timezone

import logging
import sys

# Configure logging
logging.basicConfig(
    stream=sys.stderr, 
    level=logging.INFO,
    format='%(message)s'
)

# Enable debug logs for ICC
os.environ['DEBUG_ICC'] = '1'
os.environ['PROFILE_NAME'] = 'coinbase_futures'
os.environ['CCXT_EXCHANGE'] = 'coinbase'

settings = load_settings()
provider = CCXTHistoricalDataProvider(settings)

# Focus on Nov 3, 2025
symbol = 'BTC/USD'
start = datetime(2025, 11, 3, 10, 0, tzinfo=timezone.utc)
end = datetime(2025, 11, 3, 22, 0, tzinfo=timezone.utc)

# Fetch HTF candles (15m) which are now used for ALL detections
print("Fetching 15m candles...")
candles = provider.fetch_historical_candles(symbol, '15m', start, end)
print(f"Loaded {len(candles)} candles.")

# We know there's a correction around 13:00 (index ~12 since start is 10:00 -> 3 hours = 12 candles)
# Let's scan through
found_setup = False

print("\nScanning...")
for i in range(10, len(candles)):
    window = candles[:i+1]
    
    # 1. Detect Indication
    indication = detect_indication(window, swing_lookback=1, max_swings_to_check=3)
    if not indication:
        continue
        
    # 2. Detect Correction
    correction = detect_correction(
        window, 
        indication, 
        swing_lookback=1,
        # Use defaults (0.10, 0.90) set in icc_signals.py
    )
    if not correction:
        continue
        
    print(f"\n[{i}] {candles[i].timestamp} Setup Found!")
    print(f"  Indication: {indication.direction} @ {indication.level}")
    print(f"  Correction: {correction.retracement_pct:.2%}")
    
    # 3. Try Detect Continuation
    # We purposefully set window to be the same candles 
    # (since in engine.py we pass the full history/snapshot)
    
    print("  Checking Continuation...")
    continuation = detect_continuation(
        window,
        indication.direction,
        sweep=None,
        indication=indication,
        correction=correction,
        require_sweep=False,
        require_indication=False,
        require_correction=False,
        swing_lookback=1,
        confirmation_bars=2
    )
    
    if continuation:
        print(f"  SUCCESS! Continuation detected!")
        found_setup = True
        break
    else:
        print("  FAILED. See debug logs above/below.")

if not found_setup:
    print("\nNo full ICC sequence found in this window.")
