import os
import json
import math
from pathlib import Path

def ema(data, period):
    k = 2 / (period + 1)
    emas = [data[0]]
    for p in data[1:]:
        emas.append((p * k) + (emas[-1] * (1 - k)))
    return emas

def atr(candles, period=14):
    true_ranges = [candles[0]['high'] - candles[0]['low']]
    for i in range(1, len(candles)):
        h, l, pc = candles[i]['high'], candles[i]['low'], candles[i-1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
    # Simple rolling average
    res = [0] * period
    for i in range(period, len(candles)):
        res.append(sum(true_ranges[i-period:i]) / period)
    return res

def sma_std(data, period=20):
    smas = [0] * period
    stds = [0] * period
    for i in range(period, len(data)):
        window = data[i-period:i]
        mean = sum(window) / period
        smas.append(mean)
        variance = sum((x - mean) ** 2 for x in window) / period
        stds.append(math.sqrt(variance))
    return smas, stds

def analyze_london_sweep(candles):
    trades = []
    # Group by day
    # Assuming 'time' is a timestamp in ms
    days = {}
    for i, c in enumerate(candles):
        from datetime import datetime
        dt = datetime.fromisoformat(c['timestamp'])
        day_str = dt.strftime('%Y-%m-%d')
        days.setdefault(day_str, []).append((i, c, dt))
        
    for day_str, daily_candles in days.items():
        asian = [x for x in daily_candles if 0 <= x[2].hour < 7]
        london = [x for x in daily_candles if 7 <= x[2].hour < 12]
        if not asian or not london: continue
        
        asian_high = max(x[1]['high'] for x in asian)
        asian_low = min(x[1]['low'] for x in asian)
        
        for i, c, dt in london:
            # Bearish sweep
            if c['high'] > asian_high and c['close'] < asian_high:
                entry = c['close']
                sl = c['high'] + (c['atr'] * 0.1)
                risk = abs(entry - sl)
                if risk == 0: continue
                
                # Forward simulation
                max_profit = 0
                for j in range(i+1, min(i+96, len(candles))):
                    future = candles[j]
                    if future['high'] >= sl: break # Stopped out
                    profit = entry - future['low']
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Sweep Short', 'r': max_profit/risk if risk else 0})
                break
            
            # Bullish sweep
            if c['low'] < asian_low and c['close'] > asian_low:
                entry = c['close']
                sl = c['low'] - (c['atr'] * 0.1)
                risk = abs(entry - sl)
                if risk == 0: continue
                
                max_profit = 0
                for j in range(i+1, min(i+96, len(candles))):
                    future = candles[j]
                    if future['low'] <= sl: break # Stopped out
                    profit = future['high'] - entry
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Sweep Long', 'r': max_profit/risk if risk else 0})
                break
    return trades

def analyze_squeeze_breakout(candles):
    trades = []
    widths = [c['bb_up'] - c['bb_dn'] for c in candles[20:]]
    if not widths: return trades
    widths.sort()
    threshold = widths[int(len(widths) * 0.20)]
    
    in_squeeze = False
    for i in range(21, len(candles)-1):
        c = candles[i]
        pc = candles[i-1]
        width = c['bb_up'] - c['bb_dn']
        if width < threshold:
            in_squeeze = True
        elif in_squeeze and width > threshold:
            in_squeeze = False
            
            is_bullish = c['close'] > c['sma20']
            entry = c['close']
            
            if is_bullish:
                sl = c['sma20'] - (c['atr'] * 0.5)
                risk = entry - sl
                if risk <= 0: continue
                max_profit = 0
                for j in range(i+1, min(i+40, len(candles))):
                    future = candles[j]
                    if future['low'] <= sl: break
                    profit = future['high'] - entry
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Squeeze Long', 'r': max_profit/risk})
            else:
                sl = c['sma20'] + (c['atr'] * 0.5)
                risk = sl - entry
                if risk <= 0: continue
                max_profit = 0
                for j in range(i+1, min(i+40, len(candles))):
                    future = candles[j]
                    if future['high'] >= sl: break
                    profit = entry - future['low']
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Squeeze Short', 'r': max_profit/risk})
    return trades


def analyze_ema_pullback(candles):
    trades = []
    for i in range(55, len(candles)-1):
        c = candles[i]
        pc = candles[i-1]
        
        trend_up = c['ema21'] > c['ema55']
        trend_dn = c['ema21'] < c['ema55']
        
        if trend_up:
            if pc['low'] > pc['ema55'] and c['low'] <= c['ema55'] and c['close'] > c['ema55']:
                entry = c['close']
                sl = c['low'] - (c['atr'] * 0.2)
                risk = entry - sl
                if risk <= 0: continue
                
                max_profit = 0
                for j in range(i+1, min(i+40, len(candles))):
                    future = candles[j]
                    if future['low'] <= sl: break
                    profit = future['high'] - entry
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Pullback Long', 'r': max_profit/risk})
                
        elif trend_dn:
            if pc['high'] < pc['ema55'] and c['high'] >= c['ema55'] and c['close'] < c['ema55']:
                entry = c['close']
                sl = c['high'] + (c['atr'] * 0.2)
                risk = sl - entry
                if risk <= 0: continue
                
                max_profit = 0
                for j in range(i+1, min(i+40, len(candles))):
                    future = candles[j]
                    if future['high'] >= sl: break
                    profit = entry - future['low']
                    if profit > max_profit: max_profit = profit
                trades.append({'strat': 'Pullback Short', 'r': max_profit/risk})
    return trades

def main():
    data_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tradebot-sci" / "data" / "oanda_14day"
    
    all_trades = []
    
    for f in data_dir.glob("*_15m.json"):
        sym = f.stem.split("_")[0]
        with open(f) as fh:
            raw = json.load(fh)
            
        closes = [c['close'] for c in raw]
        ema21 = ema(closes, 21)
        ema55 = ema(closes, 55)
        sma20, std20 = sma_std(closes, 20)
        atrs = atr(raw, 14)
        
        for i in range(len(raw)):
            raw[i]['ema21'] = ema21[i]
            raw[i]['ema55'] = ema55[i]
            raw[i]['sma20'] = sma20[i]
            raw[i]['bb_up'] = sma20[i] + (std20[i] * 2)
            raw[i]['bb_dn'] = sma20[i] - (std20[i] * 2)
            raw[i]['atr'] = atrs[i]
            
        all_trades.extend(analyze_london_sweep(raw))
        all_trades.extend(analyze_squeeze_breakout(raw))
        all_trades.extend(analyze_ema_pullback(raw))
        
    def print_stats(name, filter_str):
        filtered = [t for t in all_trades if filter_str in t['strat']]
        if not filtered: return
        total = len(filtered)
        hits_2_4 = sum(1 for t in filtered if t['r'] >= 2.4)
        avg_r = sum(t['r'] for t in filtered) / total
        print(f"\n--- {name} ---")
        print(f"Total entries: {total}")
        print(f"Entries hitting 2.4R before SL: {hits_2_4} ({hits_2_4/total*100:.1f}%)")
        print(f"Average Potential R: {avg_r:.2f}")
        
    print_stats("London Liquidity Sweep", "Sweep")
    print_stats("Bollinger Squeeze", "Squeeze")
    print_stats("EMA Deep Pullback", "Pullback")

if __name__ == "__main__":
    main()
