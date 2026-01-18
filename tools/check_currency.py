import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

def check_balance():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if not api_key or not secret:
        print("Error: credentials missing")
        return

    if "\\n" in secret:
        secret = secret.replace("\\n", "\n")

    ex = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'spot'} 
    })
    
    print("Fetching balance...")
    bal = ex.fetch_balance()
    
    # Print non-zero
    found = False
    print("\n--- BALANCES ---")
    for currency, data in bal.items():
        if isinstance(data, dict) and 'free' in data:
            free = data['free']
            if free > 0:
                print(f"{currency}: {free}")
                found = True
        elif currency in ['free', 'used', 'total']:
             # Top level aggregates
             pass
        else:
             # direct value?
             pass
             
    if not found:
        print("No non-zero balances found.")

if __name__ == "__main__":
    check_balance()
