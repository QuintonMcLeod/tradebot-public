
import logging
import os
import sys
import asyncio

# Setup path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.config.loader import load_settings

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CoinbaseNavCheck")

async def test_connection():
    try:
        settings = load_settings() 
        # Check active profile
        profile_name = settings.app.profile_name
        logger.info(f"Loaded Active Profile: {profile_name}")
        
        if profile_name != "coinbase_futures":
            logger.error(f"Active Profile is NOT coinbase_futures (It is {profile_name}). Update .env!")
            return

        broker = CCXTExchangeBroker(settings)
        # Manually force futures options for testing
        logger.info("[Test] Re-initializing exchange with defaultType='future'...")
        import ccxt
        
        raw_secret = os.environ.get("CCXT_SECRET")
        if raw_secret and "\\n" in raw_secret:
            raw_secret = raw_secret.replace("\\n", "\n")

        broker._exchange = ccxt.coinbase({
            'apiKey': os.environ.get("CCXT_API_KEY"),
            'secret': raw_secret,
            'options': {'defaultType': 'future'}
        })
        await broker._exchange.load_markets()
        logger.info("[Test] Markets re-loaded with future option.")

        logger.info("Broker Connected.")
        
        # Test Nano Ether Fetch
        symbol = "ETP" # Or "ETH/USD:ETH"? Let's see what works.
        logger.info(f"Fetching Ticker for {symbol}...")
        
        ticker = broker._safe_fetch_ticker(symbol)
        
        if ticker:
            logger.info(f"SUCCESS: {symbol} Last={ticker.last}, Bid={ticker.bid}, Ask={ticker.ask}")
            logger.info(f"Nano Contract Value: ${ticker.last * 0.1:.2f} (approx)")
        else:
            logger.error(f"FAILED to fetch {symbol}. Broker might need specific symbol mapping (e.g. 'ETH-NANO'?).")
            
            # Debug: List available markets
            logger.info("Listing first 10 markets keys for debugging:")
            markets = broker._exchange.markets
            keys = list(markets.keys())[:20]
            logger.info(f"Markets: {keys}")

    except Exception as e:
        logger.error(f"Connection Test Failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_connection())
