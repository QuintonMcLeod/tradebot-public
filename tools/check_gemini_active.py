import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.gemini({
    'apiKey': os.getenv('GEMINI_API_KEY'),
    'secret': os.getenv('GEMINI_API_SECRET'),
})

try:
    markets = exchange.load_markets()
    symbols = ['BTC/USD', 'ETH/USD', 'LINK/USD', 'ADA/USD', 'NEAR/USD', 'USDP/USD', 'ADARL/USD']
    for sym in symbols:
        if sym in markets:
            m = markets[sym]
            print(f"{sym}: type={type(m)}")
            if isinstance(m, dict):
                print(f"  active={m.get('active')}")
                info = m.get('info')
                if isinstance(info, list):
                    print(f"  info (list) first item: {info[0] if info else 'EMPTY'}")
                else:
                    print(f"  info (dict) symbol: {info.get('symbol') if info else 'NONE'}")
            else:
                print(f"  content: {m}")
        else:
            print(f"{sym}: NOT FOUND")
except Exception as e:
    print(f"Error: {e}")
