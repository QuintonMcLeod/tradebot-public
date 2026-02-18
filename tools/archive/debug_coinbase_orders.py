import ccxt
import os
from dotenv import load_dotenv

def main():
    load_dotenv()
    apiKey = os.getenv('CCXT_API_KEY')
    print(f"Using API Key: {apiKey[:4]}...{apiKey[-4:] if apiKey else ''}")
    exchange = ccxt.coinbase({
        'apiKey': apiKey,
        'secret': os.getenv('CCXT_SECRET'),
        'enableRateLimit': True,
    })
    
    print("--- BALANCES ---")
    try:
        bal = exchange.fetch_balance()
        if 'POL' in bal:
            print(f"Raw POL balance details: {bal['POL']}")
        total = bal.get('total', {})
        free = bal.get('free', {})
        used = bal.get('used', {})
        for curr in total.keys():
            if total.get(curr, 0) > 0:
                print(f"{curr}: total={total[curr]} free={free.get(curr,0)} used={used.get(curr,0)}")
    except Exception as e:
        print(f"Balance error: {e}")

    print("\n--- OPEN ORDERS ---")
    try:
        orders = exchange.fetch_open_orders()
        if not orders:
            print("No open orders found.")
        else:
            for o in orders:
                print(f"ID: {o['id']} | Symbol: {o['symbol']} | Side: {o['side']} | Status: {o['status']}")
                print(f"  Cancelling {o['id']}...")
                exchange.cancel_order(o['id'], o['symbol'])
                print("  Cancelled.")
    except Exception as e:
        print(f"Orders error: {e}")

if __name__ == "__main__":
    main()
