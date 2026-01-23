from ib_insync import IB
import logging

logging.basicConfig(level=logging.INFO)

def diagnose():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Account Summary Tags ---")
        summary = ib.accountSummary()
        for s in summary:
            print(f"{s.tag}: {s.value} ({s.currency})")
            
        print("\n--- Searching for Palladium (XPD, PALL, XPDUSD) ---")
        for search_term in ['XPD', 'PALL', 'XPDUSD', 'Palladium']:
            print(f"\nSearching for '{search_term}':")
            matches = ib.reqMatchingSymbols(search_term)
            for m in matches:
                print(f"  Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | ID={m.contract.conId}")
                # Try to get more details for anything that looks like a metal
                if m.contract.secType in ['CMDTY', 'FOREX', 'IND']:
                    try:
                        details = ib.reqContractDetails(m.contract)
                        if details:
                            for d in details:
                                print(f"    - VALID: {d.contract.symbol} on {d.contract.exchange} ({d.contract.secType}) conId={d.contract.conId}")
                    except:
                        pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose()
