import ccxt
import os
from dotenv import load_dotenv

def verify():
    load_dotenv()
    print("Checking Coinbase Balance...")
    
    api_key = os.getenv('CCXT_API_KEY')
    secret = os.getenv('CCXT_SECRET')
    
    if not api_key or not secret:
        print("Error: credentials not found in environment.")
        # Try loading from local .env explicitly if needed
        # load_dotenv("path/to/.env")
        return

    print(f"API Key loaded: {api_key[:4]}***")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
    })
    
    try:
        balance = exchange.fetch_balance()
        usd_free = balance.get('free', {}).get('USD', 0)
        print(f"Available USD: ${usd_free}")
        
        # Check Nano Ether
        symbol = 'ETH/USD:USD-301220'
        markets = exchange.load_markets()
        if symbol in markets:
            market = markets[symbol]
            print(f"Market limits for {symbol}: {market.get('limits')}")
        else:
            print(f"Symbol {symbol} not found in markets.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()
