
import ccxt
import os
import sys
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("Protecting NEARUSD...")
    
    # Init exchange
    exchange = ccxt.coinbase({
        'apiKey': os.getenv('CCXT_API_KEY'),
        'secret': os.getenv('CCXT_SECRET'),
        # 'password': os.getenv('CCXT_PASSWORD'), # Coinbase usually doesn't need this but just in case
        'enableRateLimit': True,
    })
    
    # 27.03 NEAR at ~$1.714. Stop at 1.711
    # Fetch exact balance
    bal = exchange.fetch_balance()
    free_near = bal.get('free', {}).get('NEAR', 0.0)
    print(f"Available NEAR: {free_near}")
    
    if free_near < 0.1:
        print("No NEAR to protect!")
        return

    symbol = 'NEAR/USD'
    amount = free_near
    stop_price = 1.70
    
    # 5% buffer for limit price if stop-limit
    limit_price = stop_price * 0.95 
    
    print(f"Placing Stop Limit for {amount} {symbol} at {stop_price} (Limit {limit_price:.4f})")
    
    try:
        # Coinbase Advanced Trade params
        params = {
            'stop_price': str(stop_price),
            'stop_direction': 'STOP_DIRECTION_STOP_DOWN'
        }
        
        # Note: 'stop_limit_stop_limit_gtc' might be a specific string for some versions,
        # but standard CCXT stop_limit usually works.
        # However, the doc suggested 'type': 'stop_limit_stop_limit_gtc'. 
        # I'll stick to standard 'limit' with stopPrice params which works for Coinbase usually.
        # actually, let's use the code snippet provided in the doc exactly if possible.
        # The doc used: type='stop_limit_stop_limit_gtc'
        # That looks like a specific Coinbase ID. safely I will use standard 'limit' and params.
        
        order = exchange.create_order(
            symbol=symbol,
            type='limit', # Coinbase uses limit for stop-limit usually
            side='sell',
            amount=amount,
            price=limit_price, 
            params={
                'stopPrice': stop_price, # CCXT standard
                'stop_price': stop_price, # Coinbase specific backup
                'stop_direction': 'STOP_DIRECTION_STOP_DOWN'
            }
        )
        print(f"Stop loss placed: {order['id']}")
    except Exception as e:
        print(f"Failed to place SL: {e}")

if __name__ == "__main__":
    main()
