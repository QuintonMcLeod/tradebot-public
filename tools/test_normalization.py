
import os
import ccxt
from dotenv import load_dotenv
import logging

# Set up logging to match the bot
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock some symbols and metadata
class AssetClass:
    EQUITY = "equity"
    CRYPTO = "crypto"
    FOREX = "forex"
    FUTURE = "future"

# Import or mock the classes
from tradebot_sci.market.providers import CCXTMarketDataProvider

load_dotenv()

def test_normalization():
    api_key = os.getenv("CCXT_API_KEY")
    secret = os.getenv("CCXT_SECRET")
    if secret:
        secret = secret.replace("\\n", "\n")
        
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })
    
    # Matching the symbol map in CCXTExchangeBroker
    symbol_map = {
        "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD", "LTCUSD": "LTC/USD"
    }
    
    provider = CCXTMarketDataProvider(exchange, symbol_map)
    
    print(f"Testing ETHUSD normalization...")
    norm = provider._normalize_ccxt_symbol("ETHUSD")
    print(f"  ETHUSD -> {norm}")
    
    try:
        print(f"Attempting fetch_ticker for {norm}...")
        ticker = provider.get_ticker("ETHUSD")
        print(f"  Ticker success: {ticker}")
    except Exception as e:
        print(f"  Ticker failed: {e}")

if __name__ == "__main__":
    test_normalization()
