from ib_insync import IB, Commodity
import logging

logging.basicConfig(level=logging.INFO)

def search_london():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Searching for 'London Palladium' ---")
        matches = ib.reqMatchingSymbols("London Palladium")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")
            
        print("\n--- Searching for 'XPD' with CMDTY filter ---")
        # reqMatchingSymbols doesn't filter, but let's see.
        matches = ib.reqMatchingSymbols("XPD")
        for m in matches:
             if m.contract.secType == 'CMDTY':
                  print(f"FOUND CMDTY for XPD: {m.contract}")

        print("\n--- Searching for 'XPDUSD' with CMDTY filter ---")
        matches = ib.reqMatchingSymbols("XPDUSD")
        for m in matches:
             if m.contract.secType == 'CMDTY':
                  print(f"FOUND CMDTY for XPDUSD: {m.contract}")

        print("\n--- Brute Force conId around Platinum ---")
        # reqContractDetails(Contract(conId=...))
        # Platinum was 78363317
        for cid in range(78363300, 78363400):
            try:
                details = ib.reqContractDetails(ib.client.getContractDetails(cid)) # No, simple
                c = Contract(conId=cid)
                # ...
            except: pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_london()
