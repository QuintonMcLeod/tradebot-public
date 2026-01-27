#!/usr/bin/env python3
"""
CHALLENGE SCRIPT: BASED ON run_backtest_original.py
Modified to read _5m.json data to match checking availability.
"""

import sys
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.market.models import Candle, TrendState
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.icc_signals import (
    detect_continuation, 
    detect_liquidity_sweep,
    detect_indication,
    detect_correction,
    detect_no_trade_zone,
)

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger("forex_challenge")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')
INITIAL_CAPITAL = 100.0
# CONFIG FROM ORIGINAL
LONG_RISK_PCT = 0.01        
SHORT_RISK_PCT = 0.01       
MAX_PYRAMID_ENTRIES = 6     
PROFIT_BUFFER_PCT = 0.0015  
SECONDARY_BUFFER_PCT = 0.002 
PYRAMID_RISK_LOAD = 0.30    
PYRAMID_RISK_SCALE = 0.10   
MIN_HTF_STRENGTH = 0.25   
REQUIRE_SWEEP = False     
MIN_MOMENTUM_PIPS = 0     

@dataclass
class ForexTrade:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str
    pyramid_count: int = 0
    score: float = 0.0

@dataclass  
class ForexPosition:
    symbol: str
    direction: str
    entry_price: float
    avg_price: float
    size: float
    entry_time: datetime
    stop_price: float
    swing_invalidation: float  
    initial_entry_price: float = 0.0  
    pyramid_count: int = 0
    score: float = 0.0
    last_htf_dir: str = "neutral"

def load_candles(symbol: str) -> List[Candle]:
    # MODIFIED: Load 5m data
    filepath = os.path.join(DATA_DIR, f'{symbol}_5m.json')
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        data = json.load(f)
    candles = []
    for bar in data:
        ts = bar.get('timestamp', '')
        if 'T' in ts:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        candles.append(Candle(
            timestamp=dt,
            open=float(bar['open']),
            high=float(bar['high']),
            low=float(bar['low']),
            close=float(bar['close']),
            volume=float(bar.get('volume', 0)),
        ))
    return candles

def calculate_pnl(entry_price, exit_price, units, direction, symbol):
    if direction == "short":
        price_diff = entry_price - exit_price
    else:
        price_diff = exit_price - entry_price

    if "JPY" in symbol:
        pips = price_diff * 100
        pip_value = 0.065 
        micro_lots = units / 1000.0
        return pips * pip_value * micro_lots
    else:
        pips = price_diff * 10000
        pip_value = 0.10 
        micro_lots = units / 1000.0
        return pips * pip_value * micro_lots

def calculate_position_size(capital, risk_pct, entry_price, stop_price, symbol):
    risk_amount = capital * risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0: return 0
    
    if symbol.startswith("USD") and "JPY" in symbol:
        stop_distance = stop_distance / entry_price
    
    units = risk_amount / stop_distance
    return max(1, int(units))

def get_swing_invalidation(candles: List[Candle], direction: str) -> float:
    if len(candles) < 10:
        return candles[-1].close
    recent = candles[-20:]
    if direction == "long":
        return min(c.low for c in recent)
    else:
        return max(c.high for c in recent)

def run_forex_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    
    available_files = [f for f in os.listdir(DATA_DIR) if f.endswith("_5m.json")]
    discovered_symbols = [f.replace("_5m.json", "") for f in available_files]
    
    print(f"CHALLENGE: Running on {len(discovered_symbols)} pairs: {discovered_symbols}")
    
    all_candles = {}
    for symbol in discovered_symbols:
        candles = load_candles(symbol)
        if candles:
            all_candles[symbol] = candles
    
    if not all_candles:
        print("No data!")
        return 1
    
    capital = INITIAL_CAPITAL
    positions: Dict[str, ForexPosition] = {}
    completed_trades: List[ForexTrade] = []
    
    all_times = sorted(set(c.timestamp for candles in all_candles.values() for c in candles))
    
    for i, current_time in enumerate(all_times):
        if i < 100: continue
        
        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 100: continue
            
            current_bar = candles[bar_idx]
            lookback = candles[max(0, bar_idx-200):bar_idx+1]
            current_price = current_bar.close
            
            # --- HTF LOGIC (User's Claim) ---
            htf_candles = lookback[-60:] # 5h window approx
            ltf_candles = lookback[-30:]
            trend_htf = infer_trend_from_swings(htf_candles, window=12, swing_lookback=2, min_swings=2, strength_floor=0.25)
            trend_ltf = infer_trend_from_swings(ltf_candles, window=8, swing_lookback=2, min_swings=2, strength_floor=0.25)
            
            htf_dir = str(trend_htf.direction)
            ltf_dir = str(trend_ltf.direction)
            
            pos = positions.get(symbol)
            
            if pos:
                # 1. STOP CHECK
                if (pos.direction == "long" and current_bar.low <= pos.stop_price) or \
                   (pos.direction == "short" and current_bar.high >= pos.stop_price):
                    pnl = calculate_pnl(pos.avg_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(symbol, pos.direction, pos.avg_price, pos.stop_price, pos.size, pos.entry_time, current_time, pnl, "stop", pos.pyramid_count))
                    del positions[symbol]
                    continue
                
                # 2. EXIT on HTF FLIP (User Logic)
                if pos.direction == "long" and htf_dir == "short":
                     # Close
                    pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(symbol, pos.direction, pos.avg_price, current_price, pos.size, pos.entry_time, current_time, pnl, "htf_flip", pos.pyramid_count))
                    del positions[symbol]
                    continue
                if pos.direction == "short" and htf_dir == "long":
                    pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(symbol, pos.direction, pos.avg_price, current_price, pos.size, pos.entry_time, current_time, pnl, "htf_flip", pos.pyramid_count))
                    del positions[symbol]
                    continue

                continue
            
            # 3. ENTRY LOGIC
            # MUST ALIGN WITH HTF
            htf_align = ltf_dir != "neutral" and (htf_dir == "neutral" or htf_dir == ltf_dir)
            
            if htf_align and ltf_dir in ["long", "short"]:
                # Basic Entry
                atr = sum(abs(c.high - c.low) for c in ltf_candles[-14:]) / 14
                if ltf_dir == "long":
                     stop_price = current_price - (atr * 1.5)
                     risk_pct = 0.01 # 1% Prob
                else:
                     stop_price = current_price + (atr * 1.5)
                     risk_pct = 0.01
                
                size = calculate_position_size(capital, risk_pct, current_price, stop_price, symbol)
                if size > 0:
                    positions[symbol] = ForexPosition(symbol, ltf_dir, current_price, current_price, size, current_time, stop_price, 0)

    print(f"CHALLENGE RESULT: Final Capital ${capital:.2f}")
    if capital > 1000:
        print(">>> USER WAS RIGHT: THE SCRIPT WINS <<<")
    else:
        print(">>> SCRIPT FAILED <<<")

if __name__ == "__main__":
    run_forex_backtest()
