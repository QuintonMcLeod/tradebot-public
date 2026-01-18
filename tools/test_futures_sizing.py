
import os
import sys
import json
import ccxt
from pprint import pprint
from dotenv import load_dotenv

def test_futures_sizing_direct():
    load_dotenv()
    print("--- START FUTURES SIZING TEST (DIRECT CCXT) ---")
    
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if not api_key or not secret:
        print("Error: Missing credentials in .env")
        return

    # Handle escaped newlines in secret
    if secret and "\\n" in secret and "\n" not in secret:
        print("Normalizing secret key...")
        secret = secret.replace("\\n", "\n")

    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'},
    })
    
    try:
        # Load Markets
        print("Loading markets...")
        markets = exchange.load_markets()
        
        # Search for our target future
        target_alias = "XRP/USD:USD-301220"
        
        # 1. Find the raw Product ID from V3
        print("Fetching V3 Products to confirm ID...")
        # V3 endpoint: GET /api/v3/brokerage/products
        # CCXT Implicit: v3_private_get_brokerage_products
        
        # We'll valid candidates
        candidates = []
        try:
             products = exchange.v3_private_get_brokerage_products({'product_type': 'FUTURE'})
             # The response has a 'products' key usually
             ps = products.get('products', [])
             for p in ps:
                 pid = p['product_id']
                 if "XRP" in pid and "USD" in pid:
                     candidates.append(pid)
                     print(f"Found Candidate: {pid} (Status: {p.get('status')})")
        except Exception as e:
            print(f"Failed to list V3 products: {e}")
            
        # Pick one to test
        if not candidates:
            print("No matching V3 products found! Using 'ETP-20DEC30-CDE' (Nano ETH) as backup.")
            test_symbol = "ETP-20DEC30-CDE"
        else:
            # Prefer the one that looks like our target
            # Our target in log was XRP/USD:USD-301220. The actual product_id might be "XRP-USD-301220" (dash not colon?)
            # or it might be the same.
            test_symbol = candidates[0] # Pick first one
            print(f"Selected Test Symbol: {test_symbol}")

        # 2. Check Price
        print(f"Fetching ticker for {test_symbol}...")
        try:
             # Fetch ticker might fail if mapped incorrectly in CCXT, so loop markets to find symbol
             # Actually, for V3 Preview, we just need the product_id string.
             # But to print price we need to fetch ticker.
             # Let's try fetching by product_id directly if possible
             ticker = exchange.fetch_ticker(test_symbol)
             price = float(ticker['last'])
             print(f"Price: {price}")
        except:
             print("Ticker fetch via CCXT failed (symbol mapping issue?), assuming $2.00 price.")
             price = 2.0

        # 3. Test Preview
        
        # Test Case A: Quote Size (USD Amount)
        print(f"\n--- TEST CASE A: Quote Size $20 (Expected ~10 contracts) for {test_symbol} ---")
        try:
            req_a = {
                "product_id": test_symbol,
                "side": "BUY",
                "order_configuration": {
                    "market_market_ioc": {
                        "quote_size": "20" 
                    }
                }
            }
            res_a = exchange.v3_private_post_brokerage_orders_preview(req_a)
            print("Case A Result: SUCCESS (Quote Size Accepted)")
            print(json.dumps(res_a, indent=2))
        except Exception as e:
            print(f"Case A Result: FAILED (Quote Size Rejected) - {e}")

        # Test Case B: Base Size (Contract Amount)
        print(f"\n--- TEST CASE B: Base Size 5 Contracts for {test_symbol} ---")
        try:
            req_b = {
                "product_id": test_symbol,
                "side": "BUY",
                "order_configuration": {
                    "market_market_ioc": {
                        "base_size": "5"
                    }
                }
            }
            res_b = exchange.v3_private_post_brokerage_orders_preview(req_b)
            print("Case B Result: SUCCESS (Base Size Accepted)")
            print(json.dumps(res_b, indent=2))
        except Exception as e:
             print(f"Case B Result: FAILED (Base Size Rejected) - {e}")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_futures_sizing_direct()
