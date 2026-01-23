from ib_insync import IB, Commodity
import ccxt
import os
import logging

logging.basicConfig(level=logging.INFO)

def diagnose():
    # 1. IBKR Segment / METALS search
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99)
        print("\n--- IBKR Metals Search ---")
        for sym in ['XPD', 'XPDUSD', 'PALL']:
            for exch in ['METALS', 'LME', 'LME.USD']:
                c = Commodity(sym, exch, 'USD')
                try:
                    details = ib.reqContractDetails(c)
                    if details:
                        print(f"SUCCESS: {sym} on {exch} ({details[0].contract.secType}) conId={details[0].contract.conId}")
                except:
                    pass

        print("\n--- IBKR Group Values (Segments) ---")
        # reqAccountValues(account) returns even more details than accountSummary
        acc = ib.managedAccounts()[0]
        values = ib.accountValues(acc)
        for v in values:
            if "Liquidation" in v.tag or "Cash" in v.tag or "Balance" in v.tag:
                print(f"{v.tag}: {v.value} {v.currency} (Model: {v.modelCode})")

    except Exception as e:
        print(f"IBKR Error: {e}")
    finally:
        ib.disconnect()

    # 2. CCXT Capital
    from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
    from tradebot_sci.config.models import RuntimeSettings
    
    try:
        # Minimal settings for diagnostic
        settings = RuntimeSettings(
            ccxt_exchange="coinbase",
            ccxt_api_key=os.getenv("CCXT_API_KEY"),
            ccxt_secret=os.getenv("CCXT_SECRET"),
            ccxt_passphrase=os.getenv("CCXT_PASSPHRASE")
        )
        # Attempt to get capital via actual method if possible, or just raw fetch
        print("\n--- CCXT Capital ---")
        exchange = ccxt.coinbase({
            'apiKey': os.getenv("CCXT_API_KEY"),
            'secret': os.getenv("CCXT_SECRET"),
        })
        balance = exchange.fetch_balance()
        print(f"Total USD: {balance.get('USD', {}).get('total', 0)}")
        print(f"Total USDC: {balance.get('USDC', {}).get('total', 0)}")
        # Check for Futures sub-account if any
        if hasattr(exchange, 'fetch_positions'):
            try:
                pos = exchange.fetch_positions()
                print(f"Open Positions: {len(pos)}")
            except:
                pass

    except Exception as e:
        print(f"CCXT Error: {e}")

if __name__ == "__main__":
    diagnose()
