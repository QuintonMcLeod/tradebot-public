import sys
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.market.trend_enums import TrendDirection
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.config.models import UserConfig
from tradebot_sci.strategy.icc_signals import calculate_atr

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("robot_backtest")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'jan_2026')
INITIAL_CAPITAL = 100.0
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "SOLUSD", "ETHUSD"]

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

def load_candles(symbol: str) -> List[Candle]:
    # Prioritize 5m data for hyper-scalping
    filepath_5m = os.path.join(DATA_DIR, 'forex_backtest', f'{symbol}_5m.json')
    filepath_15m = os.path.join(DATA_DIR, f'{symbol}_15m.json')
    
    filepath = filepath_5m if os.path.exists(filepath_5m) else filepath_15m
    
    if not os.path.exists(filepath):
        # Final fallback to standard data dir
        filepath = os.path.join(DATA_DIR, 'jan_2026', f'{symbol}_15m.json')
        if not os.path.exists(filepath):
            return []
    
    # print(f"  [DATA-LOAD] Loading {filepath}")
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
    is_commodity = any(x in symbol for x in ["XAU", "XAG", "BTC", "ETH", "SOL"])
    if is_commodity:
        pnl = price_diff * units
        if abs(pnl) > 0.01: print(f"  [PNL-DEBUG] {symbol} {direction} diff={price_diff:.4f} units={units:.4f} -> PnL=${pnl:.4f}")
        return pnl
    elif "JPY" in symbol:
        return (price_diff * 100) * 0.065 * (units / 1000.0)
    else:
        return (price_diff * 10000) * 0.10 * (units / 1000.0)

def run_robot_backtest():
    os.environ['PROFILE_NAME'] = 'forex_intraday'
    UserConfig.COMBAT_MODE_ENABLED = True
    UserConfig.ROBO_CHOP_SCALP_ENABLED = True
    UserConfig.RUNNER_GRACE_ENABLED = True
    
    settings = load_settings()
    profile = settings.get_active_profile()
    
    all_candles = {}
    for symbol in SYMBOLS:
        candles = load_candles(symbol)
        if candles:
            all_candles[symbol] = candles
            
    if not all_candles:
        print("No data found!")
        return

    capital = INITIAL_CAPITAL
    positions = {} # symbol -> {pos_dict}
    completed_trades = []
    
    all_times = sorted(set(c.timestamp for candles in all_candles.values() for c in candles))
    
    # Init engines for each symbol
    engines = {
        symbol: StrategyEngine(None, None, profile, symbol)
        for symbol in all_candles.keys()
    }

    print(f"Starting Backtest: {all_times[0]} to {all_times[-1]}")
    
    for current_time in all_times:
        for symbol, candles in all_candles.items():
            bar_idx = next((j for j, c in enumerate(candles) if c.timestamp == current_time), None)
            if bar_idx is None or bar_idx < 100: continue
            
            lookback = candles[max(0, bar_idx-150):bar_idx+1]
            engine = engines[symbol]
            
            # Build Snapshot
            trend_htf = infer_trend_from_swings(lookback[-60:], window=12)
            trend_ltf = infer_trend_from_swings(lookback[-30:], window=8)
            
            snapshot = MarketSnapshot(
                symbol=symbol,
                timeframe="15m",
                candles=lookback,
                trend_htf=trend_htf,
                trend_ltf=trend_ltf,
                htf_candles=lookback[-60:],
                ltf_candles=lookback[-30:]
            )
            
            open_pos = positions.get(symbol)
            
            if open_pos:
                # Update unrealized pnl for engine BEFORE decision
                open_pos['unrealized_pnl'] = calculate_pnl(open_pos['entry_price'], lookback[-1].close, open_pos['size'], open_pos['direction'], symbol)
                
            decision = engine.decide("15m", open_position=open_pos, snapshot=snapshot)
            
            if decision.action == "close_position" and open_pos:
                pnl = calculate_pnl(open_pos['entry_price'], lookback[-1].close, open_pos['size'], open_pos['direction'], symbol)
                capital += pnl
                completed_trades.append(Trade(
                    symbol, open_pos['direction'], open_pos['entry_price'], 
                    lookback[-1].close, open_pos['size'], open_pos['entry_time'], 
                    current_time, pnl, decision.structure_summary
                ))
                positions.pop(symbol)
                # print(f"[EXIT] {symbol} {decision.structure_summary} PnL={pnl:.2f}")
                
            elif decision.action in ["enter_long", "enter_short"] and not open_pos:
                direction = "long" if decision.action == "enter_long" else "short"
                
                # [DYNAMIC-RISK] Use UserConfig risk settings for aggressive growth
                if getattr(UserConfig, "COMPOUND_PROFITS", False):
                    risk_amt = capital * UserConfig.BASE_RISK_PCT
                else:
                    # Default to $1.00 risk if not compounding, to maintain isolate expectancy
                    risk_amt = 1.00
                
                # print(f"  [RISK-DEBUG] Capital: ${capital:.2f} RiskAmt: ${risk_amt:.2f}")
                
                # Get ATR for buffer
                atr = calculate_atr(lookback, period=14) or (lookback[-1].close * 0.001)
                min_stop_dist = atr * 1.5 # Widen minimum stop to 1.5 ATR
                
                # Actual stop distance
                actual_stop_val = decision.stop_loss if (decision.stop_loss and abs(lookback[-1].close - decision.stop_loss) > 0) else (lookback[-1].close * 0.99 if direction == "long" else lookback[-1].close * 1.01)
                raw_stop_dist = abs(lookback[-1].close - actual_stop_val)
                stop_dist = max(raw_stop_dist, min_stop_dist)
                
                if stop_dist > 0:
                    size = risk_amt / stop_dist
                    
                    # CAP LEVERAGE (Max 5x) - Crypto is too volatile for 10x
                    max_size = (capital * 5.0) / lookback[-1].close
                    size = min(size, max_size)
                    
                    # Update stop loss to the effective stop used for sizing
                    if raw_stop_dist < min_stop_dist:
                        adjusted_stop = lookback[-1].close - (min_stop_dist if direction == "long" else -min_stop_dist)
                    else:
                        adjusted_stop = actual_stop_val
                    
                    # [STRICT-EXPECTANCY] Force 2R Target relative to effective stop
                    effective_stop_dist = abs(lookback[-1].close - adjusted_stop)
                    forced_target = lookback[-1].close + (effective_stop_dist * 2.0 if direction == "long" else -effective_stop_dist * 2.0)

                    positions[symbol] = {
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": lookback[-1].close,
                        "size": size,
                        "entry_time": current_time,
                        "unrealized_pnl": 0.0,
                        "stop_loss": adjusted_stop,
                        "target": forced_target, # Ignore engine target
                        "bars_held": 0,
                        "phase": decision.phase
                    }
                    # print(f"  [ENTRY-DEBUG] {symbol} {direction} Ent:{lookback[-1].close:.4f} Stop:{adjusted_stop:.4f} Tgt:{forced_target:.4f}")

            elif open_pos:
                curr_candle = lookback[-1]
                open_pos['bars_held'] = open_pos.get('bars_held', 0) + 1
                bars_held = open_pos['bars_held']
                
                entry_p = open_pos['entry_price']
                curr_p = curr_candle.close
                initial_stop = open_pos.get('initial_stop', open_pos['stop_loss'])
                target = open_pos.get('target')
                if 'initial_stop' not in open_pos:
                    open_pos['initial_stop'] = open_pos['stop_loss']
                    
                direction = open_pos['direction']
                unrealized = open_pos.get('unrealized_pnl', 0.0)
                
                # [EARLY HTF WARNING] DISABLED - Data-driven analysis shows sweep+indication entries
                # often profit from counter-trend moves, so we let them run
                # htf_dir = snapshot.trend_htf.direction
                # if direction == 'long' and htf_dir == TrendDirection.SHORT and unrealized <= 0:
                #     pnl = calculate_pnl(entry_p, curr_p, open_pos['size'], direction, symbol)
                #     capital += pnl
                #     completed_trades.append(Trade(
                #         symbol, direction, entry_p, curr_p, open_pos['size'],
                #         open_pos['entry_time'], current_time, pnl, "EARLY_HTF_CUT"
                #     ))
                #     positions.pop(symbol)
                #     continue
                # elif direction == 'short' and htf_dir == TrendDirection.LONG and unrealized <= 0:
                #     pnl = calculate_pnl(entry_p, curr_p, open_pos['size'], direction, symbol)
                #     capital += pnl
                #     completed_trades.append(Trade(
                #         symbol, direction, entry_p, curr_p, open_pos['size'],
                #         open_pos['entry_time'], current_time, pnl, "EARLY_HTF_CUT"
                #     ))
                #     positions.pop(symbol)
                #     continue
                
                # [FAST SCALP EXIT] Bar-counting based exits (no ATR, no trailing)
                
                # 0. BE STOP: DISABLED - Let profitable trades run to full TARGET
                # Data-driven approach: capture the 2R+ wins instead of exiting at break-even
                # if unrealized > 0 and bars_held >= 2:
                #     if direction == 'long' and entry_p > open_pos['stop_loss']:
                #         open_pos['stop_loss'] = entry_p  # Move to BE
                #     elif direction == 'short' and entry_p < open_pos['stop_loss']:
                #         open_pos['stop_loss'] = entry_p  # Move to BE
                
                # 1. Check for TARGET HIT first (fixed TP)
                if target:
                    if direction == 'long' and curr_candle.high >= target:
                        pnl = calculate_pnl(entry_p, target, open_pos['size'], direction, symbol)
                        print(f"  [RAW-WIN-DEBUG] {symbol} Ent:{entry_p:.4f} Tgt:{target:.4f} Size:{open_pos['size']:.4f} PnL:{pnl:.4f}")
                        capital += pnl
                        completed_trades.append(Trade(
                            symbol, direction, entry_p, target, open_pos['size'],
                            open_pos['entry_time'], current_time, pnl, "TARGET_HIT"
                        ))
                        positions.pop(symbol)
                        continue
                    elif direction == 'short' and curr_candle.low <= target:
                        pnl = calculate_pnl(entry_p, target, open_pos['size'], direction, symbol)
                        print(f"  [RAW-WIN-DEBUG] {symbol} Ent:{entry_p:.4f} Tgt:{target:.4f} Size:{open_pos['size']:.4f} PnL:{pnl:.4f}")
                        capital += pnl
                        completed_trades.append(Trade(
                            symbol, direction, entry_p, target, open_pos['size'],
                            open_pos['entry_time'], current_time, pnl, "TARGET_HIT"
                        ))
                        positions.pop(symbol)
                        continue
                
                # 2. FAST PROFIT TAKE: DISABLED for raw signal validation
                # if bars_held >= 3 and unrealized >= 0.40:
                #     pnl = calculate_pnl(entry_p, curr_p, open_pos['size'], direction, symbol)
                #     capital += pnl
                #     completed_trades.append(Trade(
                #         symbol, direction, entry_p, curr_p, open_pos['size'],
                #         open_pos['entry_time'], current_time, pnl, "FAST_PROFIT"
                #     ))
                #     positions.pop(symbol)
                #     continue
                
                # 3. STAGNATION CUT: DISABLED for raw signal validation
                # if bars_held >= 5 and unrealized <= 0:
                #     pnl = calculate_pnl(entry_p, curr_p, open_pos['size'], direction, symbol)
                #     capital += pnl
                #     completed_trades.append(Trade(
                #         symbol, direction, entry_p, curr_p, open_pos['size'],
                #         open_pos['entry_time'], current_time, pnl, "STAGNATION_CUT"
                #     ))
                #     positions.pop(symbol)
                #     continue
                
                # 4. Check for HARD STOP hit within bar
                is_stoppped = False
                if direction == 'long' and curr_candle.low <= open_pos['stop_loss']:
                    exit_p = open_pos['stop_loss']
                    is_stoppped = True
                elif direction == 'short' and curr_candle.high >= open_pos['stop_loss']:
                    exit_p = open_pos['stop_loss']
                    is_stoppped = True
                
                if is_stoppped:
                    pnl = calculate_pnl(entry_p, exit_p, open_pos['size'], direction, symbol)
                    capital += pnl
                    completed_trades.append(Trade(
                        symbol, direction, entry_p, exit_p, open_pos['size'],
                        open_pos['entry_time'], current_time, pnl, "HARD_STOP"
                    ))
                    positions.pop(symbol)
                    continue

    print("\n--- LAST 5 TRADES ---")
    for t in completed_trades[-5:]:
        print(f"  {t.symbol} {t.direction} {t.entry_time} -> {t.exit_time} | PnL: ${t.pnl:.2f} | Reason: {t.exit_reason}")
    
    print("\n--- ROBOT EVOLUTION BACKTEST RESULTS ---")
    print(f"Initial Capital: ${INITIAL_CAPITAL:.2f}")
    print(f"Final Capital:   ${capital:.2f}")
    print(f"PnL:             ${capital - INITIAL_CAPITAL:.2f} ({(capital/INITIAL_CAPITAL-1)*100:.1f}%)")
    print(f"Total Trades:    {len(completed_trades)}")
    
    winners = sorted([t for t in completed_trades if t.pnl > 0], key=lambda x: x.pnl, reverse=True)
    losers = sorted([t for t in completed_trades if t.pnl <= 0], key=lambda x: x.pnl)
    
    win_pnl = sum(t.pnl for t in winners)
    loss_pnl = abs(sum(t.pnl for t in losers))
    
    print(f"Winners:         {len(winners)}")
    print(f"Losers:          {len(losers)}")
    print(f"Win Rate:        {(len(winners)/len(completed_trades)*100 if completed_trades else 0):.1f}%")
    print(f"Profit Factor:   {(win_pnl / loss_pnl if loss_pnl > 0 else 0):.2f}")
    
    if winners:
        print(f"Avg Win:         ${win_pnl / len(winners):.2f}")
        print(f"Max Win:         ${winners[0].pnl:.2f} ({winners[0].symbol})")
    if losers:
        print(f"Avg Loss:        ${-loss_pnl / len(losers):.2f}")
        print(f"Max Loss:        ${losers[0].pnl:.2f} ({losers[0].symbol})")

    reasons = {}
    for t in completed_trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    print("\nExit Reasons:")
    for r, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  {r:<40}: {count}")

    print("\nTop 5 Winners:")
    for t in winners[:5]:
        print(f"  {t.symbol} {t.direction} {t.entry_time.strftime('%m-%d %H:%M')} -> {t.pnl:.2f} ({t.exit_reason})")
    
    print("\nTop 5 Losers:")
    for t in losers[:5]:
        print(f"  {t.symbol} {t.direction} {t.entry_time.strftime('%m-%d %H:%M')} -> {t.pnl:.2f} ({t.exit_reason})")
    
    if len(winners) >= 80:
        print("\nSUCCESS: Target of 80 winners achieved!")
    else:
        print(f"\nTarget not met: {len(winners)}/80 winners.")

if __name__ == "__main__":
    run_robot_backtest()
