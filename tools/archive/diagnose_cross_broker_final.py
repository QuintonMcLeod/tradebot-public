from ib_insync import IB, Commodity
import ccxt
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

def diagnose():
    # 1. CCXT Capital
    api_key = os.getenv("CCXT_API_KEY")
    secret_raw = os.getenv("CCXT_SECRET") # Note: handled by .env loader
    
    print("\n--- CCXT Capital (Coinbase) ---")
    try:
        exchange = ccxt.coinbase({
            'apiKey': api_key,
            'secret': secret_raw,
        })
        balance = exchange.fetch_balance()
        usd_bal = balance.get('USD', {}).get('total', 0)
        usdc_bal = balance.get('USDC', {}).get('total', 0)
        print(f"Total USD: {usd_bal}")
        print(f"Total USDC: {usdc_bal}")
        
        # Check for Futures sub-account
        # Coinbase uses a different API for futures sometimes, but CCXT handles it via types
        # Let's try to fetch balance for default type 'future' if possible
        try:
            exchange_f = ccxt.coinbase({
                'apiKey': api_key,
                'secret': secret_raw,
                'options': {'defaultType': 'future'}
            })
            bal_f = exchange_f.fetch_balance()
            print(f"Futures Balance (total): {bal_f.get('total', {})}")
        except Exception as e:
            print(f"Futures Balance Check Failed: {e}")

    except Exception as e:
        print(f"CCXT Error: {e}")

    # 2. Palladium Targeted
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        print("\n--- IBKR Palladium Deep Search ---")
        # London Palladium is often XPD
        # Let's try various names and types
        search_terms = ['XPD', 'XPDUSD', 'Palladium', 'LUPALL', 'LXPALL']
        for term in search_terms:
            matches = ib.reqMatchingSymbols(term)
            for m in matches:
                # Filter for things that could be metals
                if m.contract.secType in ['CMDTY', 'IND', 'STK', 'BAG']:
                    print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")
                    # If it's CMDTY or IND, it's a high candidate
                    if m.contract.secType == 'CMDTY':
                        # Try to get data
                        details = ib.reqContractDetails(m.contract)
                        if details:
                            print(f"  [VALID CMDTY] {m.contract.symbol} found on {details[0].contract.exchange}")

        # Final brute force on SMART for XPD
        c = Commodity('XPD', 'SMART', 'USD')
        details = ib.reqContractDetails(c)
        if details:
            print(f"SUCCESS: XPD on SMART as CMDTY found! conId={details[0].contract.conId}")

    except Exception as e:
        print(f"IBKR Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose()
