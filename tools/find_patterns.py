#!/usr/bin/env python3
print("DEBUG: Script starting...", flush=True)

"""
Pattern Hunter: Reverse Engineer Winning Setups
Scans historical data for significant moves and analyzes pre-move conditions.
"""

import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict
import math

# Add project root to path
print("DEBUG: Configuring path...", flush=True)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
from tradebot_sci.market.models import Candle
from tradebot_sci.market.providers import MockMarketDataProvider

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
        
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
            
    # Simple average logic mimicking standard RSI
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def main():
    print("=" * 60, flush=True)
    print("🤖 PATTERN HUNTER: REVERSE ENGINEERING WINNERS", flush=True)
    print("=" * 60, flush=True)

    # 1. Load Data
    settings = load_settings()
    settings.app.profile_name = "coinbase_futures" 
    
    # Instantiate CCXT Provider directly
    provider = CCXTHistoricalDataProvider(settings, exchange_id="coinbase")
    
    start_date = datetime(2025, 11, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2025, 11, 7, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
    symbol = "BTC/USD"
    timeframe = "1m" # 1m for scalping precision

    print(f"Scanning {symbol} ({timeframe}) from {start_date.date()} to {end_date.date()}...")
    
    candles = provider.fetch_historical_candles(symbol, timeframe, start_date, end_date)
    if not candles:
        print("No data found!")
        return

    # Convert to simple list of dicts for easier indexing
    data = [{
        'ts': c.timestamp, 
        'open': c.open, 'high': c.high, 'low': c.low, 'close': c.close, 'vol': c.volume
    } for c in candles]
    
    # 2. Identify "Winning Moves" and "Fakeouts"
    look_forward = 60 # 1 hour ahead
    min_move_pct = 0.01 # 1.0% move (stronger signal)
    max_drawdown_pct = 0.003 # 0.3% drawdown tolerance (tight)
    
    winning_setups = []
    fakeout_setups = []
    
    print(f"Analyzing {len(data)} candles for Winners and Fakeouts...")
    
    last_signal_idx = -100
    
    for i in range(50, len(data) - look_forward): 
        if i < last_signal_idx + 15: # Don't analyze overlapping signals too closely
            continue
            
        current_close = data[i]['close']
        future_window = data[i+1:i+1+look_forward]
        
        # Check Long Candidates (Sweep Low)
        lookback = 20
        recent_window = data[i-lookback:i]
        recent_low = min(d['low'] for d in recent_window)
        current_bar = data[i]
        
        is_sweep_long = current_bar['low'] <= recent_low
        
        if is_sweep_long:
            # Did it WIN or FAKEOUT?
            max_high = max(d['high'] for d in future_window)
            min_low = min(d['low'] for d in future_window)
            
            up_move = (max_high - current_close) / current_close
            drawdown = (current_close - min_low) / current_close
            
            if up_move >= min_move_pct and drawdown <= max_drawdown_pct:
                winning_setups.append(analyze_setup(data, i, "long", "WIN"))
                last_signal_idx = i
            elif drawdown > max_drawdown_pct: # Immediate failure
                # Define Fakeout: Failed immediately after sweep, continued lower
                fakeout_setups.append(analyze_setup(data, i, "long", "FAKEOUT"))
                last_signal_idx = i
                
        # Check Short Candidates (Sweep High)
        recent_high = max(d['high'] for d in recent_window)
        is_sweep_short = current_bar['high'] >= recent_high
        
        if is_sweep_short:
            # Did it WIN or FAKEOUT?
            min_future_low = min(d['low'] for d in future_window)
            max_future_high = max(d['high'] for d in future_window)
            
            down_move = (current_close - min_future_low) / current_close
            short_drawdown = (max_future_high - current_close) / current_close
            
            if down_move >= min_move_pct and short_drawdown <= max_drawdown_pct:
                winning_setups.append(analyze_setup(data, i, "short", "WIN"))
                last_signal_idx = i
            elif short_drawdown > max_drawdown_pct: # Immediate failure
                fakeout_setups.append(analyze_setup(data, i, "short", "FAKEOUT"))
                last_signal_idx = i

    analyze_comparison(winning_setups, fakeout_setups)

def analyze_setup(data, index, direction, result):
    # Capture the "DNA"
    
    # 1. RSI (Momentum)
    past_closes = [d['close'] for d in data[index-20:index+1]]
    rsi_14 = calculate_rsi(past_closes, 14)
    rsi_5 = calculate_rsi(past_closes, 5) # Faster RSI
    
    # 2. Volume Profile
    past_vols = [d['vol'] for d in data[index-20:index]]
    avg_vol = sum(past_vols) / len(past_vols) if past_vols else 1.0
    current_vol = data[index]['vol']
    vol_ratio = current_vol / avg_vol
    
    # 3. Candle Body Size (Reaction)
    c = data[index]
    body = abs(c['close'] - c['open'])
    range_ = c['high'] - c['low']
    body_pct = body / range_ if range_ > 0 else 0
    
    return {
        "direction": direction,
        "result": result,
        "rsi_14": rsi_14,
        "rsi_5": rsi_5,
        "vol_ratio": vol_ratio,
        "body_pct": body_pct,
        "hour": c['ts'].hour
    }

def analyze_comparison(winners, fakeouts):
    print("\n" + "=" * 60)
    print(f"COMPARATIVE ANALYSIS: {len(winners)} Winners vs {len(fakeouts)} Fakeouts")
    print("=" * 60)
    
    if not winners or not fakeouts:
        print("Insufficient data for comparison.")
        return

    # Helper to avg
    def get_avg(lst, key):
        return sum(x[key] for x in lst) / len(lst)
        
    print(f"\n1. RSI (14) Comparison")
    print(f"  Winners Avg: {get_avg(winners, 'rsi_14'):.2f}")
    print(f"  Fakeouts Avg: {get_avg(fakeouts, 'rsi_14'):.2f}")
    
    # Check extremes
    w_extreme = len([x for x in winners if x['rsi_14'] < 30 or x['rsi_14'] > 70]) / len(winners)
    f_extreme = len([x for x in fakeouts if x['rsi_14'] < 30 or x['rsi_14'] > 70]) / len(fakeouts)
    print(f"  Winners Extreme %: {w_extreme*100:.1f}%")
    print(f"  Fakeouts Extreme %: {f_extreme*100:.1f}%")

    print(f"\n2. Volume Ratio Comparison (Climax)")
    print(f"  Winners Avg: {get_avg(winners, 'vol_ratio'):.2f}x")
    print(f"  Fakeouts Avg: {get_avg(fakeouts, 'vol_ratio'):.2f}x")

    print(f"\n3. Candle Body % (Rejection Strength)")
    print(f"  Winners Avg: {get_avg(winners, 'body_pct')*100:.1f}% (Fuller body = stronger close)")
    print(f"  Fakeouts Avg: {get_avg(fakeouts, 'body_pct')*100:.1f}%")

    print("-" * 60)
    print("ROBOT FILTER RECOMMENDATION:")
    
    # Naive differentiator logic
    avg_diff_rsi = abs(get_avg(winners, 'rsi_14') - get_avg(fakeouts, 'rsi_14'))
    if avg_diff_rsi > 5:
        print(" >> RSI is a strong discriminator. Filter trades with RSI near 50.")
        
    avg_diff_vol = get_avg(winners, 'vol_ratio') - get_avg(fakeouts, 'vol_ratio')
    if avg_diff_vol > 0.5:
        print(" >> Higher Volume favors winning setups (Absorption).")
    elif avg_diff_vol < -0.5:
        print(" >> Lower Volume favors winning setups (No Panic).")
        
    print("=" * 60)

if __name__ == "__main__":
    print("DEBUG: Calling main()...", flush=True)
    main()
