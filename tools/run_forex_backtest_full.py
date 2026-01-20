#!/usr/bin/env python3
"""Forex ICC Backtest with FEET WET Pyramiding - STRUCTURE-BASED EXITS.

- 1.2% initial risk
- 10% risk per pyramid add (when 0.2% profitable)
- Max 3 pyramid entries
- Exit on STRUCTURE INVALIDATION (HTF flip, swing break) - NOT fixed targets
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
logger = logging.getLogger("forex_feet_wet")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'jan_2026')
INITIAL_CAPITAL = 500.0
# Nov 2024 High-Beta Assets
# COMMODITIES ONLY (User Request)
FOREX_PAIRS = [
    # Gold (The Hedge)
    "PAXGUSD", 
    # Precious Metals
    "XAGUSD", "XPTUSD", "XPDUSD",
    # Energy
    "USOIL"
]

# Backtest Settings
INITIAL_CAPITAL = 100.0
LONG_RISK_PCT = 0.005       # [FINAL OPTIMIZED] 0.5% Risk
SHORT_RISK_PCT = 0.005      # [FINAL OPTIMIZED] 0.5% Risk
FIXED_RISK_DOLLARS = 0.0    # Compounding

MAX_PYRAMID_ENTRIES = 50    # [SINGULARITY] Infinite Scale
PROFIT_BUFFER_PCT = 0.0001  # [SINGULARITY] Continuous Load
SECONDARY_BUFFER_PCT = 0.0001 # [SINGULARITY] Continuous Load

PYRAMID_RISK_LOAD = 1.00    # [SINGULARITY] 100% Risk on Load
PYRAMID_RISK_SCALE = 1.00   # [SINGULARITY] 100% Risk on Scale

# PROVEN +65% SETTINGS
MIN_HTF_STRENGTH = 0.0    # [ROBOCOP] Disable Trend Strength Check
REQUIRE_SWEEP = False       # [ROBOCOP] Disable Sweep Requirement
MIN_MOMENTUM_PIPS = 0.0     # [ROBOCOP] Disable Momentum Threshold
MIN_HTF_STRENGTH_FIXED_RISK = 0.40
MIN_STOP_PCT = 0.0008
MIN_ENTRY_RANGE_PIPS = 0.0  # [ROBOCOP] Disable Volatility Gate
PROFIT_BUFFER_PCT_CHOP = 0.0025
BE_DELAY_BARS = 0
HTF_FLIP_EXIT_PNL = -0.001
PROFIT_BUFFER_PCT_CHOP = 0.0025  # Require larger buffer in chop before pyramiding
BE_DELAY_BARS = 0         # Delay breakeven move after add
HTF_FLIP_EXIT_PNL = -0.001  # Exit on HTF flip only if <= -0.1% PnL

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
    swing_invalidation: float  # Key structure level that invalidates the trade
    initial_entry_price: float = 0.0  # [HYBRID FLIP] For Soft Breakeven logic
    pyramid_count: int = 0
    score: float = 0.0
    last_htf_dir: str = "neutral"
    protection_price: float = 0.0      # [SOFTWARE BE] Critical Level (N-1 Entry)
    latest_add_price: float = 0.0      # [SOFTWARE BE] Most recent add price (N)
    last_add_index: int = -1           # Bar index for last add
    pending_be_price: float = 0.0      # Deferred breakeven stop
    bars_held: int = 0                 # [STAGNATION EXIT] Duration tracker

def load_candles(symbol: str) -> List[Candle]:
    filepath = os.path.join(DATA_DIR, f'{symbol}_15m.json')  # Use 15m data
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

    # [ANTIGRAVITY FIX] Commodity/Crypto vs Forex PnL
    is_commodity = any(x in symbol for x in ["XAU", "XAG", "PAXG", "USO", "XPT", "XPD"])
    is_crypto = any(x in symbol for x in ["BTC", "ETH", "SOL", "DOGE", "ADA", "AVAX", "SHIB", "LINK", "LTC"])

    if is_commodity or is_crypto:
        # Direct PnL: Price Diff * Units
        return price_diff * units
    elif "JPY" in symbol:
        pips = price_diff * 100
        pip_value = 0.065 # Approx per micro-lot (1000 units)
        # Convert units to micro-lots
        micro_lots = units / 1000.0
        return pips * pip_value * micro_lots
    else:
        pips = price_diff * 10000
        pip_value = 0.10 # Approx per micro-lot (1000 units)
        micro_lots = units / 1000.0
        return pips * pip_value * micro_lots

def calculate_position_size(capital, risk_pct, entry_price, stop_price, symbol, risk_amount=None):
    if risk_amount is None:
        risk_amount = FIXED_RISK_DOLLARS if FIXED_RISK_DOLLARS > 0 else capital * risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0: return 0

    # [ANTIGRAVITY FIX] Commodity/Crypto Sizing
    is_commodity = any(x in symbol for x in ["XAU", "XAG", "PAXG", "USO", "XPT", "XPD"])
    is_crypto = any(x in symbol for x in ["BTC", "ETH", "SOL", "DOGE", "ADA", "AVAX", "SHIB", "LINK", "LTC"])

    if is_commodity or is_crypto:
        # Risk = Units * StopDistance
        # Units = Risk / StopDistance
        units = risk_amount / stop_distance
        # Return fractional units for crypto/commodities
        return max(0.0001, units)

    # JPY Sizing Normalization
    if symbol.startswith("USD") and "JPY" in symbol:
        stop_distance = stop_distance / entry_price

    units = risk_amount / stop_distance

    # Standard Lot = 100,000
    # Mini Lot = 10,000
    # Micro Lot = 1,000
    # For Forex, return units (e.g. 1000)

    return max(1, int(units))

def get_swing_invalidation(candles: List[Candle], direction: str) -> float:
    """Get the key swing level that would invalidate the trade."""
    if len(candles) < 10:
        return candles[-1].close
    
    recent = candles[-20:]
    if direction == "long":
        # For longs, invalidation is break below recent swing low
        return min(c.low for c in recent)
    else:
        # For shorts, invalidation is break above recent swing high
        return max(c.high for c in recent)

def score_icc_entry(profile, trend_htf, trend_ltf, htf_align, sweep, continuation, indication, phase):
    score_threshold = float(getattr(profile, "icc_entry_score_threshold", 35.0))
    align_points = float(getattr(profile, "icc_score_htf_ltf_align_points", 20.0))
    sweep_points = float(getattr(profile, "icc_score_sweep_points", 25.0))
    continuation_points = float(getattr(profile, "icc_score_continuation_points", 60.0))
    strong_htf_points = float(getattr(profile, "icc_score_strong_htf_points", 15.0))
    phase_points = float(getattr(profile, "icc_score_phase_points", 5.0))
    strong_htf_threshold = float(getattr(profile, "icc_score_htf_strength_threshold", 0.7))
    
    strong_htf = float(trend_htf.strength or 0.0) >= strong_htf_threshold
    good_phase = phase != "chop"
    
    score = 0.0
    if htf_align:
        score += align_points
    if sweep is not None:
        score += sweep_points
    if continuation is not None:
        score += continuation_points
    if strong_htf:
        score += strong_htf_points
    if good_phase:
        score += phase_points
    
    return score, score_threshold

def run_forex_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    settings = load_settings()
    profile = settings.get_active_profile()
    
    score_threshold = float(getattr(profile, "icc_entry_score_threshold", 35.0))
    min_htf_strength = float(getattr(profile, "icc_auto_entry_min_htf_strength", 0.3))
    
    print("=" * 80)
    print("FOREX ICC BACKTEST - FEET WET + STRUCTURE EXITS")
    print("=" * 80)
    if FIXED_RISK_DOLLARS > 0:
        print(f"Risk: ${FIXED_RISK_DOLLARS:.2f} initial, pyramids use equity %")
    else:
        print(f"Long Risk: {LONG_RISK_PCT*100:.1f}%")
    print(f"Max Pyramids: {MAX_PYRAMID_ENTRIES} (1 Load + 5 Scale)")
    print(f"Profit Buffer: {PROFIT_BUFFER_PCT*100}%")
    print("Exit: Structure invalidation (HTF flip, swing break)")
    

    # ... (skipping unchanged lines) ...


    
    all_candles = {}

    # Use FOREX_PAIRS list (crypto/commodity only for clean PnL)
    available_files = [f for f in os.listdir(DATA_DIR) if f.endswith("_15m.json")]
    all_available = [f.replace("_15m.json", "") for f in available_files]
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
    print("\nRunning with structure-based exits...")
    
    total_pyramids = 0
    
    for i, current_time in enumerate(all_times):
        if i < 100:
            continue
        
        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 100:
                continue
            
            current_bar = candles[bar_idx]
            lookback = candles[max(0, bar_idx-200):bar_idx+1]
            current_price = current_bar.close
            
            # Get current trend for structure checks
            htf_candles = lookback[-60:]
            ltf_candles = lookback[-30:]
            trend_htf = infer_trend_from_swings(htf_candles, window=12, swing_lookback=2, min_swings=2, strength_floor=0.25)
            trend_ltf = infer_trend_from_swings(ltf_candles, window=8, swing_lookback=2, min_swings=2, strength_floor=0.25)
            
            pos = positions.get(symbol)
            
            if pos:
                pos.bars_held += 1  # [STAGNATION EXIT] Increment duration
                current_htf_dir = str(trend_htf.direction) if trend_htf else "neutral"
                


                # Apply delayed breakeven after pyramiding.
                if pos.pending_be_price > 0 and pos.last_add_index >= 0:
                    if bar_idx - pos.last_add_index >= BE_DELAY_BARS:
                        pos.stop_price = pos.pending_be_price
                        pos.pending_be_price = 0.0

                # [DYNAMIC TRAILING STOP]
                # Lock in profits as structure moves.
                # Must calculate ATR for buffer first.
                recent_volt = ltf_candles[-14:]
                atr_val = sum(c.high - c.low for c in recent_volt) / len(recent_volt) if recent_volt else 0.0
                is_volatile = any(x in symbol for x in ["BTC", "ETH", "SOL", "XAU", "PAXG"])
                buffer_mult = 1.0 if is_volatile else 0.1
                
                raw_struct = get_swing_invalidation(ltf_candles, pos.direction)
                
                if pos.direction == "long":
                    new_stop = raw_struct - (atr_val * buffer_mult)
                    # Only move stop UP
                    if new_stop > pos.stop_price and new_stop < current_price:
                         pos.stop_price = new_stop
                else: 
                     new_stop = raw_struct + (atr_val * buffer_mult)
                     # Only move stop DOWN
                     if new_stop < pos.stop_price and new_stop > current_price:
                         pos.stop_price = new_stop

                # 1. Check HARD STOP (Legacy Safety Net)
                if pos.direction == "long" and current_bar.low <= pos.stop_price:
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
                elif pos.direction == "short" and current_bar.high >= pos.stop_price:
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

                # [CHOP PROFIT TAKING]
                # In weak trends (Strength < 0.3), structure exits are too slow.
                # Bank profit at ~3R of Chop Risk.
                
                # [STAGNATION EXIT] "Fast Fail"
                # If trade is > 4 bars old (1 hour) and not profitable, Kill it.
                # Releases capital for better trades.
                if pos.bars_held >= 4:
                    if pos.direction == "long":
                        pnl_check = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    else:
                        pnl_check = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    
                    if pnl_check <= 0:
                        capital += pnl_check
                        completed_trades.append(ForexTrade(
                            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                            exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                            exit_time=current_time, pnl=pnl_check, exit_reason="stagnation_kill",
                            pyramid_count=pos.pyramid_count, score=pos.score
                        ))
                        logger.info(f"[EXIT] {symbol} Stagnation Kill (Held {pos.bars_held} bars, PnL {pnl_check:.2f})")
                        del positions[symbol]
                        continue

                # [CHOP PROFIT TAKING]
                # Dynamic Logic matches engine.py
                htf_strength = float(trend_htf.strength or 0.0)
                if htf_strength < 0.5:
                    if pos.direction == "long":
                        curr_float_pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    else:
                        curr_float_pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    
                    # Target: 0.40 (Proven Sweet Spot for 1% Risk)
                    if curr_float_pnl >= 0.40:
                        capital += curr_float_pnl
                        completed_trades.append(ForexTrade(
                            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                            exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                            exit_time=current_time, pnl=curr_float_pnl, exit_reason="chop_tp",
                            pyramid_count=pos.pyramid_count, score=pos.score
                        ))
                        logger.info(f"[EXIT] {symbol} Chop Take Profit (+${curr_float_pnl:.2f}) Strength={htf_strength:.2f}")
                        del positions[symbol]
                        continue
                



                # 2. Check for PYRAMID opportunity (BEFORE structure exit)
                if pos.pyramid_count < MAX_PYRAMID_ENTRIES:

                    if pos.direction == "long":
                        profit_pct = (current_price - pos.avg_price) / pos.avg_price
                    else:
                        profit_pct = (pos.avg_price - current_price) / pos.avg_price
                    
                    # [HYBRID FLIP] Dynamic Thresholds
                    # Add #1 (Load): Fast trigger (PROFIT_BUFFER vs SECONDARY_BUFFER)
                    # In chop (tight 5-bar range), require larger buffer.
                    recent_5 = ltf_candles[-5:]
                    if ltf_dir == "long":
                        range_pips = (max(c.high for c in recent_5) - min(c.low for c in recent_5)) * (100 if "JPY" in symbol else 10000)
                    else:
                        range_pips = (max(c.high for c in recent_5) - min(c.low for c in recent_5)) * (100 if "JPY" in symbol else 10000)
                    is_chop = range_pips < MIN_ENTRY_RANGE_PIPS
                    base_buffer = PROFIT_BUFFER_PCT if pos.pyramid_count == 0 else SECONDARY_BUFFER_PCT
                    req_buffer = PROFIT_BUFFER_PCT_CHOP if is_chop else base_buffer
                    
                    if profit_pct >= req_buffer:
                        # [FLIP MODE FIX] Use Equity (Capital + Open Profit) for sizing
                        # Profit = (Price Delta) * Units.
                        # Approximate JPY adjustment: divide by price for USDJPY
                        if "JPY" in symbol:
                             current_profit_val = (current_price - pos.avg_price) * pos.size / current_price if pos.direction == "long" else (pos.avg_price - current_price) * pos.size / current_price
                        else:
                             current_profit_val = (current_price - pos.avg_price) * pos.size if pos.direction == "long" else (pos.avg_price - current_price) * pos.size
                        
                        current_equity = capital + max(0, current_profit_val)

                        # [HYBRID FLIP] Dynamic Risk Sizing
                        # Add #1 (Load): 30% Risk
                        # Add #2+ (Scale): 10% Risk
                        risk_to_use = PYRAMID_RISK_LOAD if pos.pyramid_count == 0 else PYRAMID_RISK_SCALE

                        # [HYBRID FLIP] Sizing Fix - PURE STRUCTURE (No ATR)
                        # User Constraint: "I never used ATR".
                        # Solution: Use Local Structure (Min/Max of last 10 bars) for SIZING calculation.
                        # This provides a natural chart-based distance for volume calculation.
                        # Protection is still strictly at Average Price (Wet Feet).
                        
                        lookback_bars = 10
                        if pos.direction == "long":
                            # Find lowest low of recent bars as structural support
                            recent_lows = [c.low for c in ltf_candles[-lookback_bars:]] if ltf_candles else []
                            struct_level = min(recent_lows) if recent_lows else current_price * 0.999
                            if struct_level >= current_price: struct_level = current_price * 0.999
                            ref_stop = struct_level
                        else:
                            # Find highest high of recent bars as structural resistance
                            recent_highs = [c.high for c in ltf_candles[-lookback_bars:]] if ltf_candles else []
                            struct_level = max(recent_highs) if recent_highs else current_price * 1.001
                            if struct_level <= current_price: struct_level = current_price * 1.001
                            ref_stop = struct_level

                        # Safety: Ensure meaningful distance (at least 0.05%) to prevents infinite sizing on tight wicks
                        dist_pct = abs(current_price - ref_stop) / current_price
                        if dist_pct < 0.0005:
                            if pos.direction == "long": ref_stop = current_price * 0.9995
                            else: ref_stop = current_price * 1.0005

                        # Enforce a minimum stop distance before adding size.
                        stop_dist_pct = abs(current_price - ref_stop) / current_price
                        if stop_dist_pct < MIN_STOP_PCT:
                            continue

                        add_risk_amount = None
                        if FIXED_RISK_DOLLARS > 0:
                            add_risk_amount = current_equity * risk_to_use
                        add_size = calculate_position_size(
                            current_equity, risk_to_use, current_price, ref_stop, symbol, risk_amount=add_risk_amount
                        )
                        total_size = pos.size + add_size
                        new_avg = (pos.avg_price * pos.size + current_price * add_size) / total_size
                        
                        pos.avg_price = new_avg
                        pos.size = total_size
                        
                        # [SOFTWARE BE] Update Protection Levels - PURE WET FEET
                        # User Constraint: "N-1 causes issues, as it reduces the legs".
                        # Solution: Protect at AVERAGE PRICE (True Breakeven) for ALL levels.
                        # This gives the trade MAXIMUM room (the entire profit buffer) to breathe.
                        
                        pos.protection_price = new_avg
                        protection_type = "Avg Price (Max Room)"

                        # Delay breakeven move to avoid immediate shakeouts.
                        pos.pending_be_price = pos.protection_price
                        pos.last_add_index = bar_idx
                        
                        # New Ceiling = Current Add Price (for next N-1 reference)
                        pos.latest_add_price = current_price
                        
                        pos.pyramid_count += 1
                        total_pyramids += 1
                        
                        logger.info(f"[PYRAMID] {symbol} add #{pos.pyramid_count} @ {current_price:.5f}, profit={profit_pct*100:.2f}%, size={total_size}, new_avg={pos.avg_price:.5f} [Protection: {pos.protection_price:.5f} ({protection_type})]")
                
                # 3. Check HTF FLIP - SMART EXIT: only exit if in loss, let profitable trades run
                if pos.direction == "long":
                    current_pnl = (current_price - pos.avg_price) / pos.avg_price
                else:
                    current_pnl = (pos.avg_price - current_price) / pos.avg_price
                
                # Only exit on HTF flip if we're at a LOSS or barely profitable
                if current_pnl <= HTF_FLIP_EXIT_PNL:
                    if pos.direction == "long" and current_htf_dir == "short":
                        pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                        capital += pnl
                        completed_trades.append(ForexTrade(
                            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                            exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                            exit_time=current_time, pnl=pnl, exit_reason="htf_flip",
                            pyramid_count=pos.pyramid_count, score=pos.score
                        ))
                        logger.info(f"[EXIT] {symbol} HTF flip: was long, HTF now short (at loss)")
                        del positions[symbol]
                        continue
                    elif pos.direction == "short" and current_htf_dir == "long":
                        pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                        capital += pnl
                        completed_trades.append(ForexTrade(
                            symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                            exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                            exit_time=current_time, pnl=pnl, exit_reason="htf_flip",
                            pyramid_count=pos.pyramid_count, score=pos.score
                        ))
                        logger.info(f"[EXIT] {symbol} HTF flip: was short, HTF now long (at loss)")
                        del positions[symbol]
                        continue
                # If in profit during HTF flip, let it ride and trail with structure
                
                # 4. Check SWING INVALIDATION (structure break)
                if pos.direction == "long" and current_bar.close < pos.swing_invalidation:
                    pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                        exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="structure",
                        pyramid_count=pos.pyramid_count, score=pos.score
                    ))
                    logger.info(f"[EXIT] {symbol} structure break: close < swing_low")
                    del positions[symbol]
                    continue
                elif pos.direction == "short" and current_bar.close > pos.swing_invalidation:
                    pnl = calculate_pnl(pos.avg_price, current_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                        exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="structure",
                        pyramid_count=pos.pyramid_count, score=pos.score
                    ))
                    logger.info(f"[EXIT] {symbol} structure break: close > swing_high")
                    del positions[symbol]
                    continue
                
                # Update swing invalidation level (trail it)
                # Update swing invalidation level (trail it)
                # [TIERED BUFFER] Re-calc ATR
                is_volatile = any(x in symbol for x in ["BTC", "ETH", "SOL", "XAU", "PAXG"])
                buffer_mult = 1.0 if is_volatile else 0.1
                
                recent_volt = ltf_candles[-14:]
                atr_val = sum(c.high - c.low for c in recent_volt) / len(recent_volt) if recent_volt else 0.0
                
                raw_struct = get_swing_invalidation(ltf_candles, pos.direction) # Revert to LTF structure for trail
                
                if pos.direction == "long":
                     new_invalidation = raw_struct - (atr_val * buffer_mult)
                else:
                     new_invalidation = raw_struct + (atr_val * buffer_mult)
                if pos.direction == "long" and new_invalidation > pos.swing_invalidation:
                    pos.swing_invalidation = new_invalidation
                elif pos.direction == "short" and new_invalidation < pos.swing_invalidation:
                    pos.swing_invalidation = new_invalidation
                
                pos.last_htf_dir = current_htf_dir
                continue  # Stay in position
            
            # NEW ENTRY LOGIC
            if not trend_htf or not trend_ltf:
                continue
            
            htf_dir = str(trend_htf.direction)
            ltf_dir = str(trend_ltf.direction)
            htf_strength = float(trend_htf.strength or 0.0)
            
            htf_align = ltf_dir != "neutral" and (htf_dir == "neutral" or htf_dir == ltf_dir)
            
            if ltf_dir not in ("long", "short"):
                continue

            # Chop/NTZ filters disabled per user request.
            
            sweep = detect_liquidity_sweep(ltf_candles, ltf_dir, swing_lookback=2)
            indication = detect_indication(ltf_candles, swing_lookback=2)
            correction = detect_correction(ltf_candles, indication, swing_lookback=2)
            continuation = detect_continuation(
                ltf_candles, ltf_dir, sweep, indication, correction,
                require_sweep=False, require_indication=False, require_correction=False,
                swing_lookback=2, confirmation_bars=2
            )
            
            # [RELAXED ENTRY]
            # Allow (Sweep + Indication) OR Continuation
            valid_entry = continuation is not None or (sweep is not None and indication is not None)
            
            if not valid_entry:
                continue
            
            # MOMENTUM FILTER: Require sweep for entry
            if REQUIRE_SWEEP and sweep is None:
                continue
            
            # MOMENTUM FILTER: Require strong HTF strength
            if htf_strength < MIN_HTF_STRENGTH:
                continue
            
            # MOMENTUM FILTER: Check recent price momentum (must be moving in direction)
            recent_5 = ltf_candles[-5:]
            if ltf_dir == "long":
                momentum_pips = (recent_5[-1].close - min(c.low for c in recent_5)) * (100 if "JPY" in symbol else 10000)
            else:
                momentum_pips = (max(c.high for c in recent_5) - recent_5[-1].close) * (100 if "JPY" in symbol else 10000)

            if momentum_pips < MIN_MOMENTUM_PIPS:
                continue

            # Volatility filter: skip entries when range is too tight.
            range_pips = (max(c.high for c in recent_5) - min(c.low for c in recent_5)) * (100 if "JPY" in symbol else 10000)
            if range_pips < MIN_ENTRY_RANGE_PIPS:
                continue
            
            phase = "continuation" if continuation else "indication"
            score, threshold = score_icc_entry(
                profile, trend_htf, trend_ltf, htf_align, sweep, continuation, indication, phase
            )
            
            if score < threshold:
                continue
            
            entry_price = current_price
            atr = sum(abs(c.high - c.low) for c in ltf_candles[-14:]) / 14
            
            if ltf_dir == "long":
                stop_price = entry_price - (atr * 1.5)  # Tighter stop (was 2.0)
            else:
                stop_price = entry_price + (atr * 1.5)  # Tighter stop (was 2.0)

            # Enforce a minimum stop distance on entry to avoid micro-stops.
            stop_dist_pct = abs(entry_price - stop_price) / entry_price
            if stop_dist_pct < MIN_STOP_PCT:
                continue
            
            # [TIERED BUFFER]
            # Crypto/Gold = 1.0 ATR (Survive wicks)
            # Forex = 0.1 ATR (Tight)
            is_volatile = any(x in symbol for x in ["BTC", "ETH", "SOL", "XAU", "PAXG"])
            buffer_mult = 1.0 if is_volatile else 0.1
            
            # Calculate ATR for buffer
            # (Simple 14-period avg of High-Low)
            recent_volt = ltf_candles[-14:]
            atr_val = sum(c.high - c.low for c in recent_volt) / len(recent_volt) if recent_volt else 0.0
            
            raw_struct = get_swing_invalidation(ltf_candles, ltf_dir)
            
            if ltf_dir == "long":
                 swing_invalidation = raw_struct - (atr_val * buffer_mult)
            else:
                 swing_invalidation = raw_struct + (atr_val * buffer_mult)
            
            # Asymmetric risk: conservative on shorts, aggressive on longs
            # Asymmetric risk: conservative on shorts, aggressive on longs
            base_risk = LONG_RISK_PCT if ltf_dir == "long" else SHORT_RISK_PCT
            
            # [DYNAMIC RISK SIZING for COMPOUNDING]
            # Scale Base Risk % by Trend Strength
            htf_val = float(trend_htf.strength or 0.0)
            if htf_val >= 0.5:
                risk_mult = 1.0
            elif htf_val >= 0.3:
                risk_mult = 0.5
            else:
                risk_mult = 0.25
                
            risk_pct = base_risk * risk_mult
            
            initial_risk_amount = None
            if FIXED_RISK_DOLLARS > 0:
                # [DYNAMIC RISK SIZING]
                # Scale risk based on HTF strength to handle chop without strict blocking.
                # Strength >= 0.5: 100% Risk ($0.50)
                # Strength >= 0.3: 50% Risk ($0.25)
                # Strength < 0.3:  25% Risk ($0.125) - "Chop Fishing"
                
                if htf_strength >= 0.5:
                    initial_risk_amount = FIXED_RISK_DOLLARS
                elif htf_strength >= 0.3:
                    initial_risk_amount = FIXED_RISK_DOLLARS * 0.5
                else:
                    initial_risk_amount = FIXED_RISK_DOLLARS * 0.25
                
            initial_size = calculate_position_size(
                capital, risk_pct, entry_price, stop_price, symbol, risk_amount=initial_risk_amount
            )
            
            positions[symbol] = ForexPosition(
                symbol=symbol, direction=ltf_dir, entry_price=entry_price,
                avg_price=entry_price, size=initial_size, entry_time=current_time,
                stop_price=stop_price, swing_invalidation=swing_invalidation,
                pyramid_count=0, score=score, last_htf_dir=htf_dir,
                latest_add_price=entry_price, protection_price=0.0
            )
            logger.info(f"[ENTRY] {symbol} {ltf_dir} @ {entry_price:.5f}, score={score:.0f}, size={initial_size}")
    
    # Close remaining positions
    for symbol, pos in list(positions.items()):
        if all_candles.get(symbol):
            last_bar = all_candles[symbol][-1]
            pnl = calculate_pnl(pos.avg_price, last_bar.close, pos.size, pos.direction, symbol)
            capital += pnl
            completed_trades.append(ForexTrade(
                symbol=symbol, direction=pos.direction, entry_price=pos.avg_price,
                exit_price=last_bar.close, size=pos.size, entry_time=pos.entry_time,
                exit_time=last_bar.timestamp, pnl=pnl, exit_reason="eod",
                pyramid_count=pos.pyramid_count, score=pos.score
            ))
    
    # Results
    print("\n" + "=" * 80)
    print("RESULTS - FEET WET + STRUCTURE EXITS")
    print("=" * 80)
    print(f"Total Pyramid Adds: {total_pyramids}")
    print(f"Trades: {len(completed_trades)}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Total PnL: ${capital - INITIAL_CAPITAL:.2f}")
    print(f"Return: {(capital / INITIAL_CAPITAL - 1) * 100:.2f}%")

    # DETAILED CAPITAL JOURNAL
    print("\n" + "=" * 80)
    print("DETAILED TRADE JOURNAL (Chronological)")
    print("=" * 80)
    print(f"{'Date':<12} {'Symbol':<10} {'Dir':<6} {'Entry':<12} {'Exit':<12} {'Size':<12} {'PnL':<12} {'Capital':<14} {'Pyr':<4}")
    print("-" * 110)

    # Sort trades by exit time
    sorted_trades = sorted(completed_trades, key=lambda t: t.exit_time)
    running_capital = INITIAL_CAPITAL

    current_date = None
    daily_pnl = 0.0

    for t in sorted_trades:
        trade_date = t.exit_time.strftime("%Y-%m-%d")

        # Print daily summary when date changes
        if current_date and trade_date != current_date:
            print(f"{'─'*110}")
            print(f"  📊 Day End {current_date}: Daily PnL = ${daily_pnl:+.2f}, Capital = ${running_capital:.2f}")
            print(f"{'─'*110}")
            daily_pnl = 0.0

        current_date = trade_date
        running_capital += t.pnl
        daily_pnl += t.pnl

        pyr_mark = f"🔺{t.pyramid_count}" if t.pyramid_count > 0 else ""
        pnl_color = "+" if t.pnl >= 0 else ""

        # Format size appropriately
        if t.size >= 1000:
            size_str = f"{t.size/1000:.1f}K"
        elif t.size >= 1:
            size_str = f"{t.size:.2f}"
        else:
            size_str = f"{t.size:.6f}"

        print(f"{trade_date:<12} {t.symbol:<10} {t.direction:<6} {t.entry_price:<12.5f} {t.exit_price:<12.5f} {size_str:<12} ${pnl_color}{t.pnl:<11.2f} ${running_capital:<13.2f} {pyr_mark:<4}")

    # Final day summary
    if current_date:
        print(f"{'─'*110}")
        print(f"  📊 Day End {current_date}: Daily PnL = ${daily_pnl:+.2f}, Capital = ${running_capital:.2f}")
        print(f"{'─'*110}")

    print(f"\n{'='*110}")
    print(f"  SUMMARY: Started ${INITIAL_CAPITAL:.2f} → Ended ${running_capital:.2f} ({(running_capital/INITIAL_CAPITAL-1)*100:+.2f}%)")
    print(f"{'='*110}")
    
    if completed_trades:
        winners = [t for t in completed_trades if t.pnl > 0]
        losers = [t for t in completed_trades if t.pnl < 0]
        print(f"\nWinners: {len(winners)} (${sum(t.pnl for t in winners):.2f})")
        print(f"Losers: {len(losers)} (${sum(t.pnl for t in losers):.2f})")
        print(f"Win Rate: {len(winners)/len(completed_trades)*100:.1f}%")
        
        pyramid_trades = [t for t in completed_trades if t.pyramid_count > 0]
        no_pyramid = [t for t in completed_trades if t.pyramid_count == 0]
        
        print(f"\nWith Pyramids: {len(pyramid_trades)} trades, ${sum(t.pnl for t in pyramid_trades):.2f}")
        
        # [ANTIGRAVITY ANALYSIS] Pyramid Losers
        pyramid_losers = [t.pnl for t in pyramid_trades if t.pnl < 0]
        print(f"Pyramid Failed Trades (Trap): {len(pyramid_losers)} trades, ${sum(pyramid_losers):.2f} (Avg: ${sum(pyramid_losers)/len(pyramid_losers) if pyramid_losers else 0:.2f})")
        if pyramid_losers:
            print(f"  Worst Pyramid Loss: ${min(pyramid_losers):.2f}")

        print(f"Without Pyramids: {len(no_pyramid)} trades, ${sum(t.pnl for t in no_pyramid):.2f}")
        
        print("\nBy Exit Reason:")
        for reason in set(t.exit_reason for t in completed_trades):
            rt = [t for t in completed_trades if t.exit_reason == reason]
            print(f"  {reason}: {len(rt)} trades, ${sum(t.pnl for t in rt):.2f}")
        
        print("\nTrade Details:")
        for t in completed_trades[:20]:
            pyramid_marker = f"🔺{t.pyramid_count}" if t.pyramid_count > 0 else ""
            print(f"  {t.symbol} {t.direction}: ${t.pnl:.2f} ({t.exit_reason}) {pyramid_marker}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(run_forex_backtest())
