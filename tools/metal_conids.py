from ib_insync import IB, Commodity
import logging

logging.basicConfig(level=logging.INFO)

def search_metals():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        metals = ['XAUUSD', 'XAGUSD', 'XPTUSD']
        for sym in metals:
            c = Commodity(sym, 'SMART', 'USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND !!! {sym} | conId={details[0].contract.conId} | exch={details[0].contract.exchange}")
            except:
                print(f"Failed to find details for {sym}")

        # Let's try to search for any CMDTY on SMART that has USD currency
        # and see if we can spot Palladium.
        # This isn't easily possible with a single call, but we can try common ones.
        for sym in ['XPDUSD', 'XPD']:
            # Maybe it's not SMART but IBCMDTY primary?
            c = Commodity(sym, 'SMART', 'USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"!!! FOUND PALLADIUM !!! {sym} | conId={details[0].contract.conId}")
            except: pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_metals()
