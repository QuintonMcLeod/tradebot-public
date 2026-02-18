
import os
import sys
import json
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv(".env")

def debug_permissions():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if not api_key or not secret:
        print("Error: Missing credentials in .env")
        return

    print(f"DEBUG: Using Key ID: {api_key}")
    
    # Initialize Coinbase (V3)
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })

    try:
        # Fetch Balance (Raw)
        print("\n--- Fetching Default Balance (RAW) ---")
        balance = exchange.fetch_balance()
        # Print keys to see structure
        print(f"Keys: {list(balance.keys())}")
        if 'total' in balance:
             print(f"Total: {balance['total']}")
        
        # Check specific known assets
        for currency in ['USD', 'USDC', 'BTC', 'ETH']:
            if currency in balance:
                print(f"{currency}: {balance[currency]}")
            elif 'total' in balance and currency in balance['total']:
                 print(f"{currency} (in total): {balance['total'][currency]}")
            else:
                 print(f"{currency}: Not found in balance keys")

    except Exception as e:
        print(f"FETCH BALANCE FAILED: {e}")

if __name__ == "__main__":
    debug_permissions()
