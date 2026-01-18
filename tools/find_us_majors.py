
import os
import ccxt
from dotenv import load_dotenv

load_dotenv(".env")
exchange = ccxt.coinbase({
    'apiKey': os.getenv("CCXT_API_KEY"),
    'secret': os.getenv("CCXT_SECRET"),
    'options': {'defaultType': 'future'}
})
markets = exchange.load_markets()
print("--- Bitcoin Nano Candidates ---")
for k, v in markets.items():
    if 'BTC' in k and 'USD' in k and 'PERP' not in v['id']:
        print(f"Symbol: {k} | ID: {v['id']} | Spot: {v.get('spot')}")
print("--- Ether Nano Candidates ---")
for k, v in markets.items():
    if 'ETH' in k and 'USD' in k and 'PERP' not in v['id']:
        print(f"Symbol: {k} | ID: {v['id']} | Spot: {v.get('spot')}")
