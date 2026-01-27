#!/usr/bin/env python3
"""Friday Fade Validation - ICC Backtest for Forex.

Tests the Friday Fade Risk Damper using the same ICC logic
as run_forex_backtest_full.py but filtered to Jan 22-24, 2026.
"""

import sys
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.market.models import Candle, TrendState
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.strategy.icc_signals import (
    detect_continuation,
    detect_liquidity_sweep,
    detect_indication,
    detect_correction,
)

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger("friday_icc")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')
INITIAL_CAPITAL = 25.0
RISK_PCT = 0.20  # 20% base risk

@dataclass
class Trade:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str
    risk_used: float = 0.0

@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    size: float
    entry_time: datetime
    stop_price: float
    risk_used: float = 0.0

def load_candles(symbol: str) -> List[Candle]:
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
    if stop_distance == 0:
        return 0
    if symbol.startswith("USD") and "JPY" in symbol:
        stop_distance = stop_distance / entry_price
    units = risk_amount / stop_distance
    return max(1, int(units))

def is_friday_fade_active(timestamp: datetime) -> bool:
    """Check if Friday Fade should be active (Friday >= 12 PM EST)."""
    from zoneinfo import ZoneInfo
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    est_time = timestamp.astimezone(ZoneInfo("America/New_York"))
    # Friday is 4
    return est_time.weekday() == 4 and est_time.hour >= 12

def run_friday_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    settings = load_settings()

    print("=" * 80)
    print("WEEKLY ICC BACKTEST (Jan 22-24)")
    print("=" * 80)
    print(f"Capital: ${INITIAL_CAPITAL}")
    print(f"Base Risk: {RISK_PCT*100}%")
    print(f"Friday Fade: ENABLED")
    print()

    # Forex pairs (Explicit List of available data)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
    
    print(f"Testing {len(symbols)} Assets: {symbols}")

    all_candles = {}
    for symbol in symbols:
        candles = load_candles(symbol)
        if candles:
            all_candles[symbol] = candles
            print(f"Loaded {len(candles)} candles for {symbol}")

    if not all_candles:
        print("No data!")
        return 1

    capital = INITIAL_CAPITAL
    positions: Dict[str, Position] = {}
    completed_trades: List[Trade] = []

    # Get timestamps for Thursday Jan 22 - Saturday Jan 24
    start_date_range = datetime(2026, 1, 22, tzinfo=timezone.utc).date()
    end_date_range = datetime(2026, 1, 24, tzinfo=timezone.utc).date()

    all_times = sorted(set(
        c.timestamp for candles in all_candles.values() for c in candles
        if start_date_range <= c.timestamp.date() <= end_date_range
    ))

    print(f"\nBacktest Date: Jan 22-24, 2026 (WEEKLY SIMULATION - MARKET HOURS ONLY)")
    print(f"Bars: {len(all_times)}")
    print()

    morning_trades = 0
    afternoon_trades = 0

    for i, current_time in enumerate(all_times):
        # SKIP WEEKEND DATA (Market Close is Friday ~22:00 UTC)
        # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        if current_time.weekday() > 4:
            continue
            
        if i < 20:  # Need warmup
            continue

        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 20:
                continue

            current_bar = candles[bar_idx]
            lookback = candles[max(0, bar_idx-100):bar_idx+1]
            current_price = current_bar.close

            htf_candles = lookback[-60:]
            ltf_candles = lookback[-30:]
            trend_htf = infer_trend_from_swings(htf_candles, window=12, swing_lookback=2, min_swings=2, strength_floor=0.25)
            trend_ltf = infer_trend_from_swings(ltf_candles, window=8, swing_lookback=2, min_swings=2, strength_floor=0.25)

            pos = positions.get(symbol)

            # Position management
            if pos:
                # Simple stop check
                if pos.direction == "long" and current_bar.low <= pos.stop_price:
                    pnl = calculate_pnl(pos.entry_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(Trade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=pos.stop_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="stop", risk_used=pos.risk_used
                    ))
                    del positions[symbol]
                    continue
                elif pos.direction == "short" and current_bar.high >= pos.stop_price:
                    pnl = calculate_pnl(pos.entry_price, pos.stop_price, pos.size, pos.direction, symbol)
                    capital += pnl
                    completed_trades.append(Trade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=pos.stop_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl, exit_reason="stop", risk_used=pos.risk_used
                    ))
                    del positions[symbol]
                    continue

                # Scalp exit at small profit (Quick TP)
                if pos.direction == "long":
                    pnl_check = calculate_pnl(pos.entry_price, current_price, pos.size, pos.direction, symbol)
                else:
                    pnl_check = calculate_pnl(pos.entry_price, current_price, pos.size, pos.direction, symbol)

                # Use a larger TP for Thursday runs to capture "Profit"
                tp_target = 0.20 # $0.20
                if pnl_check >= tp_target:
                    capital += pnl_check
                    completed_trades.append(Trade(
                        symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=current_price, size=pos.size, entry_time=pos.entry_time,
                        exit_time=current_time, pnl=pnl_check, exit_reason="scalp_tp", risk_used=pos.risk_used
                    ))
                    del positions[symbol]
                    continue

                continue  # Stay in position

            # NEW ENTRY LOGIC
            if not trend_htf or not trend_ltf:
                continue

            htf_dir = str(trend_htf.direction)
            ltf_dir = str(trend_ltf.direction)

            if ltf_dir not in ("long", "short"):
                continue

            sweep = detect_liquidity_sweep(ltf_candles, ltf_dir, swing_lookback=2)
            indication = detect_indication(ltf_candles, swing_lookback=2)
            correction = detect_correction(ltf_candles, indication, swing_lookback=2)
            continuation = detect_continuation(
                ltf_candles, ltf_dir, sweep, indication, correction,
                require_sweep=False, require_indication=False, require_correction=False,
                swing_lookback=2, confirmation_bars=2
            )

            valid_entry = continuation is not None or (sweep is not None and indication is not None)

            if not valid_entry:
                continue

            entry_price = current_price
            atr = sum(abs(c.high - c.low) for c in ltf_candles[-14:]) / 14

            if ltf_dir == "long":
                # Tighter stops for better R/R
                stop_price = entry_price - (atr * 1.5)
            else:
                stop_price = entry_price + (atr * 1.5)

            # FRIDAY FADE RISK DAMPER
            friday_fade_active = is_friday_fade_active(current_time)
            if friday_fade_active:
                risk_to_use = 0.0025  # 0.25%
                logger.info(f"[FRIDAY FADE] {symbol} @ {current_time.strftime('%H:%M')} - Risk capped to 0.25%")
                afternoon_trades += 1
            else:
                risk_to_use = RISK_PCT  # 20%
                morning_trades += 1

            initial_size = calculate_position_size(capital, risk_to_use, entry_price, stop_price, symbol)

            if initial_size < 1:
                continue

            # CHECK MAX POSITIONS (User Rule: Max 4 Concurrent)
            if len(positions) >= 4:
                # print(f"Skipping {symbol}: Max positions (4) reached")
                continue

            positions[symbol] = Position(
                symbol=symbol, direction=ltf_dir, entry_price=entry_price,
                size=initial_size, entry_time=current_time, stop_price=stop_price,
                risk_used=risk_to_use
            )
            logger.info(f"[ENTRY] {symbol} {ltf_dir} @ {entry_price:.5f}, risk={risk_to_use*100:.2f}%, size={initial_size}")

    # Close remaining positions
    for symbol, pos in list(positions.items()):
        if all_candles.get(symbol):
            last_bar = all_candles[symbol][-1]
            pnl = calculate_pnl(pos.entry_price, last_bar.close, pos.size, pos.direction, symbol)
            capital += pnl
            completed_trades.append(Trade(
                symbol=symbol, direction=pos.direction, entry_price=pos.entry_price,
                exit_price=last_bar.close, size=pos.size, entry_time=pos.entry_time,
                exit_time=last_bar.timestamp, pnl=pnl, exit_reason="eod", risk_used=pos.risk_used
            ))

    # Results
    print("\n" + "=" * 80)
    print("WEEKLY SIMULATION RESULTS")
    print("=" * 80)
    print(f"Trades: {len(completed_trades)}")
    print(f"Normal Trades: {morning_trades}")
    print(f"Friday Fade Trades: {afternoon_trades}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Total PnL: ${capital - INITIAL_CAPITAL:.2f}")
    print(f"Return: {(capital / INITIAL_CAPITAL - 1) * 100:.2f}%")

    if completed_trades:
        print("\n" + "-" * 80)
        print("Trade Details (Last 20):")
        print("-" * 80)
        for t in completed_trades:
            fade_marker = "[FADE]" if t.risk_used <= 0.003 else ""
            print(f"{t.exit_time.strftime('%d-%H:%M')} {t.symbol} {t.direction} risk={t.risk_used*100:.2f}% PnL=${t.pnl:+.2f} ({t.exit_reason}) {fade_marker}")

    return 0

if __name__ == "__main__":
    raise SystemExit(run_friday_backtest())
