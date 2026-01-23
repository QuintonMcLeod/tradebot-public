from ib_insync import IB, Commodity, Forex, Contract
import ccxt
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

def diagnose():
    # 1. CCXT Capital
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    
    print("\n--- CCXT Capital (Coinbase) ---")
    if not api_key or not secret:
        print("Missing CCXT credentials in environment.")
    else:
        try:
            exchange = ccxt.coinbase({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
            })
            balance = exchange.fetch_balance()
            print(f"Total USD: {balance.get('USD', {}).get('total', 0)}")
            print(f"Total USDC: {balance.get('USDC', {}).get('total', 0)}")
        except Exception as e:
            print(f"CCXT Error: {e}")

    # 2. IBKR Palladium
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        print("\n--- IBKR Palladium Final Search ---")
        # Try generic search for Palladium
        matches = ib.reqMatchingSymbols("Palladium")
        for m in matches:
            print(f"MATCH: {m.contract.symbol} | {m.contract.secType} | {m.contract.primaryExchange} | {m.contract.currency} | conId={m.contract.conId} | desc={m.contract.description}")
            # Try to get data for anything that looks like London Spot
            if "London" in m.contract.description or "Physical" in m.contract.description:
                try:
                    details = ib.reqContractDetails(m.contract)
                    if details:
                        print(f"  [VALID] Found on {details[0].contract.exchange}")
                except:
                    pass

        # Try specific variants
        for sym in ['XPDUSD', 'XPD']:
            for sec in ['CMDTY', 'FOREX', 'STK']:
                for exch in ['SMART', 'IBCMDTY', 'IDEALPRO']:
                    c = Contract()
                    c.symbol = sym
                    c.secType = sec
                    c.exchange = exch
                    c.currency = 'USD'
                    try:
                        details = ib.reqContractDetails(c)
                        if details:
                            print(f"SUCCESS: {sym} as {sec} on {exch}!! conId={details[0].contract.conId}")
                    except:
                        pass

    except Exception as e:
        print(f"IBKR Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    diagnose()
