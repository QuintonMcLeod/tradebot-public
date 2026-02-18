
import os
import sys
import ccxt

# Force loading form src
sys.path.insert(0, "./src")

def check_balance():
    # Load keys directly from env to be sure
    api_key = os.getenv("GEMINI_API_KEY")
    secret = os.getenv("GEMINI_API_SECRET")
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in env")
        return

    print(f"Connecting to Gemini with key: {api_key[:15]}...")
    
    import time
    exchange = ccxt.gemini({
        'apiKey': api_key,
        'secret': secret,
        'timeout': 30000,
        'options': {'adjustForTimeDifference': True},
    })
    exchange.nonce = lambda: time.time_ns()
    
    try:
        balance = exchange.fetch_balance()
        print("\n--- BALANCE REPORT ---")
        
        # Check USD specifically
        print(f"USD: Free={balance.get('free', {}).get('USD', 0)} | Total={balance.get('total', {}).get('USD', 0)}")
        
        # Print all non-zero
        print("\n--- ALL NON-ZERO ASSETS (Total) ---")
        for curr, amt in balance.get('total', {}).items():
            if float(amt) > 0:
                print(f"{curr}: {amt} (Free: {balance['free'].get(curr, 0)})")
                
    except Exception as e:
        print(f"ERROR Fetching Balance: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_balance()
