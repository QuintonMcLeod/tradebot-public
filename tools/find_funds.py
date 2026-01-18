
import os
import sys
import json
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv(".env")

def find_funds():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    print(f"DEBUG: Using Key ID: {api_key}")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
    })

    try:
        print("\n--- Scanning All Portfolios/Accounts for Funds ---")
        # In Coinbase V3, fetch_accounts returns wallets.
        # We need to see if fetch_balance accepts params to specify portfolio.
        # But first, let's see where the money IS.
        
        # Method 1: fetch_accounts (often just lists wallets, but maybe includes balance)
        accounts = exchange.fetch_accounts()
        found_funds = False
        
        for acc in accounts:
            # acc structure varies. print one to see.
            # Usually 'info' contains the raw response.
            raw = acc.get('info', {})
            val = float(raw.get('available_balance', {}).get('value', 0.0))
            currency = raw.get('available_balance', {}).get('currency', '')
            
            if val > 0:
                found_funds = True
                print(f"FOUND FUNDS: {val} {currency} | ID: {acc['id']} | Name: {acc.get('name')} | Type: {acc.get('type')}")
        
        if not found_funds:
            print("No funds found in fetch_accounts(). Checking 'portfolios' endpoint directly...")
            # Try raw fetch of portfolios if CCXT method is ambiguous
            if hasattr(exchange, 'v3PrivateGetBrokeragePortfolios'):
                 ports = exchange.v3PrivateGetBrokeragePortfolios()
                 print(json.dumps(ports, indent=2))

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    find_funds()
