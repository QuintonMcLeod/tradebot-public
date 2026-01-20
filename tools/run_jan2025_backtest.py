#!/usr/bin/env python3
"""Forex ICC Backtest (Jan 2025 Benchmark) - 1H INTERVAL.

Benchmarking "Wet Feet" Strategy on Jan 2025 Data (1H).
Goal: Verify if the strategy catches trends in a different market period.

- 1.2% initial risk
- 10% risk per pyramid add (when 0.2% profitable)
- Max 3 pyramid entries
- Exit on STRUCTURE INVALIDATION
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
logger = logging.getLogger("jan2025_benchmark")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'jan_2025')
INITIAL_CAPITAL = 100.0

# COMMODITIES ONLY (Benchmark Set)
FOREX_PAIRS = [
    "PAXGUSD", # Gold
    "XAGUSD",  # Silver
    "XPTUSD",  # Platinum
    "XPDUSD",  # Palladium
    "USOIL"    # Oil
]

# Backtest Settings
LONG_RISK_PCT = 0.01        # [HYBRID FLIP] Initial Probe: 1%
SHORT_RISK_PCT = 0.01       # [HYBRID FLIP] Initial Probe: 1%

MAX_PYRAMID_ENTRIES = 6     # 1 Load + 5 Scale
PROFIT_BUFFER_PCT = 0.0015  # Trigger "Load" at 0.15% profit
SECONDARY_BUFFER_PCT = 0.002  # Standard spacing

PYRAMID_RISK_LOAD = 0.30    # 30% Load
PYRAMID_RISK_SCALE = 0.10   # 10% Scale

# MINIMAL FILTERS
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
    protection_price: float = 0.0
    latest_add_price: float = 0.0

def load_candles(symbol: str) -> List[Candle]:
    # Using 1h data for Jan 2025
    filepath = os.path.join(DATA_DIR, f'{symbol}_1h.json')
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

    # Commodity Logic (Direct PnL)
    return price_diff * units

def calculate_position_size(capital, risk_pct, entry_price, stop_price, symbol):
    risk_amount = capital * risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0: return 0

    # Commodity Logic
    units = risk_amount / stop_distance
    return max(0.0001, units)

def get_swing_invalidation(candles: List[Candle], direction: str) -> float:
    if len(candles) < 10:
        return candles[-1].close
    
    recent = candles[-20:]
    if direction == "long":
        return min(c.low for c in recent)
    else:
        return max(c.high for c in recent)

def score_icc_entry(profile, trend_htf, trend_ltf, htf_align, sweep, continuation, indication, phase):
    # Simplified scoring
    score = 50.0 # Default pass
    threshold = 35.0
    return score, threshold

def run_jan2025_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    settings = load_settings()
    profile = settings.get_active_profile()
    
    print("=" * 80)
    print("JAN 2025 COMMODITY BACKTEST (1H) - WET FEET CHECK")
    print("=" * 80)

    all_candles = {}
    available_files = [f for f in os.listdir(DATA_DIR) if f.endswith("_1h.json")]
    all_available = [f.replace("_1h.json", "") for f in available_files]
    discovered_symbols = [s for s in FOREX_PAIRS if s in all_available]

    print(f"Using {len(discovered_symbols)} symbols: {discovered_symbols}")
    
    for symbol in discovered_symbols:
        candles = load_candles(symbol)
        if candles:
            all_candles[symbol] = candles
            logger.info(f"Loaded {len(candles)} candles for {symbol}")
    
    if not all_candles:
        print("No data!")
        return 1
    
    capital = INITIAL_CAPITAL
    positions: Dict[str, ForexPosition] = {}
    completed_trades: List[ForexTrade] = []
    
    all_times = sorted(set(c.timestamp for candles in all_candles.values() for c in candles))
    print(f"\nBacktest: {all_times[0]} to {all_times[-1]}")
    print(f"Bars: {len(all_times)}")
    
    total_pyramids = 0
    
    for i, current_time in enumerate(all_times):
        if i < 100: continue
        
        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 100: continue
            
            current_bar = candles[bar_idx]
            lookback = candles[max(0, bar_idx-200):bar_idx+1]
            current_price = current_bar.close
            
            # Trend Analysis (1H Data)
            htf_candles = lookback[-60:]
            ltf_candles = lookback[-30:]
            trend_htf = infer_trend_from_swings(htf_candles, window=12, swing_lookback=2, min_swings=2, strength_floor=0.25)
            trend_ltf = infer_trend_from_swings(ltf_candles, window=8, swing_lookback=2, min_swings=2, strength_floor=0.25)
            
            pos = positions.get(symbol)
            
            if pos:
                current_htf_dir = str(trend_htf.direction) if trend_htf else "neutral"

                # 1. HARD STOP (Exact Breakeven Logic)
                if (pos.direction == "long" and current_bar.low <= pos.stop_price) or \
                   (pos.direction == "short" and current_bar.high >= pos.stop_price):
                    pnl = calculate_pnl(pos.avg_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                        exit_price=pos.stop_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="stop",
                        pyramid_count=pos.pyramid_count, score=pos.score
                    ))
                    del positions[symbol]
                    continue

                # 2. PYRAMID (Wet Feet)
                if pos.pyramid_count < MAX_PYRAMID_ENTRIES:
                    profit_pct = (current_price - pos.avg_price)/pos.avg_price if pos.direction == "long" else (pos.avg_price - current_price)/pos.avg_price
                    req_buffer = PROFIT_BUFFER_PCT if pos.pyramid_count == 0 else SECONDARY_BUFFER_PCT
                    
                    if profit_pct >= req_buffer:
                        # Profit Calculation for Equity Sizing
                        pnl_val = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                        current_equity = capital + max(0, pnl_val)
                        risk_to_use = PYRAMID_RISK_LOAD if pos.pyramid_count == 0 else PYRAMID_RISK_SCALE
                        
                        # Structure Sizing (10 bars)
                        lookback_bars = 10
                        if pos.direction == "long":
                            recent_lows = [c.low for c in ltf_candles[-lookback_bars:]]
                            ref_stop = min(recent_lows) if recent_lows else current_price * 0.999
                            if ref_stop >= current_price: ref_stop = current_price * 0.999
                        else:
                            recent_highs = [c.high for c in ltf_candles[-lookback_bars:]]
                            ref_stop = max(recent_highs) if recent_highs else current_price * 1.001
                            if ref_stop <= current_price: ref_stop = current_price * 1.001
                            
                        # Min dist check
                        dist_pct = abs(current_price - ref_stop) / current_price
                        if dist_pct < 0.0005:
                            if pos.direction == "long": ref_stop = current_price * 0.9995
                            else: ref_stop = current_price * 1.0005

                        add_size = calculate_position_size(current_equity, risk_to_use, current_price, ref_stop, symbol)
                        total_size = pos.size + add_size
                        new_avg = (pos.avg_price * pos.size + current_price * add_size) / total_size
                        
                        pos.avg_price = new_avg
                        pos.size = total_size
                        
                        # WET FEET PROTECT: Move Stop to Avg Price
                        pos.protection_price = new_avg
                        pos.stop_price = pos.protection_price
                        
                        pos.pyramid_count += 1
                        total_pyramids += 1
                        logger.info(f"[PYRAMID] {symbol} add #{pos.pyramid_count} @ {current_price:.5f}, new_avg={new_avg:.5f}")

                # 3. HTF FLIP EXIT
                current_pnl = (current_price - pos.avg_price)/pos.avg_price if pos.direction == "long" else (pos.avg_price - current_price)/pos.avg_price
                if current_pnl < 0.001: 
                    if (pos.direction == "long" and current_htf_dir == "short") or (pos.direction == "short" and current_htf_dir == "long"):
                        pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                        capital += pnl
                        completed_trades.append(ForexTrade(
                            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                            exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                            exit_time=current_time, pnl=pnl, exit_reason="htf_flip",
                            pyramid_count=pos.pyramid_count
                        ))
                        del positions[symbol]
                        continue

                # 4. STRUCTURE EXIT
                if (pos.direction == "long" and current_bar.close < pos.swing_invalidation) or \
                   (pos.direction == "short" and current_bar.close > pos.swing_invalidation):
                    pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                        exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="structure",
                        pyramid_count=pos.pyramid_count
                    ))
                    del positions[symbol]
                    continue

                # Trail Structure
                raw_struct = get_swing_invalidation(ltf_candles, pos.direction)
                # Volatility buffer (1.0 ATR for commodities)
                recent_volt = ltf_candles[-14:]
                atr_val = sum(c.high - c.low for c in recent_volt) / len(recent_volt) if recent_volt else 0.0
                buffer_mult = 1.0 
                
                if pos.direction == "long":
                     new_invalidation = raw_struct - (atr_val * buffer_mult)
                     if new_invalidation > pos.swing_invalidation: pos.swing_invalidation = new_invalidation
                else:
                     new_invalidation = raw_struct + (atr_val * buffer_mult)
                     if new_invalidation < pos.swing_invalidation: pos.swing_invalidation = new_invalidation
                     
                pos.last_htf_dir = current_htf_dir
                continue

            # NEW ENTRY
            if not trend_htf or not trend_ltf: continue
            htf_dir = str(trend_htf.direction)
            ltf_dir = str(trend_ltf.direction)
            
            if ltf_dir not in ("long", "short"): continue
            
            # Minimal logic
            if htf_dir != "neutral" and htf_dir != ltf_dir: continue # Alignment check
            
            indication = detect_indication(ltf_candles, swing_lookback=2)
            correction = detect_correction(ltf_candles, indication, swing_lookback=2)
            continuation = detect_continuation(
                ltf_candles, ltf_dir, None, indication, correction,
                require_sweep=False, require_indication=False, require_correction=False,
                swing_lookback=2, confirmation_bars=2
            )
            
            if not continuation: continue
            
            entry_price = current_price
            atr = sum(abs(c.high - c.low) for c in ltf_candles[-14:]) / 14 if ltf_candles else entry_price*0.01
            
            stop_dist = atr * 1.5
            if ltf_dir == "long": stop_price = entry_price - stop_dist
            else: stop_price = entry_price + stop_dist
            
            if ltf_dir == "long": risk_pct = LONG_RISK_PCT
            else: risk_pct = SHORT_RISK_PCT
            
            initial_size = calculate_position_size(capital, risk_pct, entry_price, stop_price, symbol)
            
            # Initial Structure Invalidation
            raw_struct = get_swing_invalidation(ltf_candles, ltf_dir)
            if ltf_dir == "long": swing_invalidation = raw_struct - atr
            else: swing_invalidation = raw_struct + atr
            
            positions[symbol] = ForexPosition(
                symbol=symbol, direction=ltf_dir, entry_price=entry_price,
                avg_price=entry_price, size=initial_size, entry_time=current_time,
                stop_price=stop_price, swing_invalidation=swing_invalidation,
                pyramid_count=0, last_htf_dir=htf_dir
            )
            logger.info(f"[ENTRY] {symbol} {ltf_dir} @ {entry_price:.5f}")

    # Close positions
    for symbol, pos in list(positions.items()):
        current_bar = all_candles[symbol][-1]
        pnl = calculate_pnl(pos.avg_price, current_bar.close, pos.size, pos.direction, symbol)
        capital += pnl
        completed_trades.append(ForexTrade(
            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
            exit_price=current_bar.close, size=pos.size, entry_time=pos.entry_time,
            exit_time=current_bar.timestamp, pnl=pnl, exit_reason="eod",
            pyramid_count=pos.pyramid_count
        ))

    print("\n" + "=" * 80)
    print("RESULTS - JAN 2025 BENCHMARK (1H)")
    print("=" * 80)
    print(f"Total Pyramid Adds: {total_pyramids}")
    print(f"Trades: {len(completed_trades)}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Total PnL: ${capital - INITIAL_CAPITAL:.2f}")
    print(f"Return: {(capital / INITIAL_CAPITAL - 1) * 100:.2f}%")
    
    if completed_trades:
        pyramid_trades = [t for t in completed_trades if t.pyramid_count > 0]
        pyramid_losers = [t.pnl for t in pyramid_trades if t.pnl < 0]
        print(f"Pyramid Failed Trades (Trap): {len(pyramid_losers)} trades, ${sum(pyramid_losers):.2f}")

    return 0

if __name__ == "__main__":
    run_jan2025_backtest()
