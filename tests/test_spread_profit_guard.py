from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from helpers import make_test_profile
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.market.models import MarketSnapshot, TrendState, Candle


class FakeStrategy:
    SESSION_PROFILE = None
    name = "fake_strategy"

    def __init__(self, exit_decision=None):
        self.exit_decision = exit_decision

    def check_exit_signal(self, *args, **kwargs):
        return self.exit_decision

    def check_entry_signal(self, *args, **kwargs):
        return None

    def score_signal(self, *args, **kwargs):
        return 50.0, "C", "dummy summary"


def _make_profile(**overrides):
    return make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        enable_hold_guard=False,          # disable hold guard to isolate tests
        enable_negative_hold_guard=False, # disable negative hold guard to isolate tests
        enable_spread_profit_guard=True,
        **overrides,
    )


def test_spread_profit_guard_blocks_low_profit(monkeypatch):
    """Verify that exits are blocked if profit is positive but less than estimated spread cost."""
    now = datetime.now(timezone.utc)
    # Entry = 1.1000, Current = 1.1001 (profit of 0.0001 per unit)
    # For size=10000 EURUSD, profit = $1.00 USD.
    # Spread cost (1.3 pips) = 10000 * 1.3 * 0.0001 = $1.30 USD.
    # $1.00 < $1.30, so non-emergency exit should be blocked.
    
    candles = [Candle(timestamp=now, open=1.1000, high=1.1002, low=1.0999, close=1.1001, volume=1000)]
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )

    class MockProvider:
        def get_latest_snapshot(self, symbol, timeframe):
            return snapshot

    profile = _make_profile()
    
    # Non-emergency exit decision
    exit_decision = AITradeDecision(
        symbol="EURUSD", timeframe="5m", bias="neutral", phase="management",
        action="close_position", entry_price=1.1001, stop_loss=0, take_profit=0,
        notes="Take Profit Target Hit (Fixed RR)"
    )
    exit_decision.emergency_exit = False

    # Monkeypatch run_universal_exit_logic to return our mock exit decision
    monkeypatch.setattr(
        "tradebot_sci.strategy.exit_logic.run_universal_exit_logic",
        lambda *args, **kwargs: exit_decision
    )

    engine = StrategyEngine(
        ai_client=MagicMock(),
        market_provider=MockProvider(),
        profile=profile,
        symbol="EURUSD"
    )
    engine._strategy = FakeStrategy(exit_decision=exit_decision)

    open_pos = {
        "symbol": "EURUSD",
        "side": "long",
        "entry_price": 1.1000,
        "entry_time": (now - timedelta(minutes=20)).isoformat(),
        "size": 10000.0,
    }

    # Run decide - it should block the exit and return "hold"
    decision = engine.decide(timeframe="5m", open_position=open_pos, snapshot=snapshot)
    assert decision is not None
    assert decision.action == "hold"


def test_spread_profit_guard_allows_high_profit(monkeypatch):
    """Verify that exits are allowed if profit is greater than estimated spread cost."""
    now = datetime.now(timezone.utc)
    # Entry = 1.1000, Current = 1.1005 (profit of 0.0005 per unit)
    # For size=10000 EURUSD, profit = $5.00 USD.
    # Spread cost (1.3 pips) = $1.30 USD.
    # $5.00 >= $1.30, so exit should be allowed.
    
    candles = [Candle(timestamp=now, open=1.1000, high=1.1006, low=1.0999, close=1.1005, volume=1000)]
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )

    class MockProvider:
        def get_latest_snapshot(self, symbol, timeframe):
            return snapshot

    profile = _make_profile()
    
    exit_decision = AITradeDecision(
        symbol="EURUSD", timeframe="5m", bias="neutral", phase="management",
        action="close_position", entry_price=1.1005, stop_loss=0, take_profit=0,
        notes="Take Profit Target Hit (Fixed RR)"
    )
    exit_decision.emergency_exit = False

    # Monkeypatch run_universal_exit_logic to return our mock exit decision
    monkeypatch.setattr(
        "tradebot_sci.strategy.exit_logic.run_universal_exit_logic",
        lambda *args, **kwargs: exit_decision
    )

    engine = StrategyEngine(
        ai_client=MagicMock(),
        market_provider=MockProvider(),
        profile=profile,
        symbol="EURUSD"
    )
    engine._strategy = FakeStrategy(exit_decision=exit_decision)

    open_pos = {
        "symbol": "EURUSD",
        "side": "long",
        "entry_price": 1.1000,
        "entry_time": (now - timedelta(minutes=20)).isoformat(),
        "size": 10000.0,
    }

    # Run decide - it should not block the exit
    decision = engine.decide(timeframe="5m", open_position=open_pos, snapshot=snapshot)
    assert decision is not None
    assert decision.action == "close_position"


def test_spread_profit_guard_allows_emergency_exits(monkeypatch):
    """Verify that emergency exits bypass the spread profit guard."""
    now = datetime.now(timezone.utc)
    # Entry = 1.1000, Current = 1.1001 (profit = $1.00 < spread $1.30)
    # Since it is an emergency exit, it should bypass the guard and be allowed.
    
    candles = [Candle(timestamp=now, open=1.1000, high=1.1002, low=1.0999, close=1.1001, volume=1000)]
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )

    class MockProvider:
        def get_latest_snapshot(self, symbol, timeframe):
            return snapshot

    profile = _make_profile()
    
    # Emergency exit
    exit_decision = AITradeDecision(
        symbol="EURUSD", timeframe="5m", bias="neutral", phase="management",
        action="close_position", entry_price=1.1001, stop_loss=0, take_profit=0,
        notes="Emergency Trend Invalidation"
    )
    exit_decision.emergency_exit = True

    # Monkeypatch run_universal_exit_logic to return our mock exit decision
    monkeypatch.setattr(
        "tradebot_sci.strategy.exit_logic.run_universal_exit_logic",
        lambda *args, **kwargs: exit_decision
    )

    engine = StrategyEngine(
        ai_client=MagicMock(),
        market_provider=MockProvider(),
        profile=profile,
        symbol="EURUSD"
    )
    engine._strategy = FakeStrategy(exit_decision=exit_decision)

    open_pos = {
        "symbol": "EURUSD",
        "side": "long",
        "entry_price": 1.1000,
        "entry_time": (now - timedelta(minutes=20)).isoformat(),
        "size": 10000.0,
    }

    # Run decide - emergency exit is allowed
    decision = engine.decide(timeframe="5m", open_position=open_pos, snapshot=snapshot)
    assert decision is not None
    assert decision.action == "close_position"
