import os
import sys
import json
import ccxt

def main():
    exchange_id = 'coinbase'
    print(f"Connecting to {exchange_id}...")
    exchange = getattr(ccxt, exchange_id)({
        'apiKey': os.getenv('CCXT_API_KEY'),
        'secret': os.getenv('CCXT_SECRET'),
        'password': os.getenv('CCXT_PASSWORD'),
    })
    
    print("Loading markets...")
    exchange.load_markets()
    
    symbol = "DOGE/USDT"
    if symbol in exchange.markets:
        market = exchange.market(symbol)
        print(f"\n--- Market Info for {symbol} ---")
        limits = market.get('limits', {})
        print(f"Limits: {json.dumps(limits, indent=2)}")
        
        min_amount = limits.get('amount', {}).get('min')
        print(f"\nExtracted min_amount: {min_amount}")
    else:
        print(f"Symbol {symbol} not found in markets.")
        # print keys
        # print(list(exchange.markets.keys()))

if __name__ == "__main__":
    main()
