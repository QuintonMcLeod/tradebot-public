from ib_insync import IB, Commodity, Contract
import logging

logging.basicConfig(level=logging.INFO)

def deep_metal_dump():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        metals = ['XAUUSD', 'XAGUSD', 'XPTUSD']
        for sym in metals:
            c = Commodity(sym, 'SMART', 'USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"\n--- {sym} Details ---")
                    d = details[0].contract
                    print(f"symbol: {d.symbol}")
                    print(f"secType: {d.secType}")
                    print(f"exchange: {d.exchange}")
                    print(f"primaryExchange: {d.primaryExchange}")
                    print(f"currency: {d.currency}")
                    print(f"localSymbol: {d.localSymbol}")
                    print(f"tradingClass: {d.tradingClass}")
                    print(f"conId: {d.conId}")
            except Exception as e:
                print(f"Error for {sym}: {e}")

        print("\n--- Searching for 'Spot Palladium' ---")
        matches = ib.reqMatchingSymbols("Spot Palladium")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Searching for 'Palladium USD' ---")
        matches = ib.reqMatchingSymbols("Palladium USD")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Searching for 'XPD' and checking all exchange/type pairs ---")
        # Try to find what XPT's primaryExchange is. 
        # If XPT is on SMART but primary is IBCMDTY, maybe XPD is too.
        for ex in ['IBCMDTY', 'SMART', 'LME', 'NYMEX']:
            c = Commodity('XPD', ex, 'USD')
            try:
                details = ib.reqContractDetails(c)
                if details:
                    print(f"SUCCESS: XPD as CMDTY found on {ex}!! conId={details[0].contract.conId}")
            except: pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    deep_metal_dump()
