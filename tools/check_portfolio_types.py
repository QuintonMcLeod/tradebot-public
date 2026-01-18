
import os
import json
from dotenv import load_dotenv
import ccxt

# Load environment variables
load_dotenv(".env")

def check_futures_capability():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
    })

    print("--- Searching for Futures/Perpetuals Portfolios ---")
    try:
        # 1. Fetch Accounts
        accounts = exchange.fetch_accounts()
        futures_found = False
        
        for acc in accounts:
            # Check ID, Name, Type, and Info
            aid = acc.get('id', '')
            name = str(acc.get('name', '')).lower()
            atype = str(acc.get('type', '')).lower()
            info = acc.get('info', {})
            
            # Keywords to look for
            is_futures = False
            if 'future' in name or 'perp' in name or 'fcm' in name:
                is_futures = True
            if 'future' in atype or 'perp' in atype:
                is_futures = True
            
            # Coinbase V3 specific info fields?
            # 'allow_deposits', 'allow_withdrawals' might be relevant.
            
            if is_futures:
                futures_found = True
                print(f"\n[POSSIBLE FUTURES WALLET FOUND]")
                print(f"ID: {aid}")
                print(f"Name: {acc.get('name')}")
                print(f"Type: {acc.get('type')}")
                print(f"Raw Info: {json.dumps(info, indent=2)}")
        
        if not futures_found:
            print("\n[-] No obvious 'Futures', 'Perpetuals', or 'FCM' portfolios found in the account list.")
            print(f"Total accounts scanned: {len(accounts)}")
            
        # 2. Try 'fetch_portfolios' explicitly if available (Advanced Trade concept)
        # Accounts != Portfolios in V3. 
        # Accounts are wallets WITHIN portfolios.
        # We need to list PORTFOLIOS.
        print("\n--- Fetching Portfolios (Portfolios Endpoint) ---")
        if hasattr(exchange, 'v3PrivateGetBrokeragePortfolios'):
            try:
                response = exchange.v3PrivateGetBrokeragePortfolios()
                # Debug the structure
                # print(json.dumps(response, indent=2)) 
                
                ports = response.get('portfolios', [])
                print(f"Found {len(ports)} Portfolios:")
                for p in ports:
                    p_name = p.get('name', 'N/A')
                    p_uuid = p.get('uuid', 'N/A')
                    print(f" - Name: {p_name} | UUID: {p_uuid} | Type: {p.get('type')}")
                    
                    if 'perp' in p_name.lower() or 'future' in p_name.lower():
                        print("   ^ THIS IS THE FUTURES PORTFOLIO!")
                        
            except Exception as e:
                print(f"Portfolios fetch failed: {e}")
        else:
            print("Method v3PrivateGetBrokeragePortfolios not found on ccxt object.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_futures_capability()
