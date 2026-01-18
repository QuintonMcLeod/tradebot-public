
import ccxt
import time
from datetime import datetime, timedelta

def main():
    print("Testing CCXT Historical Data Fetch (Coinbase)")
    try:
        exchange = ccxt.coinbase()
        exchange.load_markets()
        
        symbol = "BTC/USD"
        timeframe = "1h"
        limit = 24
        
        print(f"Fetching {limit} candles for {symbol} ({timeframe})...")
        
        # Calculate start time (24 hours ago)
        since = exchange.parse8601((datetime.utcnow() - timedelta(hours=48)).isoformat())
        
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        
        print(f"Fetched {len(ohlcv)} candles.")
        for candle in ohlcv[:3]:
            # Timestamp is in ms
            ts = datetime.fromtimestamp(candle[0] / 1000)
            print(f"  {ts}: Open={candle[1]}, High={candle[2]}, Low={candle[3]}, Close={candle[4]}, Vol={candle[5]}")
            
        print("... (more) ...")
        
        if len(ohlcv) > 0:
            print("✅ Success: CCXT supports historical data for Coinbase.")
        else:
            print("❌ Failure: No candles returned.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
