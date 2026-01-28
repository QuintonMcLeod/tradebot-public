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
    with open('gemini_markets_full.txt', 'w') as f:
        for symbol in sorted(markets.keys()):
            f.write(symbol + '\n')
    print(f"Saved {len(markets)} symbols to gemini_markets_full.txt")
except Exception as e:
    print(f"Error: {e}")
