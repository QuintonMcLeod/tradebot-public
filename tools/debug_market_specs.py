
import os
import sys
import json
import ccxt
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), "src"))
load_dotenv()

def main():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })
    
    print("Loading markets...")
    markets = exchange.load_markets()
    
    symbols_to_check = [
        "AVAX/USD:USD-260130",
        "BTC/USD:USD-260130",
        "ETH/USD:USD-260130", 
        "LTC/USD:USD-260130",
        "SHIB/USD:USD-260130"
    ]
    
    print("\n--- CONTRACT SPECS ---")
    for sym in symbols_to_check:
        if sym in markets:
            m = markets[sym]
            print(f"\nSymbol: {sym}")
            print(f"  Contract Size: {m.get('contractSize')}")
            print(f"  Spot/Future: {m.get('type')}")
            print(f"  Box Info: {m.get('info', {}).get('default_leverage')}") # Guessing key
            
            # Dump a bit of info to find margin requirements
            print(f"  Limits: {json.dumps(m.get('limits'), indent=2)}")
            # print(f"  Info Keys: {list(m.get('info', {}).keys())}")
            
            # Try to calculate Notional for $1 Price
            # Cost = Price * ContractSize
            
        else:
            print(f"\nSymbol {sym} NOT FOUND in markets.")

if __name__ == "__main__":
    main()
