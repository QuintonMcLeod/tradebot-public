import ccxt
import os
import json
from dotenv import load_dotenv

load_dotenv()

def check():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    if not api_key or not secret:
        print("Error: credentials missing")
        return

    # Handle escaped newlines
    if "\\n" in secret:
        secret = secret.replace("\\n", "\n")

    ex = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'} # or swap/future
    })
    
    print("Loading markets...")
    markets = ex.load_markets()
    
    targets = ["DASH/USDC:USDC", "ORDI/USDC:USDC", "INJ/USDC:USDC", "AR/USDC:USDC", "ZEN/USDC:USDC"]
    
    for t in targets:
        if t in markets:
            m = markets[t]
            print(f"\n--- {t} ---")
            print(f"Active: {m.get('active')}")
            print(f"Type: {m.get('type')}")
            # print(json.dumps(m, indent=2, default=str)) # too verbose, let's look for info
            info = m.get('info', {})
            print(f"Status: {info.get('status')}")
            print(f"Trading Disabled: {info.get('trading_disabled')}")
            print(f"Cancel Only: {info.get('cancel_only')}")
            print(f"Post Only: {info.get('post_only')}")
            print(f"Limit Only: {info.get('limit_only')}")
            
            # Coinbase Derivatives often have session times in info
            # Look for session_times or similar
            
        else:
            print(f"{t}: NOT FOUND in CCXT markets")

if __name__ == "__main__":
    check()
