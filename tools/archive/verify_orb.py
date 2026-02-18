import sys
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import List

# Setup path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState
from tradebot_sci.strategy.variants.orb_breakout import ORBStrategy

def create_candle(ts: datetime, open: float, high: float, low: float, close: float) -> Candle:
    return Candle(timestamp=ts, open=open, high=high, low=low, close=close, volume=1000)

def run_verification():
    print("--- Verifying ORB Strategy ---")
    
    # Setup Range 9:30 - 9:45 NY
    # We'll use a hypothetical date
    base_date = datetime(2026, 2, 2, tzinfo=ZoneInfo("America/New_York")) # A Monday
    
    strat = ORBStrategy()
    
    candles = []
    # 1. Create Range (9:30-9:45)
    # Range High: 100.00, Low: 99.00
    current_time = base_date.replace(hour=9, minute=30)
    
    # 9:30 - 9:45: Chop between 99 and 100
    for i in range(15):
        c = create_candle(current_time, 99.5, 100.0, 99.0, 99.5)
        candles.append(c)
        current_time += timedelta(minutes=1)
        
    print(f"Generated {len(candles)} range candles.")
    
    # 2. Breakout (9:46)
    # Bull Breakout: Close > 100
    breakout_c = create_candle(current_time, 99.8, 100.5, 99.8, 100.2)
    candles.append(breakout_c)
    current_time += timedelta(minutes=1)
    
    # 3. Retest (9:47)
    # Price touches 100.00 (High Level)
    retest_c = create_candle(current_time, 100.3, 100.4, 99.95, 100.1) # Low 99.95 touches 100
    candles.append(retest_c)
    current_time += timedelta(minutes=1)
    
    # 4. Flag (9:48)
    # Small body near 100
    # Open 100.1, Close 100.15 (Body 0.05), Range (100.05-100.2)
    flag_c = create_candle(current_time, 100.1, 100.2, 100.05, 100.15)
    candles.append(flag_c)
    current_time += timedelta(minutes=1)
    
    # 5. Trigger (9:49)
    # Breaks Flag High (100.2)
    trigger_c = create_candle(current_time, 100.15, 100.5, 100.15, 100.4)
    candles.append(trigger_c)
    
    snapshot = MarketSnapshot(
        symbol="TEST",
        timeframe="1m",
        candles=candles,
        trend_htf=TrendState("neutral", strength=0.5),
        trend_ltf=TrendState("bullish", strength=1.0)
    )
    
    decision = strat.check_entry_signal(snapshot, {})
    
    if decision:
        print(f"✅ SUCCESS: Signal Generated!")
        print(f"   Action: {decision.action}")
        print(f"   Entry: {decision.entry_price} (Target: {decision.take_profit})")
        print(f"   Reason: {decision.structure_summary}")
        
        # Validate Entry Logic
        if decision.entry_price == 100.4:
            print("   Entry Price Verified (Break of Flag)")
        else:
             print(f"   ⚠️ Unexpected Entry Price: {decision.entry_price}")
             
    else:
        print("❌ FAILURE: No Signal Generated")
        # Debug why
        # (The strategy prints/logs would help, but we rely on output)

if __name__ == "__main__":
    run_verification()
