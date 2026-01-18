#!/usr/bin/env python3
"""Minimal backtest test to debug why AI isn't being called."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ib_insync import IB
from tradebot_sci.config.loader import load_settings
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.simulation.backtester import Backtester, HistoricalMarketDataProvider

def main():
    print("=" * 60)
    print("MINIMAL BACKTEST TEST")
    print("=" * 60)
    print()

    settings = load_settings()
    profile = settings.get_active_profile()

    print(f"Profile: {settings.app.profile_name}")
    print(f"Decision interval: {profile.ai_decision_interval_seconds}s")
    print(f"Candle timeframe: {profile.candle_timeframe}")
    print()

    # Connect
    ib = IB()
    ib.connect(settings.broker.host, settings.broker.port, clientId=996)
    print("Connected to IBKR")
    print()

    try:
        # Create market provider and fetch data
        provider = HistoricalMarketDataProvider(ib, settings)

        symbol = "SPY"
        timeframe = profile.candle_timeframe
        start_date = datetime(2024, 11, 11, tzinfo=ZoneInfo("UTC"))
        end_date = datetime(2024, 11, 12, tzinfo=ZoneInfo("UTC"))  # Just 1 day

        print(f"Fetching {symbol} {timeframe} candles from {start_date.date()} to {end_date.date()}...")
        candles = provider.fetch_historical_candles(symbol, timeframe, start_date, end_date)
        print(f"Fetched {len(candles)} candles")

        if candles:
            print(f"First candle: {candles[0].timestamp}")
            print(f"Last candle: {candles[-1].timestamp}")

        print()
        print("Now simulating bar-by-bar loop...")
        print()

        # Calculate time increment
        tf_seconds = 300  # 5 minutes
        decision_bar_interval = max(1, profile.ai_decision_interval_seconds // tf_seconds)

        print(f"Timeframe: {tf_seconds}s ({tf_seconds//60}m)")
        print(f"Decision interval: {profile.ai_decision_interval_seconds}s")
        print(f"Decision bar interval: {decision_bar_interval} bars")
        print()

        # Simulate loop
        current_time = start_date
        bar_index = 0
        decision_count = 0

        while current_time <= end_date:
            # Update cache
            current_candles = [c for c in candles if c.timestamp <= current_time]
            cache_key = f"{symbol}:{timeframe}_current"
            provider._cache[cache_key] = current_candles

            # Check if we should make decision
            if bar_index % decision_bar_interval == 0:
                if len(current_candles) >= 100:  # Need enough candles
                    decision_count += 1
                    if decision_count <= 3:  # Show first 3
                        print(f"Bar {bar_index}: {current_time.strftime('%Y-%m-%d %H:%M')} - Would call AI (have {len(current_candles)} candles)")

            current_time += timedelta(seconds=tf_seconds)
            bar_index += 1

        print()
        print(f"Total bars: {bar_index}")
        print(f"Total decision points: {decision_count}")
        print()

        if decision_count == 0:
            print("ERROR: No decision points! This explains why 0 trades.")
            print(f"Need at least 100 candles, but starting with {len([c for c in candles if c.timestamp <= start_date])} at start_date")

        return 0

    finally:
        ib.disconnect()

if __name__ == "__main__":
    sys.exit(main())
