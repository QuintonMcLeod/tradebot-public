from ib_insync import IB, Contract, Commodity, Forex
import logging

logging.basicConfig(level=logging.INFO)

def diagnose_deep():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Listing All Managed Accounts ---")
        accounts = ib.managedAccounts()
        print(f"Managed Accounts: {accounts}")
        
        for acc in accounts:
            print(f"\nAccount: {acc}")
            # Get full account values (this is very detailed)
            vals = ib.accountValues(acc)
            for v in vals:
                if "NetLiquidation" in v.tag or "Cash" in v.tag or "Equity" in v.tag:
                     print(f"  {v.tag}: {v.value} {v.currency} (Model: {v.modelCode})")

        print("\n--- Testing XPDUSD as CFD ---")
        for exch in ['SMART', 'IDEALPRO']:
            c = Contract(symbol='XPDUSD', secType='CFD', exchange=exch, currency='USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND CFD !!! XPDUSD on {exch}!! conId={details[0].contract.conId}")
            except:
                pass

        print("\n--- Testing conId Neighbors of Platinum (78363317) ---")
        # reqContractDetails works with conId too
        for cid in range(78363310, 78363325):
            c = Contract(conId=cid)
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"conId {cid}: {details[0].contract.symbol} | {details[0].contract.secType} | {details[0].contract.exchange}")
            except:
                pass

        print("\n--- Testing XPD as CFD ---")
        for exch in ['SMART', 'IDEALPRO']:
            c = Contract(symbol='XPD', secType='CFD', exchange=exch, currency='USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND CFD !!! XPD on {exch}!! conId={details[0].contract.conId}")
            except:
                pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose_deep()
