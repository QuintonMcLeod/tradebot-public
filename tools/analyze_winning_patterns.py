"""
Retrospective Market Analysis Tool
===================================
Instead of guessing strategies, this tool:
1. Looks at where the market ACTUALLY went (hindsight)
2. Identifies the best potential trades (moves of 1%+)
3. Analyzes what conditions existed BEFORE those moves
4. Finds common patterns that could predict these moves

This is "designing the war strategy after knowing how it ends."
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import List, Dict, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.market.models import Candle
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.icc_signals import (
    calculate_atr,
    detect_indication,
    detect_correction,
    detect_liquidity_sweep,
    detect_no_trade_zone,
)


@dataclass
class BigMove:
    """Represents a significant market move (Winner or Loser)."""
    symbol: str
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    direction: str  # "long" or "short"
    pct_move: float
    duration_bars: int
    is_loser: bool = False # Was this a move AGAINST a potential signal?
    
    # Pre-move conditions
    had_indication: bool = False
    had_correction: bool = False
    had_sweep: bool = False
    had_ntz: bool = False
    ltf_trend_before: str = ""
    htf_trend_before: str = ""
    atr_normalized_move: float = 0.0


DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'jan_2026')

def load_candles_from_cache(symbol: str) -> List[Candle]:
    """Load candle data for a symbol from the same source as the backtest."""
    filepath = os.path.join(DATA_DIR, f'{symbol}_15m.json')
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    candles = []
    for bar in data:
        ts = bar.get('timestamp', '')
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
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


def find_big_moves(candles: List[Candle], symbol: str, min_pct_move: float = 0.5) -> List[BigMove]:
    """Find all significant price moves, tagging both directions."""
    big_moves = []
    if len(candles) < 20: return big_moves
    
    i = 0
    while i < len(candles) - 10:
        start_candle = candles[i]
        start_p = start_candle.close
        
        best_up = start_p
        best_down = start_p
        up_idx = i
        down_idx = i
        
        for j in range(i + 1, min(i + 50, len(candles))):
            c = candles[j]
            if c.high > best_up:
                best_up = c.high
                up_idx = j
            if c.low < best_down:
                best_down = c.low
                down_idx = j
                
        up_pct = (best_up - start_p) / start_p * 100
        down_pct = (start_p - best_down) / start_p * 100
        
        # Detect winners (moves in signal direction)
        if up_pct >= min_pct_move:
            big_moves.append(BigMove(symbol, start_candle.timestamp, candles[up_idx].timestamp, start_p, best_up, "long", up_pct, up_idx - i))
        
        if down_pct >= min_pct_move:
            big_moves.append(BigMove(symbol, start_candle.timestamp, candles[down_idx].timestamp, start_p, best_down, "short", down_pct, down_idx - i))
            
        # Detect losers (adverse moves after a hypothetical signal)
        # If there's a huge move one way, we want to know what signals suggested the OTHER way
        if up_pct >= (min_pct_move * 2): # Huge upward move
             # Was there a SHORT signal before this?
             big_moves.append(BigMove(symbol, start_candle.timestamp, candles[up_idx].timestamp, start_p, best_up, "short", up_pct, up_idx - i, is_loser=True))
        
        if down_pct >= (min_pct_move * 2): # Huge downward move
             big_moves.append(BigMove(symbol, start_candle.timestamp, candles[down_idx].timestamp, start_p, best_down, "long", down_pct, down_idx - i, is_loser=True))
                
        i += 5 # Tighten window for better coverage
    
    return big_moves


def analyze_pre_move_conditions(candles: List[Candle], move: BigMove, lookback: int = 20) -> BigMove:
    """
    Analyze what conditions existed BEFORE the big move started.
    This is the "hindsight" analysis that tells us what patterns preceded winning moves.
    """
    # Find the index of the move start
    start_idx = None
    for idx, c in enumerate(candles):
        if c.timestamp >= move.start_time:
            start_idx = idx
            break
    
    if start_idx is None or start_idx < lookback:
        return move
    
    # Get the candles BEFORE the move
    pre_move_candles = candles[start_idx - lookback : start_idx]
    
    if len(pre_move_candles) < 10:
        return move
    
    # Analyze what signals were present before the move
    
    # 1. Was there an Indication (impulse move)?
    indication = detect_indication(pre_move_candles, swing_lookback=1)
    if indication:
        move.had_indication = True
        # Check if indication direction matches the subsequent move
        if indication.direction == move.direction:
            move.had_indication = True  # Aligned indication
    
    # 2. Was there a Correction (pullback)?
    if indication:
        correction = detect_correction(pre_move_candles, indication, swing_lookback=1)
        move.had_correction = correction is not None
    
    # 3. Was there a Liquidity Sweep?
    sweep = detect_liquidity_sweep(pre_move_candles, move.direction, swing_lookback=2)
    move.had_sweep = sweep is not None
    
    # 4. Was there a No Trade Zone (range)?
    ntz = detect_no_trade_zone(pre_move_candles, swing_lookback=2)
    move.had_ntz = ntz is not None and not ntz.is_broken
    
    # 5. What was the trend?
    ltf_trend = infer_trend_from_swings(pre_move_candles)
    htf_trend = infer_trend_from_swings(pre_move_candles[-30:] if len(pre_move_candles) >= 30 else pre_move_candles)
    move.ltf_trend_before = str(ltf_trend.direction)
    move.htf_trend_before = str(htf_trend.direction)
    
    # 6. ATR-normalized move size
    atr = calculate_atr(pre_move_candles, period=14)
    if atr and atr > 0:
        move.atr_normalized_move = abs(move.end_price - move.start_price) / atr
    
    return move


def main():
    print("=" * 60)
    print("RETROSPECTIVE MARKET ANALYSIS: WINNERS VS LOSERS")
    print("Finding what patterns preceded big moves vs big failures")
    print("=" * 60)
    
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "ETHUSD", "SOLUSD"]
    all_moves: List[BigMove] = []
    
    for symbol in symbols:
        print(f"\nLoading {symbol}...")
        candles = load_candles_from_cache(symbol)
        if not candles:
            continue
        
        print(f"  {len(candles)} candles loaded")
        
        min_move = 0.2 if 'XAU' in symbol else 0.5
        moves = find_big_moves(candles, symbol, min_pct_move=min_move)
        print(f"  Found {len(moves)} significant moves")
        
        for move in moves:
            move = analyze_pre_move_conditions(candles, move)
            all_moves.append(move)
    
    if not all_moves:
        print("\nNo big moves found in data!")
        return
    
    winners = [m for m in all_moves if not m.is_loser]
    losers = [m for m in all_moves if m.is_loser]
    
    print(f"\nAnalysis Summary:")
    print(f"  Total Potential Winning Moves: {len(winners)}")
    print(f"  Total Significant Failed Moves: {len(losers)}")
    
    def print_pattern_stats(moves_list, title):
        print(f"\n--- {title} PATTERNS ---")
        total = len(moves_list)
        if total == 0: return
        
        had_ind = sum(1 for m in moves_list if m.had_indication)
        had_sweep = sum(1 for m in moves_list if m.had_sweep)
        had_ntz = sum(1 for m in moves_list if m.had_ntz)
        
        print(f"  Indication Rate: {had_ind/total*100:.1f}%")
        print(f"  Sweep Rate:      {had_sweep/total*100:.1f}%")
        print(f"  NTZ Rate:        {had_ntz/total*100:.1f}%")
        
        patterns = defaultdict(int)
        for m in moves_list:
            key = []
            if m.had_indication: key.append("IND")
            if m.had_sweep: key.append("SWEEP")
            if not key: key.append("NONE")
            patterns['+'.join(key)] += 1
            
        sorted_p = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
        for p, count in sorted_p[:5]:
            print(f"    {p:<15}: {count:>3} ({count/total*100:.1f}%)")

    print_pattern_stats(winners, "WINNER")
    print_pattern_stats(losers, "LOSER")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC: How to filter the losers?")
    print("=" * 60)
    
    # Calculate ratio of Winner Presence / Loser Presence
    win_patterns = set()
    for m in winners:
        p = []
        if m.had_indication: p.append("IND")
        if m.had_sweep: p.append("SWEEP")
        win_patterns.add('+'.join(p) if p else "NONE")
        
    for p in win_patterns:
        w_count = sum(1 for m in winners if ('IND' in p) == m.had_indication and ('SWEEP' in p) == m.had_sweep)
        l_count = sum(1 for m in losers if ('IND' in p) == m.had_indication and ('SWEEP' in p) == m.had_sweep)
        w_rate = w_count / len(winners)
        l_rate = l_count / len(losers) if losers else 0
        
        ratio = w_rate / (l_rate + 0.001)
        print(f"  Pattern {p:<15}: Win Prob {w_rate*100:>5.1f}% | Fail Prob {l_rate*100:>5.1f}% | Edge Ratio: {ratio:.2f}")

if __name__ == "__main__":
    main()
