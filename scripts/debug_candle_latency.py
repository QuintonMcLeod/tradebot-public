from datetime import datetime, timezone
import os
import json
from tradebot_sci.config.loader import get_settings
from tradebot_sci.runtime.provider_factory import build_market_provider
from tradebot_sci.market.symbols import SUPPORTED_SYMBOLS

def debug_candles():
    settings = get_settings()
    profile = settings.get_active_profile()
    
    # Try to connect to provider
    print(f"Active Profile: {settings.app.profile_name}")
    print(f"Timeframe: {profile.candle_timeframe}")
    
    provider = build_market_provider(settings, profile, shared_ib=None)
    
    symbols = ["EURUSD", "BTCUSD", "LINKUSD"]
    
    now = datetime.now(timezone.utc)
    print(f"Current UTC: {now}")
    
    for symbol in symbols:
        try:
            print(f"\n--- {symbol} ---")
            candles = provider.get_latest_candles(symbol, profile.candle_timeframe, limit=5)
            if not candles:
                print(f"No candles returned for {symbol}")
                continue
                
            for i, c in enumerate(candles):
                print(f"Candle {i}: {c.timestamp} (UTC) | Close: {c.close}")
            
            last_ts = candles[-1].timestamp
            diff = now - last_ts
            print(f"Difference (Now - Last Candle): {diff}")
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")

if __name__ == "__main__":
    debug_candles()
