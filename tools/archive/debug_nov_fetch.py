
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
from tradebot_sci.config.loader import load_settings

def debug_fetch():
    settings = load_settings()
    provider = CCXTHistoricalDataProvider(settings)
    
    symbol = "ETH/USD:USD-260130"
    timeframe = "5m"
    start_date = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 11, 2, tzinfo=timezone.utc)
    
    print(f"DEBUG: Fetching {symbol} for {start_date}")
    
    candles = provider.fetch_historical_candles(symbol, timeframe, start_date, end_date)
    print(f"Result: {len(candles)} candles")
    if candles:
        print(f"First: {candles[0]}")
        print(f"Last: {candles[-1]}")
    else:
        print("NO DATA RETURNED")

if __name__ == "__main__":
    debug_fetch()
