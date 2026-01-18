#!/usr/bin/env python3
"""Test the strategy engine directly to see what it decides."""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

from ib_insync import IB, util
from tradebot_sci.config.loader import load_settings
from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.market.contracts import build_contract
from tradebot_sci.market.models import Candle, MarketSnapshot
from tradebot_sci.market.trend import infer_trend_from_swings

def main():
    print("=" * 60)
    print("DIRECT STRATEGY TEST")
    print("=" * 60)
    print()

    # Load settings
    settings = load_settings()
    profile = settings.get_active_profile()

    print(f"Profile: {settings.app.profile_name}")
    print(f"Candle timeframe: {profile.candle_timeframe}")
    print(f"HTF timeframe: {profile.htf_timeframe}")
    print(f"LTF timeframe: {profile.ltf_timeframe}")
    print(f"Structure score threshold: {profile.structure_score_threshold}")
    print()

    # Connect to IBKR
    print("Connecting to IBKR...")
    ib = IB()
    ib.connect(settings.broker.host, settings.broker.port, clientId=997)
    print("  Connected")
    print()

    try:
        # Fetch recent SPY data
        symbol = "SPY"
        contract = build_contract(symbol)
        qualified = ib.qualifyContracts(contract)

        if not qualified:
            print(f"ERROR: Could not qualify {symbol}")
            return 1

        print(f"Fetching recent 5-minute candles for {symbol}...")
        bars = util.run(
            ib.reqHistoricalDataAsync(
                qualified[0],
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
            )
        )

        candles = [
            Candle(
                timestamp=bar.date,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
            )
            for bar in bars
        ]

        print(f"  Fetched {len(candles)} candles")
        if candles:
            print(f"  First: {candles[0].timestamp}")
            print(f"  Last:  {candles[-1].timestamp}")
        print()

        # Build market snapshot
        htf_window = profile.trend_window
        ltf_window = profile.ltf_trend_window or htf_window

        trend_htf = infer_trend_from_swings(
            candles[-htf_window:] if len(candles) >= htf_window else candles,
            swing_lookback=profile.trend_swing_lookback,
            min_swings=profile.trend_min_swings,
            strength_floor=profile.trend_strength_floor,
        )

        trend_ltf = infer_trend_from_swings(
            candles[-ltf_window:] if len(candles) >= ltf_window else candles,
            swing_lookback=profile.trend_swing_lookback,
            min_swings=profile.trend_min_swings,
            strength_floor=profile.trend_strength_floor,
        )

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=profile.candle_timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=candles[-htf_window:] if len(candles) >= htf_window else candles,
            ltf_candles=candles[-ltf_window:] if len(candles) >= ltf_window else candles,
            htf_timeframe=profile.htf_timeframe,
            ltf_timeframe=profile.ltf_timeframe or profile.candle_timeframe,
        )

        print(f"Market snapshot built:")
        print(f"  HTF trend: {trend_htf}")
        print(f"  LTF trend: {trend_ltf}")
        print(f"  Latest price: ${candles[-1].close:.2f}")
        print()

        # Initialize strategy engine with a mock market provider
        class MockMarketProvider:
            def __init__(self, snapshot):
                self.snapshot = snapshot

            def get_latest_candles(self, symbol, timeframe, limit):
                return self.snapshot.candles[-limit:]

            def get_latest_snapshot(self, symbol, timeframe):
                return self.snapshot

        ai_client = TradeSciAIClient(settings.ai)
        market_provider = MockMarketProvider(snapshot)

        engine = StrategyEngine(
            ai_client=ai_client,
            market_provider=market_provider,
            profile=profile,
            symbol=symbol,
        )

        print("Calling strategy engine to make decision...")
        print()

        decision = engine.decide(
            timeframe=profile.candle_timeframe,
            open_position=None,
            snapshot=snapshot,
        )

        print("=" * 60)
        print("DECISION RESULT")
        print("=" * 60)
        print()
        print(f"Action: {decision.action}")
        print(f"Confidence: {decision.confidence:.2f}")
        print(f"Stop Loss: ${decision.stop_loss:.2f}" if decision.stop_loss else "Stop Loss: None")
        print(f"Take Profit: ${decision.take_profit:.2f}" if decision.take_profit else "Take Profit: None")
        print()
        print(f"Reasoning:")
        print(f"  {decision.reasoning}")
        print()

        return 0

    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
