
import os
import json
import logging
from datetime import datetime, timezone
from typing import List

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend import infer_trend_from_swings
from tradebot_sci.simulation.utils import resample_candles
from tools.utils.downloader import ensure_data_exists

logger = logging.getLogger(__name__)

class LocalJSONProvider:
    """Reads candles from tools/download_forex_data.py output format."""
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._cache = {}

    def fetch_historical_candles(self, symbol, timeframe, start_date, end_date):
        # Map symbol "EUR/USD" -> "EURUSD"
        file_symbol = symbol.replace("/", "")
        file_name = f"{file_symbol}_{timeframe}.json"
        path = os.path.join(self.data_dir, file_name)
        
        if path not in self._cache:
            if not os.path.exists(path):
                # [AUTO-DOWNLOAD FEATURE]
                print(f"[PROVIDER] Data missing for {symbol}. Attempting auto-download...")
                success = ensure_data_exists(symbol, timeframe, start_date, end_date, self.data_dir)
                if not success:
                    print(f"[WARN] Data file not found and download failed: {path}")
                    return []
            
            try:
                with open(path, "r") as f:
                    raw_data = json.load(f)
            except Exception as e:
                print(f"[ERROR] Failed to read {path}: {e}")
                return []
            
            candles = []
            for item in raw_data:
                ts = datetime.fromisoformat(item["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                
                c = Candle(
                    timestamp=ts,
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"])
                )
                candles.append(c)
            self._cache[path] = candles
            print(f"[INFO] Loaded {len(candles)} candles from {file_name}")
            
        # Filter by date range
        filtered = [
            c for c in self._cache[path] 
            if start_date <= c.timestamp <= end_date
        ]
        return filtered

    def get_latest_candles(self, symbol, timeframe, limit):
         # The engine uses market_provider._cache to set 'current' candles before calling this.
         # So we just need to return that cache entry if patched, or fallback to file.
         # Actually backtester.py populates its own cache.
         # But implementing this allows direct lookups if needed.
         # For consistency with Backtester:
         cache_key = f"{symbol}:{timeframe}_current"
         # This assumes the Backtester has monkey-patched or populated this cache key
         # If not, we can't really answer "latest" relative to simulation time without extra context.
         # But the specific `Backtester` implementation manages `self.market_provider._cache` directly.
         # So we should be good if we inherit or just expose ._cache.
         return self._cache.get(cache_key, [])[-limit:]

    def get_latest_snapshot(self, symbol, timeframe):
        # Use helper checks
        candles = self.get_latest_candles(symbol, timeframe, 300)
        
        # Resample to HTF (e.g. 15m) for trend if needed
        # Assuming 15m HTF from 1m/5m candles for simplistic trend
        # Or just use the candles as-is if they are already HTF?
        # A common pattern is:
        if timeframe in ["1m", "5m"]:
             htf_candles = resample_candles(candles, 900) # 15m
        else:
             htf_candles = candles
             
        # Calculate Trend
        # Use longer window (60) and swing_lookback=2 to match the successful "Direct Script" logic
        trend_htf = infer_trend_from_swings(
            htf_candles[-60:] if len(htf_candles) > 60 else htf_candles,
            swing_lookback=2,
            min_swings=2,
            strength_floor=0.1
        )
        
        # For LTF trend, use raw candles
        trend_ltf = infer_trend_from_swings(
            candles[-60:] if len(candles) > 60 else candles,
            swing_lookback=2,
            min_swings=2,
            strength_floor=0.1
        )
        
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
        )
