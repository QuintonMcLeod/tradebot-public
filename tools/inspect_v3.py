import ccxt
import os
from dotenv import load_dotenv

def inspect_coinbase():
    load_dotenv(override=True)
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if secret and "\\n" in secret and "\n" not in secret:
         secret = secret.replace("\\n", "\n")
    if secret.startswith('"') and secret.endswith('"'):
        secret = secret[1:-1]

    exchange = ccxt.coinbase({
        "apiKey": api_key,
        "secret": secret,
    })

    print("=== Searching for transaction_summary in methods ===")
    methods = [m for m in dir(exchange) if "transaction_summary" in m]
    print(methods)

    print("\n=== Testing request() approach ===")
    try:
        # GET /api/v3/brokerage/transaction_summary
        res = exchange.request('brokerage/transaction_summary', 'private', 'GET', {})
        print("Success!")
        print(res)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    inspect_coinbase()
