import os
import ccxt
from dotenv import load_dotenv

def check_balances():
    load_dotenv()
    
    # Simple normalization for the secret (the bot does this too)
    secret = os.getenv('CCXT_SECRET', '')
    if '\\n' in secret:
        secret = secret.replace('\\n', '\n')
        
    exchange = ccxt.coinbase({
        'apiKey': os.getenv('CCXT_API_KEY'),
        'secret': secret,
        'enableRateLimit': True,
    })
    
    try:
        bal = exchange.fetch_balance()
        print("--- NON-ZERO BALANCES ---")
        for curr, amount in bal['total'].items():
            if amount > 0:
                print(f"{curr}: Total={amount}, Free={bal['free'].get(curr, 0)}, Used={bal['used'].get(curr, 0)}")
    except Exception as e:
        print(f"Error fetching balance: {e}")

if __name__ == "__main__":
    check_balances()
