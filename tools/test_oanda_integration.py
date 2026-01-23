import os
import logging
from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
from tradebot_sci.market.oanda_provider import OandaMarketDataProvider
from tradebot_sci.config.models import TradingProfileSettings

logging.basicConfig(level=logging.INFO)

def test_oanda_init():
    # Placeholder profile
    profile = TradingProfileSettings(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=300
    )
    
    print("Testing OANDA Provider Init...")
    try:
        provider = OandaMarketDataProvider("123-456", "dummy_key")
        print("OANDA Provider Initialized Successfully.")
    except Exception as e:
        print(f"OANDA Provider Init Failed: {e}")

    print("Testing OANDA Broker Init...")
    try:
        broker = OandaExchangeBroker("123-456", "dummy_key", profile)
        print("OANDA Broker Initialized Successfully.")
    except Exception as e:
        print(f"OANDA Broker Init Failed: {e}")

if __name__ == "__main__":
    test_oanda_init()
