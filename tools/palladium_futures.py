from ib_insync import IB, Future, Contract
import logging

logging.basicConfig(level=logging.INFO)

def search_palladium_futures():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Searching for Palladium Futures (PA) ---")
        # Try reqMatchingSymbols for PA
        matches = ib.reqMatchingSymbols("PA")
        for m in matches:
            if m.contract.secType == 'FUT':
                 print(f"Match FUT: {m.contract.symbol} | {m.contract.lastTradeDateOrContractMonth} | {m.contract.exchange} | conId={m.contract.conId} | desc={m.contract.description}")

        # Try to find specific XPD futures if any
        matches = ib.reqMatchingSymbols("XPD")
        for m in matches:
             if m.contract.secType == 'FUT':
                  print(f"Match FUT XPD: {m.contract.symbol} | {m.contract.lastTradeDateOrContractMonth} | {m.contract.exchange} | conId={m.contract.conId}")

        # Try some common Palladium futures
        # NYMEX Palladium is PA
        contracts = [
            Future('PA', '202603', 'NYMEX'),
            Future('PA', '202606', 'NYMEX'),
        ]
        for c in contracts:
             try:
                  details = ib.reqContractDetails(c)
                  if details:
                       print(f"SUCCESS FUT: {c.symbol} {c.lastTradeDateOrContractMonth}!! conId={details[0].contract.conId}")
             except: pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_palladium_futures()
