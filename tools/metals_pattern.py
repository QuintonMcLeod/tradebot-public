from ib_insync import IB, Contract, Commodity, Forex
import logging

logging.basicConfig(level=logging.INFO)

def search_metals_pattern():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Searching for 'Loco London' ---")
        matches = ib.reqMatchingSymbols("Loco London")
        for m in matches:
             print(f"Match Loco: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Searching for 'Spot' ---")
        matches = ib.reqMatchingSymbols("Spot")
        for m in matches:
             if m.contract.secType in ['CMDTY', 'IND']:
                  print(f"Match Spot: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Bruteforce Palladium variants as Forex ---")
        for sym in ['XPDUSD', 'XPD', 'XPD.USD', 'PALLUSD']:
             try:
                  f = Forex(sym)
                  details = ib.reqContractDetails(f)
                  if details:
                       print(f"SUCCESS FOREX: {sym}!! conId={details[0].contract.conId}")
             except: pass

        print("\n--- Bruteforce Palladium variants as CMDTY on SMART ---")
        for sym in ['XPD', 'XPD.USD', 'PD', 'XPDUSD', 'XPALUSD', 'LLPALL']:
             try:
                  c = Commodity(sym, 'SMART', 'USD')
                  details = ib.reqContractDetails(c)
                  if details:
                       print(f"SUCCESS CMDTY SMART: {sym}!! conId={details[0].contract.conId}")
             except: pass

        print("\n--- Brute Force conId Neighbors of Platinum (78363317) EXTENDED ---")
        for cid in range(78363300, 78363400):
            c = Contract(conId=cid)
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"conId {cid}: {details[0].contract.symbol} | {details[0].contract.secType} | {details[0].contract.exchange} | desc={details[0].longName}")
            except: pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_metals_pattern()
