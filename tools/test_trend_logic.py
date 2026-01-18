
import sys
import os
sys.path.append(os.path.abspath("src"))

from tradebot_sci.market.trend import infer_trend_from_swings, TrendDirection, _mostly_monotonic
from tradebot_sci.market.models import Candle
from datetime import datetime

def make_candle(close, high=None, low=None):
    h = high if high else close + 1
    l = low if low else close - 1
    return Candle(
        timestamp=datetime.now(),
        open=close, high=h, low=l, close=close, volume=100
    )

def test_bullish_setup():
    # Simulate User's Scenario:
    # 1. Indication (Strong Move Up) -> Break Structure
    # 2. Correction (Higher Low)
    # 3. Continuation (Higher High)
    
    p = []
    # Pre-data to form a Swing Low at 80
    p += [85, 83, 81] # Down
    p += [80]         # Bottom
    p += [82, 81]     # Up (confirming 80)
    
    # 1. Indication (Rip from 81 to 95, breaking previous highs)
    p += [85, 90, 95] # Swing High 95
    
    # 2. Correction (Drop to 88 - HIGHER LOW > 80)
    # Shallow correction: 95 -> 92 -> 88 -> 92
    p += [92, 88, 92] # Swing Low 88
    
    # 3. Continuation (Rip to 100 - HIGHER HIGH > 95)
    p += [96, 100, 98] # Swing High 100
    
    candles = [make_candle(c) for c in p]
    
    print("\n--- Testing Bullish Setup (Indication -> HL 88 -> Continuation HH 100) ---")
    # Using defaults (swing_lookback=2)
    trend = infer_trend_from_swings(candles, swing_lookback=2, min_swings=2, window=100)
    print(f"Detected Trend: {trend.direction} (Strength: {trend.strength:.2f})")
    
    swings = trend.last_confirmed_swings
    print(f"Swings: {swings}")
    
    highs = [s['price'] for s in swings if s['type'] == 'high']
    lows = [s['price'] for s in swings if s['type'] == 'low']
    print(f"Highs: {highs}")
    print(f"Lows: {lows}")

if __name__ == "__main__":
    test_bullish_setup()
