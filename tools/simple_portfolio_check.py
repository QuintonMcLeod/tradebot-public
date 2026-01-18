
import os
import sys
import json
import logging


# Check if ccxt is installed
try:
    import ccxt
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    print("CCXT or dotenv not installed.")
    sys.exit(1)


# Configure basic logging to stdout
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(message)s')
logger = logging.getLogger()

def check():
    print("--- Starting Simple Portfolio Check ---")
    
    api_key = os.environ.get("CCXT_API_KEY")
    secret = os.environ.get("CCXT_SECRET")
    
    # Fix escaped newlines in PEM key
    if secret and '\\n' in secret:
        secret = secret.replace('\\n', '\n')
    
    if not api_key or not secret:
        print("Error: CCXT_API_KEY or CCXT_SECRET not found in environment.")
        return

    # Initialize Coinbase (v3/Advanced Trade)
    # Using 'coinbase' class which covers Advanced Trade
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
    })
    
    try:
        # 1. Fetch Accounts (Balances)
        print("\n[1] Fetching Accounts/Balances...")
        accounts = exchange.fetch_accounts()
        print(f"Found {len(accounts)} accounts.")
        for msg in accounts:
            if float(msg['info'].get('available_balance', {}).get('value', 0)) > 0:
                 print(f" - {msg['code']}: {msg['info']['available_balance']['value']}")

        # 2. Fetch Portfolios (Proprietary endpoint)
        print("\n[2] Fetching Portfolios (Advanced Trade API)...")
        if hasattr(exchange, 'privateGetBrokeragePortfolios'):
            response = exchange.privateGetBrokeragePortfolios()
            portfolios = response.get('portfolios', [])
            print(f"Found {len(portfolios)} portfolios:")
            for p in portfolios:
                print(f" - Name: {p.get('name')}")
                print(f"   UUID: {p.get('uuid')}")
                print(f"   Type: {p.get('type')}")
                # Check for breakdown
                breakdown = p.get('breakdown', {})
                print(f"   Balance: {breakdown.get('portfolio_balances', {}).get('total_balance', {}).get('value', 'N/A')}")
        else:
            print(" - privateGetBrokeragePortfolios method not found on exchange object.")
            
    except Exception as e:
        print(f"\n[ERROR] Request Failed: {e}")
        # Print detailed ccxt error if available
        
    print("\n--- Check Complete ---")

if __name__ == "__main__":
    check()
