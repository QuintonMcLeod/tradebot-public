from ib_insync import IB, Contract
import logging

logging.basicConfig(level=logging.INFO)

def compare_metal_searches():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        for sym in ['XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD']:
            print(f"\n--- Searching for '{sym}' ---")
            matches = ib.reqMatchingSymbols(sym)
            for m in matches:
                print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

        for sym in ['XAU', 'XAG', 'XPT', 'XPD']:
            print(f"\n--- Searching for '{sym}' (short) ---")
            matches = ib.reqMatchingSymbols(sym)
            for m in matches:
                # Filter for things that look like metals
                desc = m.contract.description.lower()
                if 'gold' in desc or 'silver' in desc or 'platinum' in desc or 'palladium' in desc:
                     print(f"Match Meta: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    compare_metal_searches()
