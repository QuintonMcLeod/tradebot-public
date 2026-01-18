
import os
import sys
import json
import ccxt
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

load_dotenv()

def main():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    # Init Coinbase (Futures/Advanced Trade)
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'} # Check in future mode since that's where we trade
    })
    
    print("Fetching ALL accounts...")
    try:
        # Try fetch_accounts first (often more reliable for Coinbase Advanced)
        accounts = exchange.fetch_accounts()
        print(f"\nFound {len(accounts)} accounts.")
        for acc in accounts:
            if float(acc.get('info', {}).get('available_balance', {}).get('value', 0) or 0) > 0:
                 print(json.dumps(acc, indent=2))
                 
        print("\nFetching Balance (params={'type': 'spot'})...")
        # Try spot explicitly
        bal_spot = exchange.fetch_balance({'type': 'spot'})
        print("Free Spot:", bal_spot.get('free', {}))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
