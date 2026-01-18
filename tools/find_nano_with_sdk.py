
import os
import sys
import logging
from dotenv import load_dotenv

# Setup
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()

try:
    from coinbase.rest import RESTClient
except ImportError:
    print("coinbase-advanced-py not installed.")
    sys.exit(1)

def find_nano():
    print("--- Finding Nano Contracts (Official SDK) ---")
    
    api_key = os.environ.get("CCXT_API_KEY")
    secret = os.environ.get("CCXT_SECRET")
    
    if secret and "\\n" in secret:
        secret = secret.replace("\\n", "\n")

    try:
        client = RESTClient(api_key=api_key, api_secret=secret)
        
        # Method signature: get_products(product_type=None, ...)
        print("Fetching FUTURE products...")
        response = client.get_products(product_type="FUTURE")
        
        # Check response type attributes
        # print(f"Response Object: {response}")
        
        products = getattr(response, 'products', [])
        if not products and hasattr(response, 'to_dict'):
             products = response.to_dict().get('products', [])
             
        print(f"Found {len(products)} Futures Products.")
        
        for p in products:
            # p might be object too
            pid = getattr(p, 'product_id', None) or p.get('product_id')
            price = getattr(p, 'price', None) or p.get('price')
            
            if pid and ("ET" in pid or "BIT" in pid or "NANO" in str(p).upper()):
                print(f"MATCH: {pid} (Price: {price})")
                
    except Exception as e:
        print(f"SDK Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_nano()
