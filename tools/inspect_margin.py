
import os
import ccxt
import json
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

def inspect_margin():
    api_key = os.getenv("CCXT_API_KEY")
    api_secret = os.getenv("CCXT_SECRET")
    
    # [ANTIGRAVITY FIX] Handle escaped newlines
    if api_secret and "\\n" in api_secret and "\n" not in api_secret:
        api_secret = api_secret.replace("\\n", "\n")

    print("[INFO] Connecting to Coinbase Futures...")
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    try:
        markets = exchange.load_markets()
        
        targets = [
            "SHIB/USD:USD-301220", 
            "LTC/USD:USD-301220", 
            "AVAX/USD:USD-301220", 
            "DOT/USD:USD-301220"
        ]
        
        for target in targets:
            if target in markets:
                m = markets[target]
                print(f"--- {target} ---")
                info = m.get("info", {})
                future_details = info.get("future_product_details", {})
                margin_rates = future_details.get("intraday_margin_rate", {})
                
                print(f"Notional Size: {m.get('contractSize')}")
                print(f"Price: {info.get('price')}")
                print(f"Margin Rate: {margin_rates}")
                
            else:
                print(f"[ERROR] Target {target} not found.")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    inspect_margin()
