#!/usr/bin/env python3
"""Quantum Forex Pure Backtest - Forex ONLY (No Metals).
Includes full Protection Logic (Wet Feet, Trailing Stops).
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
from tradebot_sci.market.models import Candle
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.icc_signals import (
    detect_continuation, 
    detect_liquidity_sweep,
    detect_indication,
    detect_correction,
)

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger("quantum_forex")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')
INITIAL_CAPITAL = 500.0

FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", 
    "USDCHF", "NZDUSD", "GBPJPY", "EURJPY", "AUDJPY"
]

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
    protection_price: Optional[float] = None
    pyramid_count: int = 0
    bars_held: int = 0

def load_candles(symbol: str) -> List[Candle]:
    filepath = os.path.join(DATA_DIR, f'{symbol}_15m.json')
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        data = json.load(f)
    candles = []
    for bar in data:
        ts = bar.get('timestamp', '')
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        candles.append(Candle(
            timestamp=dt, open=float(bar['open']), high=float(bar['high']),
            low=float(bar['low']), close=float(bar['close']),
            volume=float(bar.get('volume', 0)),
        ))
    return candles

def calculate_pnl(entry_price, exit_price, units, direction, symbol):
    price_diff = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
    if "JPY" in symbol:
        pips = price_diff * 100
        return pips * 0.065 * (units / 1000.0)
    else:
        pips = price_diff * 10000
        return pips * 0.10 * (units / 1000.0)

def calculate_position_size(capital, risk_pct, entry_price, stop_price, symbol):
    risk_dollars = capital * risk_pct
    dist = abs(entry_price - stop_price)
    if dist < 0.0001: return 0
    if "JPY" in symbol:
        pip_distance = dist * 100
        val_per_1000 = 0.065
    else:
        pip_distance = dist * 10000
        val_per_1000 = 0.10
    
    units = (risk_dollars / (pip_distance * val_per_1000)) * 1000
    return max(1, int(units))

def get_swing_invalidation(candles: List[Candle], direction: str) -> float:
    recent = candles[-10:]
    return min(c.low for c in recent) if direction == "long" else max(c.high for c in recent)

def run_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    settings = load_settings()
    profile = settings.get_active_profile()
    
    all_candles = {}
    for symbol in FOREX_SYMBOLS:
        candles = load_candles(symbol)
        if candles:
            start_date = datetime(2026, 1, 5, tzinfo=timezone.utc)
            end_date = datetime(2026, 1, 19, tzinfo=timezone.utc)
            filtered = [c for c in candles if start_date <= c.timestamp <= end_date]
            if filtered: all_candles[symbol] = filtered
    
    if not all_candles:
        print("No Forex data found.")
        return

    capital = INITIAL_CAPITAL
    positions: Dict[str, ForexPosition] = {}
    completed_trades: List[ForexTrade] = []
    all_times = sorted(set(c.timestamp for candles in all_candles.values() for c in candles))
    
    for current_time in all_times:
        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 30: continue
            
            current_bar = candles[bar_idx]
            lookback = candles[max(0, bar_idx-60):bar_idx+1]
            current_price = current_bar.close
            
            pos = positions.get(symbol)
            if pos:
                pos.bars_held += 1
                
                # Exit Logic 1: Structural Stop or Initial Stop
                if (pos.direction == "long" and current_bar.low <= pos.swing_invalidation) or \
                   (pos.direction == "short" and current_bar.high >= pos.swing_invalidation):
                    exit_p = pos.swing_invalidation
                    pnl = calculate_pnl(pos.avg_price, exit_p, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(symbol, pos.direction, pos.avg_price, exit_p, pos.size, pos.entry_time, current_time, pnl, "structure", pos.pyramid_count))
                    del positions[symbol]
                    continue
                
                # Exit Logic 2: Wet Feet (Average Price Protection)
                if pos.protection_price is not None:
                    if (pos.direction == "long" and current_bar.low <= pos.protection_price) or \
                       (pos.direction == "short" and current_bar.high >= pos.protection_price):
                        exit_p = pos.protection_price
                        pnl = calculate_pnl(pos.avg_price, exit_p, pos.size, pos.direction, symbol)
                        capital += pnl
                        completed_trades.append(ForexTrade(symbol, pos.direction, pos.avg_price, exit_p, pos.size, pos.entry_time, current_time, pnl, "wet_feet", pos.pyramid_count))
                        del positions[symbol]
                        continue

                # Pyramiding Logic
                if pos.pyramid_count < 6:
                    profit_pct = (current_price - pos.avg_price)/pos.avg_price if pos.direction=="long" else (pos.avg_price - current_price)/pos.avg_price
                    if profit_pct >= 0.0015:
                        risk_to_use = 0.30 if pos.pyramid_count == 0 else 0.10
                        # Structure based ref_stop for sizing
                        ref_stop = get_swing_invalidation(lookback, pos.direction)
                        if abs(current_price - ref_stop)/current_price < 0.0005: 
                            ref_stop = current_price * 0.9995 if pos.direction=="long" else current_price * 1.0005
                        
                        add_size = calculate_position_size(capital, risk_to_use, current_price, ref_stop, symbol)
                        if add_size > 0:
                            total_size = pos.size + add_size
                            pos.avg_price = (pos.avg_price * pos.size + current_price * add_size) / total_size
                            pos.size = total_size
                            pos.pyramid_count += 1
                            pos.protection_price = pos.avg_price # Wet Feet Move
                            logger.info(f"[PYRAMID] {symbol} #{pos.pyramid_count} @ {current_price:.5f}, new_avg={pos.avg_price:.5f}")

                # Trail Structure
                new_struct = get_swing_invalidation(lookback, pos.direction)
                if pos.direction == "long" and new_struct > pos.swing_invalidation: pos.swing_invalidation = new_struct
                elif pos.direction == "short" and new_struct < pos.swing_invalidation: pos.swing_invalidation = new_struct
                continue

            # Entry Logic
            trend_htf = infer_trend_from_swings(lookback[-60:], window=12)
            trend_ltf = infer_trend_from_swings(lookback[-30:], window=8)
            if not trend_htf or not trend_ltf: continue
            
            htf_dir, ltf_dir = str(trend_htf.direction), str(trend_ltf.direction)
            if ltf_dir not in ("long", "short"): continue
            if htf_dir != "neutral" and htf_dir != ltf_dir: continue # Align
            
            sweep = detect_liquidity_sweep(lookback[-20:], ltf_dir)
            indication = detect_indication(lookback[-20:])
            continuation = detect_continuation(lookback[-20:], ltf_dir, sweep, indication, None)
            
            if continuation or (sweep and indication):
                risk_pct = 0.01
                stop_p = get_swing_invalidation(lookback, ltf_dir)
                size = calculate_position_size(capital, risk_pct, current_price, stop_p, symbol)
                if size > 0:
                    positions[symbol] = ForexPosition(symbol, ltf_dir, current_price, current_price, size, current_time, stop_p, stop_p)

    print(f"\n--- JAN 2026 QUANTUM FOREX (PURE) REPORT ---")
    print(f"Initial: ${INITIAL_CAPITAL:.2f}")
    print(f"Final:   ${capital:.2f}")
    print(f"PnL:     ${capital - INITIAL_CAPITAL:.2f} ({(capital / INITIAL_CAPITAL - 1) * 100:.2f}%)")
    print(f"Trades:  {len(completed_trades)}")
    
    winning_trades = [t for t in completed_trades if t.pnl > 0]
    losing_trades = [t for t in completed_trades if t.pnl <= 0]
    print(f"Win Rate: {(len(winning_trades)/len(completed_trades)*100 if completed_trades else 0):.1f}%")
    
    if winning_trades: print(f"Avg Win:  ${sum(t.pnl for t in winning_trades)/len(winning_trades):.2f}")
    if losing_trades: print(f"Avg Loss: ${sum(t.pnl for t in losing_trades)/len(losing_trades):.2f}")

if __name__ == "__main__":
    run_backtest()
