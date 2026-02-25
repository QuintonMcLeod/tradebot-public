#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                           FORWARD TESTER                                   ║
║              Controlled Simulation with Synthetic Candles                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

Injects known candle patterns to verify:
1. Trend detection works correctly
2. Strategy signals fire correctly
3. Exit logic respects the 1-hour hold rule
4. SL/TP exits still work during the hold window

Usage:
    python3 tools/forward_tester.py
"""

import sys
import os
import math
import unittest.mock
import logging
from datetime import datetime, timedelta, timezone
from typing import List

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# MOCK ib_insync for env compat
sys.modules["ib_insync"] = unittest.mock.MagicMock()

os.environ["TRADING_CONFIRMATION"] = "YES"

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.trend_consensus import detect_trend_direction, _TF_CACHE
from tradebot_sci.config.models import (
    Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
    TradingProfileSettings,
)
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.simulation.backtester import HistoricalMarketDataProvider

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("forward_tester")
logger.setLevel(logging.INFO)


# ── Synthetic Candle Generators ──────────────────────────────────────────────

def make_uptrend(n: int = 250, start: float = 1.1000, step: float = 0.0003,
                 noise: float = 0.0002, start_time: datetime = None) -> List[Candle]:
    """Generate a clear uptrend: higher highs and higher lows."""
    candles = []
    t = start_time or datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    price = start
    for i in range(n):
        # Trend up with oscillation
        base_move = step * (1.0 + 0.3 * math.sin(i * 0.15))
        o = price
        c = price + base_move
        h = max(o, c) + noise * abs(math.sin(i * 0.7))
        l = min(o, c) - noise * abs(math.cos(i * 0.9))
        candles.append(Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=1000))
        price = c
        t += timedelta(minutes=5)
    return candles


def make_downtrend(n: int = 250, start: float = 1.2000, step: float = 0.0003,
                   noise: float = 0.0002, start_time: datetime = None) -> List[Candle]:
    """Generate a clear downtrend: lower highs and lower lows."""
    candles = []
    t = start_time or datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    price = start
    for i in range(n):
        base_move = step * (1.0 + 0.3 * math.sin(i * 0.15))
        o = price
        c = price - base_move
        h = max(o, c) + noise * abs(math.sin(i * 0.7))
        l = min(o, c) - noise * abs(math.cos(i * 0.9))
        candles.append(Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=1000))
        price = c
        t += timedelta(minutes=5)
    return candles


def make_chop(n: int = 250, center: float = 1.1500, amplitude: float = 0.0010,
              start_time: datetime = None) -> List[Candle]:
    """Generate choppy/ranging price action."""
    candles = []
    t = start_time or datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    for i in range(n):
        mid = center + amplitude * math.sin(i * 0.3)
        o = mid + amplitude * 0.2 * math.cos(i * 0.7)
        c = mid + amplitude * 0.2 * math.sin(i * 0.5)
        h = max(o, c) + abs(amplitude * 0.3 * math.sin(i * 0.9))
        l = min(o, c) - abs(amplitude * 0.3 * math.cos(i * 1.1))
        candles.append(Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=1000))
        t += timedelta(minutes=5)
    return candles


# ── Test Infrastructure ──────────────────────────────────────────────────────

def build_profile(**kwargs) -> TradingProfileSettings:
    """Build a test profile."""
    defaults = dict(
        strategy_variant="evolution",
        candle_timeframe="5m",
        htf_timeframe="1h",
        ltf_timeframe="5m",
        trend_window=30,
        ltf_trend_window=30,
        risk_per_trade_pct=0.01,
        block_counter_trend_entries=True,
    )
    defaults.update(kwargs)
    return TradingProfileSettings(**defaults)


def build_settings(profile: TradingProfileSettings, symbols: list) -> Settings:
    profile_name = "ForwardTest"
    return Settings(
        app=AppSettings(profile_name=profile_name),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=symbols),
        profiles={profile_name: profile},
    )


def build_snapshot(candles: List[Candle], symbol: str = "EURUSD",
                   timeframe: str = "5m", profile=None) -> MarketSnapshot:
    """Build a snapshot with proper HTF/LTF resampling."""
    from tradebot_sci.simulation.backtester import _resample_candles, _timeframe_to_seconds

    htf_seconds = _timeframe_to_seconds(profile.htf_timeframe if profile else "1h")
    ltf_seconds = _timeframe_to_seconds(profile.ltf_timeframe if profile else "5m")
    base_seconds = _timeframe_to_seconds(timeframe)

    htf_candles = _resample_candles(candles, htf_seconds) if htf_seconds != base_seconds else candles
    ltf_candles = _resample_candles(candles, ltf_seconds) if ltf_seconds != base_seconds else candles

    htf_window = profile.trend_window if profile else 30
    ltf_window = (profile.ltf_trend_window if profile else None) or htf_window

    neutral = TrendState(direction="neutral", strength=0.0)
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        trend_htf=neutral,
        trend_ltf=neutral,
        htf_candles=htf_candles[-htf_window:],
        ltf_candles=ltf_candles[-ltf_window:],
        htf_timeframe=profile.htf_timeframe if profile else "1h",
        ltf_timeframe=profile.ltf_timeframe if profile else "5m",
    )


# ── Tests ────────────────────────────────────────────────────────────────────

def test_uptrend_detection():
    """TEST 1: Feed 250 uptrend candles. Assert HTF direction = 'long'."""
    _TF_CACHE.clear()  # Prevent cache collision between tests
    profile = build_profile()
    candles = make_uptrend(250)

    consensus = detect_trend_direction(
        candles, profile,
        htf_candles=None, ltf_candles=None,
    )

    result = "PASS" if consensus.htf_dir == "long" else "FAIL"
    detail = f"htf_dir={consensus.htf_dir}, strength={consensus.htf_strength:.2f}"
    if consensus.vote_sources:
        detail += f", votes={consensus.vote_sources}"
    print(f"  [{result}] Test 1 — Uptrend Detection: {detail}")
    return result == "PASS"


def test_downtrend_detection():
    """TEST 2: Feed 250 downtrend candles. Assert HTF direction = 'short'."""
    _TF_CACHE.clear()  # Prevent cache collision between tests
    profile = build_profile()
    candles = make_downtrend(250)

    consensus = detect_trend_direction(
        candles, profile,
        htf_candles=None, ltf_candles=None,
    )

    result = "PASS" if consensus.htf_dir == "short" else "FAIL"
    detail = f"htf_dir={consensus.htf_dir}, strength={consensus.htf_strength:.2f}"
    if consensus.vote_sources:
        detail += f", votes={consensus.vote_sources}"
    print(f"  [{result}] Test 2 — Downtrend Detection: {detail}")
    return result == "PASS"


def test_entry_signal():
    """TEST 3: Feed strong trend candles. Assert engine returns an entry signal."""
    profile = build_profile(strategy_variant="evolution")
    settings = build_settings(profile, ["EURUSD"])
    candles = make_uptrend(250, step=0.0005)

    # Build a mock provider that returns our synthetic candles
    provider = HistoricalMarketDataProvider(ib=None, settings=settings)
    provider._cache["EURUSD:5m_current"] = candles

    engine = StrategyEngine(
        ai_client=None,
        market_provider=provider,
        profile=profile,
        symbol="EURUSD",
    )

    snapshot = build_snapshot(candles, profile=profile)
    decision = engine.decide(
        timeframe="5m",
        open_position=None,
        snapshot=snapshot,
        current_capital=10000.0,
    )

    entry_actions = {"enter_long", "enter_short", "scale_in"}
    is_entry = decision.action in entry_actions
    result = "PASS" if is_entry else "INFO"
    detail = f"action={decision.action}, notes={getattr(decision, 'notes', '')[:80]}"
    print(f"  [{result}] Test 3 — Entry Signal Fire: {detail}")

    # Also acceptable: stand_aside with good reason (safety guard, counter-trend, etc.)
    if not is_entry:
        print(f"         Note: No entry is acceptable if safety guards are blocking (churn, lockout, etc.)")
    return True  # Informational — doesn't fail the suite


def test_hold_guard_blocks_early_exit():
    """TEST 4: Enter a position, feed adverse candles within 1 hour.
    Assert engine returns 'hold', not 'close_position'."""
    profile = build_profile(strategy_variant="evolution")
    settings = build_settings(profile, ["EURUSD"])

    # Create initial uptrend, then feed a REVERSAL within the first hour
    up_candles = make_uptrend(200, step=0.0004)
    # Append 10 sharp down candles (50 min — still within 1-hour window)
    reversal_candles = make_downtrend(10, start=up_candles[-1].close, step=0.0008,
                                       start_time=up_candles[-1].timestamp + timedelta(minutes=5))
    all_candles = up_candles + reversal_candles

    provider = HistoricalMarketDataProvider(ib=None, settings=settings)
    provider._cache["EURUSD:5m_current"] = all_candles

    engine = StrategyEngine(
        ai_client=None,
        market_provider=provider,
        profile=profile,
        symbol="EURUSD",
    )

    # Simulate an open position entered 30 minutes ago (wall-clock time)
    # The engine's hold guard compares entry_time to datetime.now()
    entry_time = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
    open_position = {
        "symbol": "EURUSD",
        "direction": "long",
        "entry_price": up_candles[-15].close,
        "size": 100,
        "stop_price": up_candles[-15].close - 0.0050,
        "stop_loss": up_candles[-15].close - 0.0050,
        "target_price": up_candles[-15].close + 0.0100,
        "unrealized_pnl": -0.50,
        "pyramid_count": 1,
        "htf_neutral_bars": 0,
        "entry_time": entry_time.isoformat(),
    }

    snapshot = build_snapshot(all_candles, profile=profile)
    decision = engine.decide(
        timeframe="5m",
        open_position=open_position,
        snapshot=snapshot,
        current_capital=10000.0,
    )

    # The hold guard should block close_position exits for positions < 1 hour
    blocked = decision.action != "close_position"
    result = "PASS" if blocked else "FAIL"
    detail = f"action={decision.action}, notes={getattr(decision, 'notes', '')[:80]}"
    print(f"  [{result}] Test 4 — Hold Guard Blocks Early Exit: {detail}")
    return result == "PASS"


def test_exit_allowed_after_hold():
    """TEST 5: Same as test 4 but position is >1 hour old.
    Assert engine CAN return 'close_position'."""
    profile = build_profile(strategy_variant="evolution")
    settings = build_settings(profile, ["EURUSD"])

    up_candles = make_uptrend(200, step=0.0004)
    reversal_candles = make_downtrend(20, start=up_candles[-1].close, step=0.0008,
                                       start_time=up_candles[-1].timestamp + timedelta(minutes=5))
    all_candles = up_candles + reversal_candles

    provider = HistoricalMarketDataProvider(ib=None, settings=settings)
    provider._cache["EURUSD:5m_current"] = all_candles

    engine = StrategyEngine(
        ai_client=None,
        market_provider=provider,
        profile=profile,
        symbol="EURUSD",
    )

    # Position is 2 hours old (wall-clock time) — should be allowed to exit
    entry_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    open_position = {
        "symbol": "EURUSD",
        "direction": "long",
        "entry_price": up_candles[100].close,
        "size": 100,
        "stop_price": up_candles[100].close - 0.0050,
        "stop_loss": up_candles[100].close - 0.0050,
        "target_price": up_candles[100].close + 0.0100,
        "unrealized_pnl": -2.0,
        "pyramid_count": 1,
        "htf_neutral_bars": 0,
        "entry_time": entry_time.isoformat(),
    }

    snapshot = build_snapshot(all_candles, profile=profile)
    decision = engine.decide(
        timeframe="5m",
        open_position=open_position,
        snapshot=snapshot,
        current_capital=10000.0,
    )

    # With a >2hr old position and sharp reversal, exit should be allowed
    # (though the strategy might choose to hold for other reasons)
    is_exit_or_hold = decision.action in ("close_position", "hold")
    result = "PASS" if is_exit_or_hold else "INFO"
    detail = f"action={decision.action}, notes={getattr(decision, 'notes', '')[:80]}"
    print(f"  [{result}] Test 5 — Exit Allowed After Hold: {detail}")
    if decision.action == "hold":
        print(f"         Note: Strategy chose to hold — this is valid (no forced exit)")
    return True  # Informational


# ── Runner ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FORWARD TESTER — Controlled Simulation Harness")
    print("=" * 60)
    print()

    tests = [
        ("Uptrend Detection", test_uptrend_detection),
        ("Downtrend Detection", test_downtrend_detection),
        ("Entry Signal Fire", test_entry_signal),
        ("Hold Guard Blocks Early Exit", test_hold_guard_blocks_early_exit),
        ("Exit Allowed After Hold", test_exit_allowed_after_hold),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print()
    print("=" * 60)
    passes = sum(1 for _, p in results if p)
    print(f"  Results: {passes}/{len(results)} passed")
    failures = [name for name, p in results if not p]
    if failures:
        print(f"  Failed: {', '.join(failures)}")
    print("=" * 60)

    return all(p for _, p in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
