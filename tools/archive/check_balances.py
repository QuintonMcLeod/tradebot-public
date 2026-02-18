import ccxt
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent / "src"))

from tradebot_sci.config.loader import get_settings

def check_balances():
    s = get_settings()
    
    # Check OANDA
    print("--- OANDA ---")
    if s.oanda:
        from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
        try:
            o = OandaExchangeBroker(s.oanda.account_id, s.oanda.api_key, s.profiles['auto_schedule'], environment=s.oanda.environment)
            # It logs summary in __init__ -> refresh_account_summary
            print(f"OANDA NAV (from broker object): {o.get_liquid_capital()}")
        except Exception as e:
            print(f"OANDA failed: {e}")
    else:
        print("OANDA not configured in Settings.")

    # Check CCXT (Coinbase)
    print("\n--- COINBASE (CCXT) ---")
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET", "").replace("\\n", "\n")
    if api_key and secret:
        ex = ccxt.coinbase({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True
        })
        try:
            print("Fetching Spot balances...")
            spot = ex.fetch_balance({"type": "spot"})
            print(f"Spot Total: {spot.get('total').get('USD')}")
        except Exception as e:
            print(f"Coinbase failed: {e}")
    else:
        print("Coinbase credentials missing in Env.")

if __name__ == "__main__":
    check_balances()
