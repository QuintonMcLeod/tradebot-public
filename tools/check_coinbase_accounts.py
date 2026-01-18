import os
import sys
import json
import ccxt
from dotenv import load_dotenv

def main():
    # Load .env explicitly
    load_dotenv()
    
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    password = os.getenv("CCXT_PASSWORD") # Coinbase usually doesn't need this for Cloud/Advanced, but older Pro keys did
    
    if not api_key or not secret:
        print("Error: CCXT_API_KEY and CCXT_SECRET must be set in .env")
        sys.exit(1)

    print("--- Connecting to Coinbase (via CCXT) ---")
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'password': password,
        'enableRateLimit': True,
        # 'verbose': True 
    })
    
    # Force reloading markets to ensure we have network connectivity
    try:
        exchange.load_markets()
        print(f"Connected! Loaded {len(exchange.markets)} markets.")
    except Exception as e:
        print(f"Connection Failed: {e}")
        sys.exit(1)

    print("\n--- 1. Standard fetch_balance() ---")
    try:
        bal = exchange.fetch_balance()
        total = bal.get('total', {})
        non_zero = {k: v for k, v in total.items() if float(v) > 0}
        print(f"Non-zero balances (Default Portfolio): {json.dumps(non_zero, indent=2)}")
    except Exception as e:
        print(f"fetch_balance failed: {e}")

    print("\n--- 2. Fetching All Accounts (Portfolios) ---")
    # Coinbase specific: list all accounts/wallets to see if funds are partitioned
    try:
        if exchange.has.get('fetchAccounts'):
            accounts = exchange.fetch_accounts()
            print(f"Found {len(accounts)} accounts/wallets. showing non-zero:")
            for acc in accounts:
                amt = float(acc.get('info', {}).get('available_balance', {}).get('value', 0) or acc.get('info', {}).get('balance', {}).get('amount', 0) or 0)
                if amt > 0:
                     print(f" - ID: {acc.get('id')} | Type: {acc.get('type')} | Code: {acc.get('code')} | Amount: {amt}")
        else:
            print("fetchAccounts not supported by this ccxt driver configuration.")
    except Exception as e:
        print(f"fetchAccounts failed: {e}")

if __name__ == "__main__":
    main()
