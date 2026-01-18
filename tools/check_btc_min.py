
import os
import ccxt
import json
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

def check_btc():
    api_key = os.getenv("CCXT_API_KEY")
    api_secret = os.getenv("CCXT_SECRET")

    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    print("Fetching markets...")
    markets = exchange.load_markets()
    
    target = "BTC/USD:USD-301220" # From logs: BIP-20DEC30-CDE mapped to this? Or vice versa.
    # The error message said: coinbase amount of BTC/USD:USD-301220 must be greater than minimum amount precision of 1
    
    if target in markets:
        m = markets[target]
        print(f"--- {target} ---")
        print(f"Type: {m.get('type')}")
        print(f"Contract Size: {m.get('contractSize')}")
        print(f"Precision (Amount): {m.get('precision', {}).get('amount')}")
        print(f"Min Amount (Limits): {m.get('limits', {}).get('amount', {}).get('min')}")
        print(f"Min Cost (Limits): {m.get('limits', {}).get('cost', {}).get('min')}")
        
        c_size = m.get('contractSize', 1.0)
        price = 95380.0 # Approx from logs
        cost_1_contract = c_size * price
        print(f"Estimated Cost of 1 Contract: ${cost_1_contract:.2f}")
    else:
        print(f"Symbol {target} not found in markets.")
        # Print all BTC symbols
        print("Available BTC symbols:")
        for s in markets:
            if "BTC" in s:
                print(s)

if __name__ == "__main__":
    check_btc()
