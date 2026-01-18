
import os
import ccxt
import json
from dotenv import load_dotenv

load_dotenv(".env")
exchange = ccxt.coinbase({
    'apiKey': os.getenv("CCXT_API_KEY"),
    'secret': os.getenv("CCXT_SECRET"),
    'options': {'defaultType': 'future'}
})
markets = exchange.load_markets()

print("--- US Futures Affordability Check (~$86 Capital) ---")

targets = ['BTC', 'ETH', 'LTC', 'BCH', 'DOG', 'SHIB', 'SOL']

for t in targets:
    # Find matching US futures
    for symbol, m in markets.items():
        mid = m['id']
        # US Futures ID patterns: BIT-..., ET-..., LTC-..., etc. without PERP-INTX
        if t in symbol and 'USD' in symbol and 'INTX' not in mid and not m.get('spot', True):
            price = m.get('info', {}).get('reference_price_type', '0') # Fallback
            # Fetch ticker for price
            try:
                ticker = exchange.fetch_ticker(symbol)
                last_price = ticker['last']
            except:
                last_price = 0.0
            
            # Coinbase V3 Contract Size info
            # 'contract_size' in info?
            c_size = m.get('contractSize', 1.0)
            
            notional = last_price * c_size
            
            # Estimate Margin (Coinbase US often 50x or 20x for Nanos? conservative 5x?)
            # Let's assume 20% margin (5x) as worst case for calculation
            # or try to read 'max_leverage'
            
            print(f"\nSymbol: {symbol}")
            print(f"ID: {mid}")
            print(f"Price: ${last_price}")
            print(f"Contract Size: {c_size}")
            print(f"Min Notional: ${notional:.2f}")
            print(f"Est. Margin (4% / 25x): ${notional * 0.04:.2f}")
            print(f"Est. Margin (10% / 10x): ${notional * 0.10:.2f}")
            print(f"Est. Margin (20% / 5x): ${notional * 0.20:.2f}")
