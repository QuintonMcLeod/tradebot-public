import ccxt
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_v3")

def test_v3():
    load_dotenv(override=True)
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if secret and "\\n" in secret and "\n" not in secret:
         secret = secret.replace("\\n", "\n")
    
    # Remove quotes if they were added by mistake in .env
    if secret.startswith('"') and secret.endswith('"'):
        secret = secret[1:-1]

    exchange = ccxt.coinbase({
        "apiKey": api_key,
        "secret": secret,
    })

    print("=== Testing GET /api/v3/brokerage/transaction_summary ===")
    try:
        # transaction_summary is usually mapped to fetch_transaction_summary or similar in CCXT
        # or we can use implicit call
        res = exchange.private_get_brokerage_transaction_summary()
        print("Success! Transaction Summary:")
        print(res)
    except Exception as e:
        print(f"Failed: {e}")

    print("\n=== Testing fetch_balance(type='future') ===")
    try:
        bal = exchange.fetch_balance({"type": "future"})
        print("Future Balance Header:", {k: v for k, v in bal.items() if k != 'info' and k != 'total' and k != 'free' and k != 'used'})
        positives = {k: v for k, v in bal.get('total', {}).items() if float(v or 0) > 0}
        print("Positive Future Balances:", positives)
    except Exception as e:
        print(f"Future Balance Fetch Failed: {e}")

if __name__ == "__main__":
    test_v3()
