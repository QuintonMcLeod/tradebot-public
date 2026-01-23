from ib_insync import IB, Contract
import logging

logging.basicConfig(level=logging.INFO)

def final_palladium_push():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        
        candidates = []
        # Search by symbol
        for s in ['XPD', 'XPDUSD', 'PD', 'XPD.USD']:
            matches = ib.reqMatchingSymbols(s)
            candidates.extend([m.contract for m in matches])
            
        # Search by name
        matches = ib.reqMatchingSymbols("Palladium")
        candidates.extend([m.contract for m in matches])
        
        unique_contracts = {}
        for c in candidates:
            key = (c.symbol, c.secType, c.primaryExchange, c.currency)
            if key not in unique_contracts:
                unique_contracts[key] = c

        print(f"\n--- Testing {len(unique_contracts)} unique candidates ---")
        for key, c in unique_contracts.items():
            # Override exchange to SMART if it's empty
            if not c.exchange:
                c.exchange = 'SMART'
            
            try:
                details = ib.reqContractDetails(c)
                if details:
                    for d in details:
                        # Print full details for anything that is CMDTY or is Palladium-related
                        is_palladium = "palladium" in d.longName.lower() or "palladium" in d.contract.symbol.lower()
                        if d.contract.secType == 'CMDTY' or is_palladium:
                            print(f"\n!!! SUCCESS !!!")
                            print(f"Contract: {d.contract}")
                            print(f"Long Name: {d.longName}")
                            print(f"Category: {d.category}")
                            print(f"Industry: {d.industry}")
                            print(f"Valid Exchange: {d.validExchanges}")
            except:
                pass

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    final_palladium_push()
