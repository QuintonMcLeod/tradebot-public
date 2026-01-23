
import os
import ccxt
from dotenv import load_dotenv

# Load .env
load_dotenv()

def test_coinbase():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    # Normalize secret (escaped newlines)
    if secret and "\\n" in secret:
        secret = secret.replace("\\n", "\n")
        
    print(f"API Key: {api_key[:15]}...")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {
            'createMarketBuyOrderRequiresPrice': False,
        }
    })
    
    try:
        balance = exchange.fetch_balance()
        print("Successfully connected to Coinbase!")
        # Print a few non-zero balances
        total = balance.get('total', {})
        for curr, amt in total.items():
            if float(amt or 0) > 0:
                print(f"  {curr}: {amt}")
    except Exception as e:
        print(f"Failed to connect to Coinbase: {e}")

if __name__ == "__main__":
    test_coinbase()
