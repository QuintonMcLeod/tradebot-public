
import os
import sys
import unittest.mock

# MOCK ib_insync BEFORE import for environment compatibility
sys.modules["ib_insync"] = unittest.mock.MagicMock()

import json
import logging
from datetime import datetime, timezone
from typing import List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from tradebot_sci.config.models import Settings, UserConfig
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend_enums import TrendDirection

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("tradebot_sci")

class LocalJSONProvider:
    """Reads candles from tools/download_forex_data.py output format."""
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._cache = {}

    def fetch_historical_candles(self, symbol, timeframe, start_date, end_date, **kwargs):
        # Map symbol "EUR/USD" -> "EURUSD"
        file_symbol = symbol.replace("/", "")
        file_name = f"{file_symbol}_{timeframe}.json"
        path = os.path.join(self.data_dir, file_name)
        
        if path not in self._cache:
            if not os.path.exists(path):
                print(f"[WARN] Data file not found: {path}")
                return []
            
            with open(path, "r") as f:
                raw_data = json.load(f)
            
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
         # Not used in current simple flow, or used by cache logic if engine calls it
         # The engine calls this! We need to return the 'current' slice based on simulation time.
         # But the engine uses market_provider._cache to set 'current' candles before calling this.
         # See backtester.py line 513: self.market_provider._cache[cache_key] = current_candles
         # So we just need to return that cache entry.
         cache_key = f"{symbol}:{timeframe}_current"
         return self._cache.get(cache_key, [])[-limit:]

    def get_latest_snapshot(self, symbol, timeframe):
        # Stub for strategy. Logic usually needs this.
        # We can construct a basic one.
        # This is enough to pass basic strategy checks if they don't dig too deep into trend objects.
        
        # Real backtester creates snapshot from candles.
        # We should try to use the logic from backtester? 
        # Backtester logic calls self.market_provider.get_latest_snapshot
        
        # Let's simple-mock it for now to avoid complexity of trend calculation deps
        # Or better: don't implement it and let the engine crash? 
        # The engine USES get_latest_snapshot at line 674.
        
        # We need a proper implementation or copy-paste from historical provider.
        # Let's try to minimal-mock:
        from tradebot_sci.market.trend import infer_trend_from_swings
        from tradebot_sci.simulation.utils import resample_candles

        # Use helper from provider or import
        # We need to calculate trend dynamically
        candles = self.get_latest_candles(symbol, timeframe, 300)
        
        # Resample to HTF (e.g. 15m) for trend
        # For simplicity in this script, assume 15m HTF from 1m candles
        if timeframe == "1m":
             htf_candles = resample_candles(candles, 900) # 15m
        else:
             htf_candles = candles
             
        # Calculate Trend
        trend_htf = infer_trend_from_swings(
            htf_candles[-20:] if len(htf_candles) > 20 else htf_candles,
            swing_lookback=3,
            min_swings=2,
            strength_floor=0.1
        )
        
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_htf, # approximate
        )

def run_friday_simulation():
    print("=== STARTING REAL DATA FRIDAY BACKTEST (5M FOREX) ===")

    # 1. Configure Settings
    from tradebot_sci.config.models import (
        Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
        TradingProfileSettings
    )

    # ScalpProfile: 5-minute candles for higher-resolution Forex backtesting
    # Kraken provides 5m data coverage for Friday Jan 23, 2026
    # (1m data from Kraken is limited to ~5 hours)
    profile = TradingProfileSettings(
        strategy_variant="rubberband_reaper",
        candle_timeframe="5m",               # Use 5m since 1m files are not in repo
        market_poll_interval_seconds=300,
        ai_decision_interval_seconds=300,
        htf_timeframe="15m",                 # HTF step down
        ltf_timeframe="5m",
        trend_window=30,                     # Smoother trend on 5m
        trend_min_swings=3,
        trend_strength_floor=0.1,
        risk_per_trade_pct=0.20,
        htf_neutral_exit_bars=0,
        max_pyramid_entries=3
    )

    # Use Forex pairs - 5m data has full Friday coverage from Kraken
    symbols = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]

    settings = Settings(
        app=AppSettings(profile_name="FridayTest"),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"), # Dummy
        market=MarketSettings(symbols=["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]),
        profiles={"FridayTest": profile},
        # Optional sections use defaults
    )

    # [CHANGE] DISABLE FRIDAY FADE TO TEST RISK
    type(UserConfig).FRIDAY_FADE_ENABLED = property(lambda self: False)


    # 2. Init Backtester
    # Use ib=None, passing our custom provider later
    backtester = Backtester(ib=None, settings=settings, ai_client=None)

    # data_dir logic handles path automatically
    data_dir = os.path.join(os.path.dirname(__file__), "../data/forex_backtest")
    backtester.market_provider = LocalJSONProvider(data_dir)

    # [FIX] Monkeypatch market hours to allow 24h Forex trading
    backtester._is_market_hours_utc = lambda ts: True

    # 3. Define Time Range (Jan 23, 2026 - Friday)
    # Morning: 8 AM - 12 PM EST (13:00 - 17:00 UTC) - Normal risk trades
    # Afternoon: 12 PM - 5 PM EST (17:00 - 22:00 UTC) - Friday Fade capped at 0.25%
    start_date = datetime(2026, 1, 30, 8, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 30, 23, 0, 0, tzinfo=timezone.utc)

    print(f"Time Range: {start_date} -> {end_date}")
    print(f"Symbols: {symbols}")
    print(f"Timeframe: 5m (Forex High-Resolution)")
    print(f"Friday Fade: ENABLED (Risk capped to 0.25% after 12 PM EST)")
    print()

    try:
        results = backtester.run_backtest(
            initial_capital=25.0,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )
        
        print("\n=== BACKTEST RESULTS ===")
        print(f"Final Capital: ${results.final_capital:.2f}")
        print(f"Profit/Loss: ${results.total_pnl:.2f}")
        print(f"Total Trades: {len(results.trades)}")
        
        for t in results.trades:
            print(f"[{t.exit_time.strftime('%H:%M')}] {t.symbol} {t.direction} {t.exit_reason}")
            print(f"  Entry: {t.entry_price:.5f} | Exit: {t.exit_price:.5f} | Size: {t.size:.2f} | PnL: ${t.pnl:.4f}")
            
    except Exception as e:
        print(f"\n[ERROR] Backtest run failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_friday_simulation()
