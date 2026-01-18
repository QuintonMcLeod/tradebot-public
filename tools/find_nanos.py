
import os
import sys
import json
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv(".env")

def find_nanos():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })

    try:
        print("--- Finding Nano Futures (US) ---")
        markets = exchange.load_markets()
        
        # Look for BIT (Bitcoin) and ET (Ether) contracts
        candidates = []
        for symbol, market in markets.items():
            mid = market['id']
            # US Nano Futures usually start with BIT or ET
            if mid.startswith('BIT') or mid.startswith('ET') or 'NANO' in mid:
                 candidates.append((symbol, mid, market.get('expiryDatetime', 'N/A')))
            # Also check for other regulated assets
            if mid.startswith('LTC') and 'USD' in mid and '-' in mid and 'PERP' not in mid:
                  candidates.append((symbol, mid, market.get('expiryDatetime', 'N/A')))

        print(f"Found {len(candidates)} candidates:")
        for sym, mid, exp in sorted(candidates, key=lambda x: x[1]):
            print(f"Symbol: {sym} | ID: {mid} | Exp: {exp}")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    find_nanos()
