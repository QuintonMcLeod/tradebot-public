
import ccxt
import os
import json
from dotenv import load_dotenv

def main():
    load_dotenv()
    exchange = ccxt.coinbase({
        'apiKey': os.getenv('CCXT_API_KEY'),
        'secret': os.getenv('CCXT_SECRET'),
        'enableRateLimit': True,
    })

    # Fetch all current positions
    print("Fetching balances...")
    positions = exchange.fetch_balance()
    
    # Fetch all open orders to see which have stop losses
    print("Fetching open orders...")
    open_orders = exchange.fetch_open_orders()
    
    symbols_with_stops = set()
    for order in open_orders:
        # Check for stop trigger info in various fields
        has_stop = False
        if order.get('type') in ('stop', 'stop_limit', 'stop_market'):
            has_stop = True
        elif 'stop_price' in order.get('info', {}) or 'stop_price' in order:
            has_stop = True
        elif order.get('info', {}).get('order_configuration', {}).get('stop_limit_stop_limit_gtc'):
            has_stop = True
            
        if has_stop:
            symbols_with_stops.add(order['symbol'])
            print(f"✓ {order['symbol']} already has stop loss ({order['id']})")

    # Defined Configs from Report
    STOP_LOSS_CONFIGS = {
        'SOL/USD': {
            'entry': 139.33,
            'stop_price': 139.23,
        },
        'ATOM/USD': {
            'entry': 2.606,
            'stop_price': 2.593,
        },
        'NEAR/USD': {
            'entry': 1.70, # Approximate
            'stop_price': 1.60,
        }
    }

    protected_count = 0

    for symbol, config in STOP_LOSS_CONFIGS.items():
        if symbol in symbols_with_stops:
            print(f"Skipping {symbol} - already protected")
            continue

        base_currency = symbol.split('/')[0]
        balance = positions.get('free', {}).get(base_currency, 0.0)
        
        if balance < 0.001: # Ignore empty/dust
            # check total just in case locked? No, we need free to separate STOP order usually
            # actually if we only have position and NO open orders, it should be free.
            print(f"Skipping {symbol} - no 'free' balance ({balance} {base_currency})")
            continue

        print(f"\n⚠️ UNPROTECTED POSITION FOUND: {symbol}")
        print(f"   Balance: {balance} {base_currency}")
        print(f"   Target Stop: ${config['stop_price']}")

        try:
            stop_price = float(config['stop_price'])
            limit_price = stop_price * 0.98 # 2% buffer for safety

            stop_order = exchange.create_order(
                symbol=symbol,
                type='limit', # Coinbase stop-limit
                side='sell',
                amount=balance, 
                price=limit_price,
                params={
                    'stop_price': str(stop_price),
                    'stop_direction': 'STOP_DIRECTION_STOP_DOWN'
                }
            )

            print(f"✅ Stop loss placed: {stop_order['id']}")
            protected_count += 1

        except Exception as e:
            print(f"❌ Failed to place stop loss for {symbol}: {e}")

    print(f"\n{'='*50}")
    print(f"Protected {protected_count} position(s)")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
