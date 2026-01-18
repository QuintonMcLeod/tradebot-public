
import os
import sys
import json
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv(".env")

def list_allowed_markets():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })

    try:
        print("--- Fetching Markets (US Key Context) ---")
        markets = exchange.load_markets()
        print(f"Total Markets Loaded: {len(markets)}")
        
        futures = []
        for symbol, market in markets.items():
            # Check for 'future' type or typical usage
             m_type = market.get('type')
             m_spot = market.get('spot')
             m_id = market.get('id')
             
             if m_type == 'future' or not m_spot:
                 futures.append(f"{symbol} (ID: {m_id})")

        print(f"\n--- Futures / Non-Spot Markets ({len(futures)}) ---")
        for f in sorted(futures):
            print(f)
            
        print("\n--- 'Nano' Specific Search ---")
        nanos = [m for m in markets.keys() if 'BIT' in m or 'ET' in m]
        for n in sorted(nanos):
             print(f"{n} : {markets[n]['id']}")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    list_allowed_markets()
