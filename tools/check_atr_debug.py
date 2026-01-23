import json
import os
import sys

sys.path.insert(0, '/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src')
from tradebot_sci.market.models import Candle

DATA_FILE = '/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/data/jan_2026/SOLUSD_15m.json'
with open(DATA_FILE, 'r') as f:
    data = json.load(f)

candles = []
for bar in data[:100]:
    candles.append(Candle(
        timestamp=bar['timestamp'],
        open=float(bar['open']),
        high=float(bar['high']),
        low=float(bar['low']),
        close=float(bar['close']),
        volume=float(bar.get('volume', 0))
    ))

from tradebot_sci.strategy.icc_signals import calculate_atr
atr = calculate_atr(candles, period=14)
print(f"SOLUSD ATR (14): {atr}")
print(f"Sample price: {candles[-1].close}")
