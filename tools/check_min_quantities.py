
import os
import ccxt
import json
from dotenv import load_dotenv

load_dotenv(".env")
exchange = ccxt.coinbase({
    'apiKey': os.getenv("CCXT_API_KEY"),
    'secret': os.getenv("CCXT_SECRET"),
    'options': {'defaultType': 'future'}
})

def check_limits():
    print(f"\n--- Checking Minimum Trade Sizes (Precision) ---")
    print(f"{'SYMBOL':<20} {'ID':<20} {'MIN AMOUNT':<10} {'NOTIONAL':<10}")
    print("-" * 70)
    
    targets = ['AVAX', 'SHIB', 'ETH', 'ADA', 'LINK'] # Added LINK to verify the error
    
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"Error: {e}")
        return

    for symbol, m in markets.items():
        mid = m['id']
        is_target = False
        for t in targets:
            if t in mid and 'CDE' in mid:
                is_target = True
                break
        
        if is_target:
            limits = m.get('limits', {})
            amount_limits = limits.get('amount', {})
            min_amt = amount_limits.get('min')
            
            try:
                # Get notional for context
                info = m.get('info', {})
                settle_price = float(info.get('settlement_price', 0))
                if settle_price == 0:
                     try:
                        tk = exchange.fetch_ticker(symbol)
                        settle_price = tk['last']
                     except: pass
                
                c_size = float(m.get('contractSize', 1.0))
                notional = settle_price * c_size
                
                print(f"{symbol:<20} {mid:<20} {min_amt:<10} ${notional:<10.2f}")
            except Exception as e:
                print(f"{symbol:<20} Error: {e}")

if __name__ == "__main__":
    check_limits()
