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
    print(f"Loaded {len(markets)} markets from Gemini")
    for symbol in sorted(markets.keys()):
        if '/USD' in symbol or '/GUSD' in symbol:
            print(symbol)
except Exception as e:
    print(f"Error: {e}")
