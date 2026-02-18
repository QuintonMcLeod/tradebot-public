from ib_insync import IB, Commodity, Forex
import logging

logging.basicConfig(level=logging.INFO)

def diagnose():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Managed Accounts ---")
        accounts = ib.managedAccounts()
        print(f"Accounts: {accounts}")
        
        for acc in accounts:
            print(f"\nDetails for {acc}:")
            vals = ib.accountValues(acc)
            # Find NetLiquidation, TotalCashValue, and check for segments
            for v in vals:
                if v.tag in ["NetLiquidation", "TotalCashValue", "AvailableFunds", "FuturePnL"]:
                    print(f"  {v.tag}: {v.value} {v.currency}")

        print("\n--- Deep Palladium Search ---")
        # Try some common Palladium symbols/conIds if possible
        # XPTUSD was conId=78363317 (SMART)
        # Often metals are in a sequence
        for sym in ['XPDUSD', 'XPD', 'XPD.USD', 'PD', 'PDUSD']:
            print(f"\nSearching for '{sym}':")
            # Try matching symbols first
            matches = ib.reqMatchingSymbols(sym)
            for m in matches:
                print(f"  Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId}")
            
            # Try specific definitions for each variant
            for exch in ['SMART', 'NYMEX', 'LME', 'IBCMDTY', 'ICE', 'CME']:
                c = Commodity(sym, exch, 'USD')
                try:
                    details = ib.reqContractDetails(c)
                    if details:
                        print(f"    [FOUND CMDTY] {sym} on {exch}!! conId={details[0].contract.conId}")
                except:
                    pass
                
                # Also try Forex just in case it's actually registered as Forex for Palladium
                if len(sym) == 6 and sym.endswith('USD'):
                    try:
                        f = Forex(sym)
                        details = ib.reqContractDetails(f)
                        if details:
                            print(f"    [FOUND FOREX] {sym} on {f.exchange}!! conId={details[0].contract.conId}")
                    except:
                        pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose()
