
import os
import sys
import ccxt
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
print(f"[DEBUG] Loading .env from: {env_path}")
load_dotenv(env_path)

def cancel_zombies():
    api_key = os.getenv("CCXT_API_KEY")
    api_secret = os.getenv("CCXT_SECRET")

    if not api_key or not api_secret:
        print("Error: Missing credentials in .env")
        return

    # Normalize secret
    api_secret = api_secret.replace("\\n", "\n")

    print("[INFO] Connecting to Coinbase Futures...")
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    try:
        # Fetch open orders
        print("[INFO] Fetching open orders...")
        orders = exchange.fetch_open_orders()
        
        if not orders:
            print("[INFO] No open orders found. Account is clean.")
            return

        print(f"[INFO] Found {len(orders)} open orders. Canceling...")
        
        for order in orders:
            oid = order['id']
            symbol = order['symbol']
            side = order['side']
            print(f" -> Canceling {side} {symbol} (ID: {oid})...")
            try:
                exchange.cancel_order(oid, symbol)
                print("    [SUCCESS]")
            except Exception as e:
                print(f"    [FAILED] {e}")

        print("[INFO] Done. All zombie orders cleared.")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    cancel_zombies()
