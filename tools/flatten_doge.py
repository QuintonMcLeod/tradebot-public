
import os
import sys
import logging

# Setup path to src
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, src_path)

from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.config.models import TradingProfileSettings
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def main():
    load_dotenv()
    print("Initializing Broker for manual flatten...")
    
    try:
        # Create a valid profile with required fields
        profile = TradingProfileSettings(
            name="manual_ops",
            candle_timeframe="5m",
            market_poll_interval_seconds=2,
            ai_decision_interval_seconds=5
        )
        broker = CCXTExchangeBroker(profile=profile)
        
        target = "DOGEUSD"
        print(f"Attempting to flatten {target}...")
        
        # Call the broker's flatten logic
        broker.flatten_symbol(target)
        
        print(f"Successfully sent flatten commands for {target}.")
        
    except Exception as e:
        print(f"Failed to flatten: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
