from ib_insync import IB, Contract, Index
import logging

logging.basicConfig(level=logging.INFO)

def diagnose_final():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Searching for 'Zurich' in Commodities/Indices ---")
        matches = ib.reqMatchingSymbols("Zurich")
        for m in matches:
            if "Palladium" in m.contract.description or "XPD" in m.contract.symbol:
                print(f"Match Zurich: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Searching for 'XPD' as Index/CFD/Forex specifically ---")
        for stype in ['IND', 'CFD', 'FOREX', 'CMDTY']:
            c = Contract(symbol='XPD', secType=stype, currency='USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"FOUND {stype} for XPD: {details[0].contract}")
            except: pass

        print("\n--- Checking Account Segments Again ---")
        acc = ib.managedAccounts()[0]
        vals = ib.accountValues(acc)
        for v in vals:
            if v.tag in ["NetLiquidation-S", "NetLiquidation-C", "NetLiquidation"]:
                print(f"  {v.tag}: {v.value} {v.currency}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose_final()
