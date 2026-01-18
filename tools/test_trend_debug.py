#!/usr/bin/env python3
"""Debug script to see what HTF/LTF trends are actually being detected."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.data.ibkr_client import IBKRClient
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.data.models import MarketSnapshot
from ib_insync import Stock, util

def main():
    settings = load_settings()
    profile = settings.get_active_profile()

    print("Connecting to IBKR...")
    ib_client = IBKRClient(settings.broker)
    ib_client.connect()
    print("  Connected\n")

    # Test parameters
    symbol = "SPY"
    start_date = datetime(2024, 11, 11, 14, 30, tzinfo=ZoneInfo("America/New_York"))  # Market open

    # Fetch candles
    contract = Stock(symbol, "SMART", "USD")
    end_date = start_date + timedelta(hours=1)

    print(f"Fetching candles for {symbol} at {start_date}...")
    bars = util.run(
        ib_client.ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
    )

    if not bars:
        print("No bars fetched!")
        return

    print(f"Fetched {len(bars)} bars\n")

    # Create strategy engine
    engine = StrategyEngine(settings, ib_client)

    # Build market snapshot
    from tradebot_sci.data.models import Candle
    candles = [
        Candle(
            timestamp=bar.date.replace(tzinfo=ZoneInfo("UTC")),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=int(bar.volume),
        )
        for bar in bars
    ]

    print(f"Building market snapshot at {start_date}...")
    snapshot = MarketSnapshot(
        symbol=symbol,
        candles=candles,
        timeframe="5m",
        timestamp=start_date,
    )

    # Enrich with technical analysis
    from tradebot_sci.analysis.technical import enrich_snapshot
    snapshot = enrich_snapshot(snapshot, profile)

    # Print trend information
    print(f"\n{'='*60}")
    print(f"TREND ANALYSIS FOR {symbol} at {start_date}")
    print(f"{'='*60}\n")

    print(f"HTF (4h) Trend:")
    print(f"  Direction: {snapshot.trend_htf.direction}")
    print(f"  Strength: {snapshot.trend_htf.strength:.3f}")
    print()

    print(f"LTF (15m) Trend:")
    print(f"  Direction: {snapshot.trend_ltf.direction}")
    print(f"  Strength: {snapshot.trend_ltf.strength:.3f}")
    print()

    # Check htf_align logic
    ltf_dir = snapshot.trend_ltf.direction
    htf_dir = snapshot.trend_htf.direction
    htf_align = (
        ltf_dir != "neutral"  # LTF must be trending
        and (htf_dir == "neutral" or htf_dir == ltf_dir)  # HTF can be neutral or aligned with LTF
    )

    print(f"Alignment Check:")
    print(f"  LTF trending: {ltf_dir != 'neutral'}")
    print(f"  HTF neutral or aligned: {htf_dir == 'neutral' or htf_dir == ltf_dir}")
    print(f"  htf_align: {htf_align}")
    print()

    # Check sweep and continuation
    sweep = engine._detect_sweep(snapshot)
    continuation = engine._detect_continuation(snapshot, sweep)

    print(f"ICC Gates:")
    print(f"  Sweep detected: {sweep is not None}")
    if sweep:
        print(f"    Direction: {sweep.direction}")
        print(f"    Level: {sweep.level:.2f}")
    print(f"  Continuation detected: {continuation is not None}")
    if continuation:
        print(f"    Pattern: {continuation.pattern}")
        print(f"    Zone: {continuation.zone_low:.2f} - {continuation.zone_high:.2f}")
    print()

    # Try calling decision maker
    print("Calling decision maker...")
    decision = engine.make_decision(snapshot, open_position=None)
    print(f"  Action: {decision.action}")
    print(f"  Urgency: {decision.urgency}")
    print(f"  Notes: {decision.notes}")

    ib_client.disconnect()

if __name__ == "__main__":
    main()
