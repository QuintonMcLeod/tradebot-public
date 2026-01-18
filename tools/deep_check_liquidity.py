import ccxt
import os
import logging
import json
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deep_check")

def deep_check():
    # Force load .env
    load_dotenv(override=True)
    
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if not api_key or not secret:
        logger.error("API keys missing from .env")
        return

    # EXACT logic from ccxt_broker.py
    if secret and "\\n" in secret and "\n" not in secret:
         logger.info("Detected escaped newlines in API Secret. Normalizing...")
         secret = secret.replace("\\n", "\n")
    
    # Debug info (Safe)
    print(f"Secret Length: {len(secret)}")
    print(f"Secret Prefix: {secret[:20]}...")
    print(f"Secret Suffix: ...{secret[-20:]}")

    exchange = ccxt.coinbase({
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": True,
        "timeout": 30000,
        "options": {"createMarketBuyOrderRequiresPrice": False}
    })

    print("\n=== CONNECTIVITY TEST ===")
    try:
        # Just a public call first
        markets = exchange.load_markets()
        print(f"Successfully loaded {len(markets)} markets.")
    except Exception as e:
        print(f"load_markets failed: {e}")
        return

    print("\n=== TICKER TEST ===")
    test_symbols = ["BTC/USD", "XRP/USD:USD-301220"]
    for sym in test_symbols:
        try:
            ticker = exchange.fetch_ticker(sym)
            print(f"[OK] {sym}: Last={ticker.get('last')}")
        except Exception as e:
            print(f"[FAIL] {sym}: {e}")

    # 3. Exhaustive Balance Check
    print("\n=== BALANCE DUMP ===")
    # These are the common Coinbase types
    balance_types = [None, "spot", "future", "swap", "futures", "wallet"]
    for b_type in balance_types:
        params = {}
        if b_type:
            params["type"] = b_type
        
        try:
            print(f"\n--- Balance Type: {b_type} ---")
            bal = exchange.fetch_balance(params)
            
            # Print ALL keys with non-zero total
            found = False
            if "total" in bal:
                for asset, amount in bal["total"].items():
                    if float(amount or 0) > 0:
                        print(f"  {asset}: Total={amount} | Free={bal.get('free', {}).get(asset, 0)}")
                        found = True
            
            if not found:
                print("  No non-zero balances.")
                
        except Exception as e:
            print(f"  Error fetching {b_type}: {e}")

    print("\n=== ACCOUNTS DUMP ===")
    try:
        # Coinbase accounts (wallets)
        accounts = exchange.fetch_accounts()
        for acc in accounts:
            a_id = acc.get('id')
            a_name = acc.get('name')
            a_type = acc.get('type')
            print(f"Account: {a_name} ({a_type}) ID={a_id}")
            # Try to fetch balance for specific account if possible
            # (Note: CCXT fetch_balance usually handles this via params['type'])
    except Exception as e:
        print(f"fetch_accounts failed: {e}")

if __name__ == "__main__":
    deep_check()
