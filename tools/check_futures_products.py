
import os
import sys
import json
import logging
import asyncio

# Check if ccxt is installed
try:
    import ccxt.async_support as ccxt
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    print("CCXT or dotenv not installed.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(message)s')
logger = logging.getLogger()

async def check():
    print("--- Checking Futures Products ---")
    
    api_key = os.environ.get("CCXT_API_KEY")
    secret = os.environ.get("CCXT_SECRET")
    
    # Fix escaped newlines
    if secret and '\\n' in secret:
        secret = secret.replace('\\n', '\n')

    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
    })
    
    try:
        # Load standard markets first (debug)
        # await exchange.load_markets()
        
        # Try raw request to products endpoint with filter
        # /api/v3/brokerage/products?product_type=FUTURE
        print("Requesting /api/v3/brokerage/products?product_type=FUTURE ...")
        
        if hasattr(exchange, 'publicGetBrokerageProducts'):
            response = await exchange.publicGetBrokerageProducts({'product_type': 'FUTURE'})
            products = response.get('products', [])
            print(f"Found {len(products)} FUTURES products.")
            
            for p in products:
                # Print relevant details
                pid = p.get('product_id')
                alias = p.get('alias')
                status = p.get('status')
                print(f" - {pid} (Alias: {alias}) [{status}]")
                
                # Check for Nano
                if "ET" in pid or "ETH" in pid or "NANO" in str(p).upper():
                     print(f"   *** MATCH: {p} ***")
        else:
            print("Method publicGetBrokerageProducts not found.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check())
