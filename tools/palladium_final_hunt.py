from ib_insync import IB, Contract, Commodity, Forex
import logging

logging.basicConfig(level=logging.INFO)

def search_palladium_final():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Listing ALL CMDTY on LME ---")
        # Direct list is hard, but we can try common ones
        for sym in ['XPD', 'XPDUSD', 'PD', 'XPD.USD', 'XPAL', 'XPALUSD', 'LXPALL']:
            c = Contract(symbol=sym, secType='CMDTY', exchange='LME', currency='USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND !!! {sym} | CMDTY | LME | conId={details[0].contract.conId}")
            except: pass

        print("\n--- Listing ALL CMDTY on IBCMDTY ---")
        for sym in ['XPD', 'XPDUSD', 'PD', 'XPD.USD', 'XPAL', 'XPALUSD', 'LXPALL']:
            c = Contract(symbol=sym, secType='CMDTY', exchange='IBCMDTY', currency='USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND !!! {sym} | CMDTY | IBCMDTY | conId={details[0].contract.conId}")
            except: pass

        print("\n--- Search by Matching Symbol 'XPD' ---")
        matches = ib.reqMatchingSymbols("XPD")
        for m in matches:
             print(f"Match XPD: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Search by Matching Symbol 'PD' ---")
        matches = ib.reqMatchingSymbols("PD")
        for m in matches:
             print(f"Match PD: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Search by Description 'London' AND 'Palladium' ---")
        matches = ib.reqMatchingSymbols("London")
        for m in matches:
             if "Palladium" in m.contract.description:
                  print(f"Match London Palladium: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_palladium_final()
