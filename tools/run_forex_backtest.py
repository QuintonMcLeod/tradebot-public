#!/usr/bin/env python3
"""Run ICC backtest on saved Forex data using direct signal detection.

Uses the JSON candle files and ICC signal detection directly.
"""

import sys
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional, Dict

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.icc_signals import detect_continuation, detect_liquidity_sweep

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("forex_icc_backtest")
logger.setLevel(logging.INFO)

# Configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')
INITIAL_CAPITAL = 500.0  # Realistic small Forex account
RISK_PER_TRADE = 0.02  # 2% risk per trade
MICRO_LOT = 1000  # 1 micro lot = 1000 units

# Forex pairs
FOREX_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

@dataclass
class ForexTrade:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float  # In units
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str
    had_continuation: bool = False
    had_sweep: bool = False
    htf_direction: str = "neutral"
    ltf_direction: str = "neutral"

@dataclass  
class ForexPosition:
    symbol: str
    direction: str
    entry_price: float
    size: float  # In units
    entry_time: datetime
    stop_price: float
    target_price: Optional[float] = None
    had_continuation: bool = False
    had_sweep: bool = False
    htf_direction: str = "neutral"
    ltf_direction: str = "neutral"

def load_candles(symbol: str) -> List[Candle]:
    """Load candles from JSON file."""
    filepath = os.path.join(DATA_DIR, f'{symbol}_5m.json')
    if not os.path.exists(filepath):
        logger.warning(f"No data file for {symbol}")
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

def calculate_pnl(entry_price: float, exit_price: float, micro_lots: float, direction: str, symbol: str) -> float:
    """Calculate PnL for Forex trade.
    
    1 micro lot = 1000 units = $0.10 per pip for standard pairs
    1 pip = 0.0001 for EUR/GBP/AUD pairs
    1 pip = 0.01 for JPY pairs
    """
    if direction == "short":
        price_diff = entry_price - exit_price
    else:
        price_diff = exit_price - entry_price
    
    # Convert price difference to pips, then to dollars
    if "JPY" in symbol:
        # JPY pairs: 1 pip = 0.01, pip value = ~$0.07 per micro lot at ~¥150/USD
        pips = price_diff * 100  # Convert to pips (e.g., 0.50 YEN move = 50 pips)
        pip_value = 0.065  # ~$0.065 per pip per micro lot
    else:
        # Standard pairs: 1 pip = 0.0001, pip value = $0.10 per micro lot
        pips = price_diff * 10000  # Convert to pips (e.g., 0.0001 = 1 pip)
        pip_value = 0.10  # $0.10 per pip per micro lot
    
    return pips * pip_value * micro_lots

def run_forex_backtest():
    """Run ICC strategy backtest on Forex data."""
    
    print("=" * 80)
    print("FOREX ICC BACKTEST")
    print("=" * 80)
    print(f"Initial Capital: ${INITIAL_CAPITAL:.2f}")
    print(f"Risk per Trade: {RISK_PER_TRADE*100:.1f}%")
    print(f"Position Sizing: Micro lots (1000 units)")
    
    # Load all candle data
    all_candles: Dict[str, List[Candle]] = {}
    for symbol in FOREX_PAIRS:
        candles = load_candles(symbol)
        if candles:
            all_candles[symbol] = candles
            logger.info(f"Loaded {len(candles)} candles for {symbol}")
    
    if not all_candles:
        print("ERROR: No candle data found!")
        return 1
    
    # Backtest state
    capital = INITIAL_CAPITAL
    positions: Dict[str, ForexPosition] = {}
    completed_trades: List[ForexTrade] = []
    
    # Find common time range
    all_times = set()
    for candles in all_candles.values():
        for c in candles:
            all_times.add(c.timestamp)
    sorted_times = sorted(all_times)
    
    print(f"\nBacktest period: {sorted_times[0]} to {sorted_times[-1]}")
    print(f"Total bars: {len(sorted_times)}")
    print("\nRunning backtest...")
    
    entry_count = 0
    
    # Process each timestamp
    for i, current_time in enumerate(sorted_times):
        if i < 50:  # Need warmup bars for trend analysis
            continue
            
        for symbol, candles in all_candles.items():
            # Find current bar index
            bar_idx = None
            for j, c in enumerate(candles):
                if c.timestamp == current_time:
                    bar_idx = j
                    break
            
            if bar_idx is None or bar_idx < 50:
                continue
            
            current_bar = candles[bar_idx]
            lookback_bars = candles[max(0, bar_idx-100):bar_idx+1]
            
            # Check existing position
            pos = positions.get(symbol)
            if pos:
                # Check stop hit
                if pos.direction == "long" and current_bar.low <= pos.stop_price:
                    pnl = calculate_pnl(pos.entry_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=pos.stop_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="stop",
                        had_continuation=pos.had_continuation, had_sweep=pos.had_sweep,
                        htf_direction=pos.htf_direction, ltf_direction=pos.ltf_direction
                    ))
                    del positions[symbol]
                    continue
                elif pos.direction == "short" and current_bar.high >= pos.stop_price:
                    pnl = calculate_pnl(pos.entry_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(ForexTrade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=pos.stop_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="stop",
                        had_continuation=pos.had_continuation, had_sweep=pos.had_sweep,
                        htf_direction=pos.htf_direction, ltf_direction=pos.ltf_direction
                    ))
                    del positions[symbol]
                    continue
                # Skip new entries if already in position
                continue
            
            # Build market analysis
            htf_candles = lookback_bars[-40:] if len(lookback_bars) >= 40 else lookback_bars
            ltf_candles = lookback_bars[-20:] if len(lookback_bars) >= 20 else lookback_bars
            
            trend_htf = infer_trend_from_swings(htf_candles, window=12, swing_lookback=3, min_swings=2, strength_floor=0.3)
            trend_ltf = infer_trend_from_swings(ltf_candles, window=8, swing_lookback=2, min_swings=2, strength_floor=0.25)
            
            # Detect ICC signals
            ltf_dir = str(trend_ltf.direction) if trend_ltf else "neutral"
            htf_dir = str(trend_htf.direction) if trend_htf else "neutral"
            
            # Detect sweep first (needed for continuation)
            sweep = None
            if ltf_dir in ("long", "short"):
                sweep = detect_liquidity_sweep(
                    candles=ltf_candles,
                    trend_direction=ltf_dir,
                    swing_lookback=2,
                )
            
            # Detect continuation - uses simplified params
            continuation = None
            if ltf_dir in ("long", "short"):
                continuation = detect_continuation(
                    candles=ltf_candles,
                    trend_direction=ltf_dir,
                    sweep=sweep,
                    indication=None,  # Not requiring indication for simplicity
                    correction=None,   # Not requiring correction for simplicity
                    require_sweep=False,
                    require_indication=False,
                    require_correction=False,
                    swing_lookback=2,
                    confirmation_bars=1,
                )
            
            # Require continuation signal and trend alignment
            if continuation and trend_htf and trend_ltf:
                cont_dir = continuation.direction
                if htf_dir == ltf_dir and htf_dir in ("long", "short") and cont_dir == htf_dir:
                    entry_price = current_bar.close
                    
                    # Calculate stop based on recent structure
                    if cont_dir == "long":
                        stop_price = min(c.low for c in ltf_candles[-5:]) * 0.9995
                        direction = "long"
                    else:
                        stop_price = max(c.high for c in ltf_candles[-5:]) * 1.0005
                        direction = "short"
                    
                    # Calculate position size
                    risk_amount = capital * RISK_PER_TRADE
                    risk_per_unit = abs(entry_price - stop_price)
                    
                    if risk_per_unit > 0:
                        # Size in units
                        if "JPY" in symbol:
                            raw_size = risk_amount / (risk_per_unit * 100)
                        else:
                            raw_size = risk_amount / (risk_per_unit * 10000)
                        
                        # Round to micro lots (store micro_lots directly, not units)
                        micro_lots = max(1, int(raw_size))
                        
                        positions[symbol] = ForexPosition(
                            symbol=symbol,
                            direction=direction,
                            entry_price=entry_price,
                            size=micro_lots,  # Store micro lots, not units
                            entry_time=current_time,
                            stop_price=stop_price,
                            had_continuation=True,
                            had_sweep=sweep is not None,
                            htf_direction=htf_dir,
                            ltf_direction=ltf_dir,
                        )
                        entry_count += 1
                        logger.info(f"[ENTRY] {symbol} {direction} @ {entry_price:.5f}, stop={stop_price:.5f}, size={micro_lots} lots")
    
    # Close any remaining positions at last price
    for symbol, pos in list(positions.items()):
        if symbol in all_candles and all_candles[symbol]:
            last_bar = all_candles[symbol][-1]
            pnl = calculate_pnl(pos.entry_price, last_bar.close, pos.size, pos.direction, symbol)
            capital += pnl
            completed_trades.append(ForexTrade(
                symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                exit_price=last_bar.close, size=pos.size, entry_time=pos.entry_time,
                exit_time=last_bar.timestamp, pnl=pnl, exit_reason="eod",
                had_continuation=pos.had_continuation, had_sweep=pos.had_sweep,
                htf_direction=pos.htf_direction, ltf_direction=pos.ltf_direction
            ))
    
    # Results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Trades: {len(completed_trades)}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Total PnL: ${capital - INITIAL_CAPITAL:.2f}")
    print(f"Return: {(capital / INITIAL_CAPITAL - 1) * 100:.2f}%")
    
    if completed_trades:
        winners = [t for t in completed_trades if t.pnl > 0]
        losers = [t for t in completed_trades if t.pnl < 0]
        print(f"\nWinners: {len(winners)} (${sum(t.pnl for t in winners):.2f})")
        print(f"Losers: {len(losers)} (${sum(t.pnl for t in losers):.2f})")
        if completed_trades:
            print(f"Win Rate: {len(winners)/len(completed_trades)*100:.1f}%")
        
        print("\nBy Symbol:")
        for symbol in FOREX_PAIRS:
            sym_trades = [t for t in completed_trades if t.symbol == symbol]
            if sym_trades:
                sym_pnl = sum(t.pnl for t in sym_trades)
                sym_winners = len([t for t in sym_trades if t.pnl > 0])
                print(f"  {symbol}: {len(sym_trades)} trades, WR={sym_winners/len(sym_trades)*100:.0f}%, ${sym_pnl:.2f}")
        
        # With sweep vs without
        with_sweep = [t for t in completed_trades if t.had_sweep]
        without_sweep = [t for t in completed_trades if not t.had_sweep]
        if with_sweep:
            sweep_wr = len([t for t in with_sweep if t.pnl > 0]) / len(with_sweep) * 100
            print(f"\nWith Sweep: {len(with_sweep)} trades, WR={sweep_wr:.0f}%, ${sum(t.pnl for t in with_sweep):.2f}")
        if without_sweep:
            no_sweep_wr = len([t for t in without_sweep if t.pnl > 0]) / len(without_sweep) * 100
            print(f"Without Sweep: {len(without_sweep)} trades, WR={no_sweep_wr:.0f}%, ${sum(t.pnl for t in without_sweep):.2f}")
        
        print("\nTrade History:")
        for t in completed_trades[:15]:
            sweep_marker = "🎯" if t.had_sweep else ""
            print(f"  {t.symbol} {t.direction}: ${t.pnl:.2f} ({t.exit_reason}) {sweep_marker}")
        if len(completed_trades) > 15:
            print(f"  ... and {len(completed_trades)-15} more trades")
    else:
        print("\nNo trades executed. Check entry conditions.")
        print(f"Entry attempts: {entry_count}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(run_forex_backtest())
