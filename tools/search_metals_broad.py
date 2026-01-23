from ib_insync import IB
import logging

logging.basicConfig(level=logging.INFO)

def search_london_all():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        print("\n--- Searching for 'London' (all results) ---")
        matches = ib.reqMatchingSymbols("London")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

        print("\n--- Searching for 'Palladium' (all results) ---")
        matches = ib.reqMatchingSymbols("Palladium")
        for m in matches:
            print(f"Match: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    search_london_all()
