#!/usr/bin/env python3
print("DEBUG: Script starting...", flush=True)

"""
Fakeout Hunter: Analyze Nov 2024 (Election Month)
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
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
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def main():
    print("=" * 60, flush=True)
    print("🤖 FAKEOUT HUNTER: NOV 2024 (ELECTION MONTH)", flush=True)
    print("=" * 60, flush=True)

    settings = load_settings()
    settings.app.profile_name = "coinbase_futures" 
    provider = CCXTHistoricalDataProvider(settings, exchange_id="coinbase")
    
    start_date = datetime(2024, 11, 1, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2024, 11, 30, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
    symbol = "BTC/USD"
    timeframe = "1m"

    print(f"Scanning {symbol} ({timeframe}) from {start_date.date()} to {end_date.date()}...")
    candles = provider.fetch_historical_candles(symbol, timeframe, start_date, end_date)
    if not candles:
        print("No data found!")
        return

    data = [{
        'ts': c.timestamp, 
        'open': c.open, 'high': c.high, 'low': c.low, 'close': c.close, 'vol': c.volume
    } for c in candles]
    
    look_forward = 60 
    min_move_pct = 0.01 
    max_drawdown_pct = 0.003 
    
    winning_setups = []
    fakeout_setups = []
    
    print(f"Analyzing {len(data)} candles...", flush=True)
    last_signal_idx = -100
    
    for i in range(50, len(data) - look_forward): 
        if i < last_signal_idx + 15: 
            continue
        
        # Look for Sweeps (High/Low of last 20)
        lookback = 20
        recent_window = data[i-lookback:i]
        recent_low = min(d['low'] for d in recent_window)
        recent_high = max(d['high'] for d in recent_window)
        current_bar = data[i]
        
        is_sweep_long = current_bar['low'] <= recent_low 
        is_sweep_short = current_bar['high'] >= recent_high

        if is_sweep_long:
            future_window = data[i+1:i+1+look_forward]
            max_high = max(d['high'] for d in future_window)
            min_low = min(d['low'] for d in future_window)
            up_move = (max_high - current_bar['close']) / current_bar['close']
            drawdown = (current_bar['close'] - min_low) / current_bar['close']
            
            if up_move >= min_move_pct and drawdown <= max_drawdown_pct:
                winning_setups.append(analyze_setup(data, i, "long", "WIN"))
                last_signal_idx = i
            elif drawdown > max_drawdown_pct:
                fakeout_setups.append(analyze_setup(data, i, "long", "FAKEOUT"))
                last_signal_idx = i

        elif is_sweep_short:
            future_window = data[i+1:i+1+look_forward]
            min_future_low = min(d['low'] for d in future_window)
            max_future_high = max(d['high'] for d in future_window)
            down_move = (current_bar['close'] - min_future_low) / current_bar['close']
            short_drawdown = (max_future_high - current_bar['close']) / current_bar['close']
            
            if down_move >= min_move_pct and short_drawdown <= max_drawdown_pct:
                winning_setups.append(analyze_setup(data, i, "short", "WIN"))
                last_signal_idx = i
            elif short_drawdown > max_drawdown_pct:
                fakeout_setups.append(analyze_setup(data, i, "short", "FAKEOUT"))
                last_signal_idx = i

    analyze_comparison(winning_setups, fakeout_setups)

def analyze_setup(data, index, direction, result):
    past_closes = [d['close'] for d in data[index-20:index+1]]
    rsi_14 = calculate_rsi(past_closes, 14)
    past_vols = [d['vol'] for d in data[index-20:index]]
    avg_vol = sum(past_vols) / len(past_vols) if past_vols else 1.0
    current_vol = data[index]['vol']
    vol_ratio = current_vol / avg_vol
    
    return {
        "direction": direction,
        "result": result,
        "rsi_14": rsi_14,
        "vol_ratio": vol_ratio,
    }

def analyze_comparison(winners, fakeouts):
    print("\n" + "=" * 60)
    print(f"COMPARATIVE ANALYSIS: {len(winners)} Winners vs {len(fakeouts)} Fakeouts")
    print("=" * 60)
    
    if not winners or not fakeouts:
        print("Insufficient data.")
        return

    def get_avg(lst, key): return sum(x[key] for x in lst) / len(lst)
        
    print(f"\n1. RSI (14)")
    print(f"  Winners: {get_avg(winners, 'rsi_14'):.2f}")
    print(f"  Fakeouts: {get_avg(fakeouts, 'rsi_14'):.2f}")

    print(f"\n2. Volume Ratio")
    print(f"  Winners: {get_avg(winners, 'vol_ratio'):.2f}x")
    print(f"  Fakeouts: {get_avg(fakeouts, 'vol_ratio'):.2f}x")

if __name__ == "__main__":
    main()
