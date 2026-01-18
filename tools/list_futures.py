
import os
import ccxt
import time
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

def list_futures():
    api_key = os.getenv("CCXT_API_KEY")
    api_secret = os.getenv("CCXT_SECRET")
    
    # [ANTIGRAVITY FIX] Handle escaped newlines
    if api_secret and "\\n" in api_secret and "\n" not in api_secret:
        print("[INFO] Normalizing API secret...")
        api_secret = api_secret.replace("\\n", "\n")

    print("[INFO] Connecting to Coinbase Futures...")
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    try:
        markets = exchange.load_markets()
        print(f"[INFO] Loaded {len(markets)} markets.")
        
        futures = []
        for symbol, market in markets.items():
            # Filter for futures/derivatives
            # Coinbase sometimes marks them as 'swap' or 'future'
            m_type = market.get('type')
            if m_type in ['future', 'swap', 'derivative']:
                settings = {
                    'symbol': symbol,
                    'id': market.get('id'),
                    'contractSize': market.get('contractSize', 1.0),
                    'min_amount': market.get('limits', {}).get('amount', {}).get('min'),
                    'price': 0.0
                }
                futures.append(settings)
        
        print(f"[INFO] Found {len(futures)} futures markets. Fetching prices...")
        
        # Fetch tickers to get current prices for cost estimation
        # This might fail if too many, so we'll try to fetch all or in batches
        try:
            tickers = exchange.fetch_tickers([f['symbol'] for f in futures])
        except:
            tickers = {} # Fallback
            
        affordable = []
        expensive = []
        
        print(f"{'SYMBOL':<25} | {'SIZE':<10} | {'PRICE':<10} | {'MIN COST':<10}")
        print("-" * 65)
        
        for f in futures:
            sym = f['symbol']
            ticker = tickers.get(sym)
            price = ticker['last'] if ticker else 0.0
            f['price'] = price
            
            # Calculate Min Cost
            # Cost = Price * ContractSize * MinAmount
            # Many CDE contracts have multiplier in contractSize (e.g. 0.1 ETH)
            # And min amount usually 1
            min_amt = float(f['min_amount']) if f['min_amount'] is not None else 1.0
            
            # Handle None in contractSize
            c_size = float(f['contractSize']) if f['contractSize'] is not None else 1.0
            price = float(price) if price is not None else 0.0
            
            cost = price * c_size * min_amt
            
            f['cost'] = cost
            
            row = f"{sym:<25} | {f['contractSize']:<10} | {price:<10.4f} | ${cost:<10.2f}"
            
            if cost > 0 and cost < 80.0: # Check if fits in $86 budget (with buffer)
                affordable.append(row)
            else:
                expensive.append(row)

        print("\n=== AFFORDABLE (< $80) ===")
        for r in affordable:
            print(r)
            
        print("\n=== EXPENSIVE (> $80) ===")
        for r in expensive:
            print(r)

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    list_futures()
