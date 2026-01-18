
import ccxt
import os
import sys
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("Protecting ATOMUSD...")
    
    # Init exchange
    exchange = ccxt.coinbase({
        'apiKey': os.getenv('CCXT_API_KEY'),
        'secret': os.getenv('CCXT_SECRET'),
        'enableRateLimit': True,
    })
    
    # Target: Stop at 2.593
    stop_price = 2.593
    symbol = 'ATOM/USD'
    
    # Fetch exact balance
    print("Fetching ATOM balance...")
    bal = exchange.fetch_balance()
    free_atom = bal.get('free', {}).get('ATOM', 0.0)
    print(f"Available ATOM: {free_atom}")
    
    if free_atom < 0.1:
        print("No ATOM to protect!")
        return

    amount = free_atom
    
    # 5% buffer for limit price if stop-limit
    limit_price = stop_price * 0.95 
    
    print(f"Placing Stop Limit for {amount} {symbol} at {stop_price} (Limit {limit_price:.4f})")
    try:
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
