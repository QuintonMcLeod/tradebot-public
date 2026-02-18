from ib_insync import IB, Contract, Commodity, Forex, Index, Stock
import logging

logging.basicConfig(level=logging.INFO)

def exhaustive_search():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        symbols = ['XPDUSD', 'XPD', 'PA', 'PD', 'XPD.USD', 'PALLADIUM']
        types = ['CMDTY', 'FOREX', 'IND', 'STK']
        exchanges = ['SMART', 'IDEALPRO', 'IBCMDTY', 'NYMEX', 'LME', 'GLOBEX', 'CME', 'ICE']
        
        print("\n--- Exhaustive Palladium Search ---")
        for sym in symbols:
            for t in types:
                for ex in exchanges:
                    c = Contract()
                    c.symbol = sym
                    c.secType = t
                    c.exchange = ex
                    c.currency = 'USD'
                    try:
                        # Use reqContractDetails for direct check
                        details = ib.reqContractDetails(c)
                        if details:
                            print(f"!!! FOUND !!! {sym} | {t} | {ex} (conId={details[0].contract.conId})")
                            for d in details:
                                print(f"    - Full: {d.contract}")
                    except:
                        pass

        # Also search for descriptions
        print("\n--- Search by Name 'Palladium' ---")
        matches = ib.reqMatchingSymbols("Palladium")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    exhaustive_search()
