from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend_enums import TrendDirection
from tradebot_sci.strategy.variants.rubberband_reaper import RubberbandReaperStrategy
from tradebot_sci.config.models import UserConfig

DATA_DIR = 'data/forex_backtest'

def load_data(symbol: str, timeframe: str = '5m') -> List[Candle]:
    paths = [
        os.path.join(DATA_DIR, f'{symbol}_{timeframe}.json'),
        os.path.join('data', 'jan_2026', f'{symbol}_15m.json'),
        os.path.join('data', f'{symbol}_15m.json')
    ]
    for filepath in paths:
        if os.path.exists(filepath):
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
            return sorted(candles, key=lambda x: x.timestamp)
    return []


def get_tiered_risk(capital: float) -> float:
    """
    Anti-Martingale Tiered Risk:
    - Below $1,000: 20% risk (aggressive growth)
    - $1,000-$5,000: 10% risk (growth phase)
    - Above $5,000: 1% risk (wealth protection)
    """
    if capital < 1000:
        return 0.20
    elif capital < 5000:
        return 0.10
    else:
        return 0.01


def run_tiered_risk_only():
    """
    Tiered Risk Only (No Floor)
    - 20% risk below $1,000
    - 10% risk $1,000-$5,000
    - 1% risk above $5,000
    """
    symbols = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'NZDUSD']
    
    all_data = {s: load_data(s) for s in symbols}
    all_data = {s: d for s, d in all_data.items() if d}
    if not all_data:
        print("No data found")
        return
    
    capital = 100.0
    initial_capital = 100.0
    peak_capital = 100.0
    positions = {} 
    trades = []
    
    timestamps = sorted(set(c.timestamp for d in all_data.values() for c in d))
    indexed_data = {s: {c.timestamp: c for c in d} for s, d in all_data.items()}
    lookback_buffers = {s: [] for s in all_data.keys()}
    
    strategies = {s: RubberbandReaperStrategy(base_risk_pct=0.20) for s in all_data.keys()}
    
    UserConfig.INFINITE_PYRAMIDING = False
    UserConfig.MAX_PYRAMID_ENTRIES = 0

    for ts in timestamps:
        for symbol in all_data.keys():
            candle = indexed_data[symbol].get(ts)
            if not candle: continue
            
            buffer = lookback_buffers[symbol]
            buffer.append(candle)
            if len(buffer) < 250: continue
            if len(buffer) > 300: buffer.pop(0)
            
            snapshot = MarketSnapshot(symbol=symbol, timeframe="5m", candles=buffer, trend_htf=TrendState(TrendDirection.NEUTRAL, 0), trend_ltf=TrendState(TrendDirection.NEUTRAL, 0))

            pos = positions.get(symbol)
            if pos:
                exit_price = None
                exit_reason = None
                if pos['direction'] == 'long':
                    if candle.low <= pos['stop_loss']: 
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL'
                    elif candle.high >= pos['target']: 
                        exit_price = pos['target']
                        exit_reason = 'TP'
                else:
                    if candle.high >= pos['stop_loss']: 
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL'
                    elif candle.low <= pos['target']: 
                        exit_price = pos['target']
                        exit_reason = 'TP'
                    
                if exit_price:
                    price_diff = (exit_price - pos['entry_price']) if pos['direction'] == 'long' else (pos['entry_price'] - exit_price)
                    pnl = price_diff * pos['size']
                    capital_before = pos['capital_at_entry']
                    capital += pnl
                    
                    if capital > peak_capital:
                        peak_capital = capital
                    
                    trades.append({
                        '#': len(trades) + 1,
                        'symbol': symbol,
                        'direction': pos['direction'].upper(),
                        'capital_before': capital_before,
                        'capital_after': capital,
                        'pnl': pnl,
                        'pnl_pct': (pnl / capital_before) * 100,
                        'peak': peak_capital,
                        'risk_used': pos['risk_used'] * 100,
                        'result': exit_reason,
                    })
                    del positions[symbol]
                    if capital <= 0: 
                        print(f"  *** RUIN at trade #{len(trades)}")
                        break
                    continue

            if symbol not in positions:
                dec = strategies[symbol].check_entry_signal(snapshot, {})
                if dec and dec.action in ['enter_long', 'enter_short']:
                    tiered_risk = get_tiered_risk(capital)
                    risk_amt = capital * tiered_risk
                    stop_dist = abs(candle.close - dec.stop_loss)
                    if stop_dist > 0:
                        size = risk_amt / stop_dist
                        positions[symbol] = {
                            'direction': 'long' if dec.action == 'enter_long' else 'short',
                            'entry_price': candle.close,
                            'stop_loss': dec.stop_loss,
                            'target': dec.take_profit,
                            'size': size,
                            'capital_at_entry': capital,
                            'risk_used': tiered_risk
                        }
    
    print("\n" + "=" * 110)
    print("TIERED RISK ONLY (No Floor) - 20%/10%/1%")
    print("=" * 110)
    print(f"{'#':>3} | {'Symbol':<7} | {'Dir':<5} | {'Cap Before':>10} | {'Cap After':>10} | {'PnL':>10} | {'PnL%':>7} | {'Peak':>10} | {'Risk%':>5} | {'Exit':<4}")
    print("-" * 110)
    
    for t in trades:
        print(f"{t['#']:>3} | {t['symbol']:<7} | {t['direction']:<5} | ${t['capital_before']:>8.2f} | ${t['capital_after']:>8.2f} | ${t['pnl']:>8.2f} | {t['pnl_pct']:>6.1f}% | ${t['peak']:>8.2f} | {t['risk_used']:>4.0f}% | {t['result']:<4}")
    
    print("=" * 110)
    
    wins = len([t for t in trades if t['result'] == 'TP'])
    losses = len([t for t in trades if t['result'] == 'SL'])
    
    print(f"\nSUMMARY:")
    print(f"  Starting Capital:     ${initial_capital:.2f}")
    print(f"  Peak Capital:         ${peak_capital:.2f} (+{(peak_capital/initial_capital - 1)*100:.1f}%)")
    print(f"  Final Capital:        ${capital:.2f} (+{(capital/initial_capital - 1)*100:.1f}%)")
    print(f"  Preserved from Peak:  {(capital/peak_capital)*100:.1f}%")
    print(f"  Total Trades:         {len(trades)} (TP:{wins} SL:{losses})")
    print("=" * 110)

if __name__ == '__main__':
    run_tiered_risk_only()
