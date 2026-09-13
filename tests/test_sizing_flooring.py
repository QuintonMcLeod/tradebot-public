"""Unit tests for symbol-specific flooring and spread-based risk scaling."""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.broker.paper_broker import PaperBroker
from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
from tradebot_sci.strategy.safety_guard import SafetyGuard
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState


# The paper broker blocks forex entries between Friday 17:00 and Sunday 17:00 EST.
# These tests are about position sizing, not market hours, so without a pinned clock
# the flooring assertions only hold Monday to Friday.
_WEEKDAY_MID_SESSION = datetime(2026, 1, 7, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _pin_broker_clock(monkeypatch):
    monkeypatch.setattr(PaperBroker, "_now", lambda self: _WEEKDAY_MID_SESSION)


def _make_profile(min_units=None, below_min_unit_action=None):
    profile = types.SimpleNamespace(
        risk_per_trade_pct=0.01,
        target_leverage=1.0,
        min_units=min_units,
        below_min_unit_action=below_min_unit_action
    )
    return profile


def _make_decision(symbol, action, entry, sl, tp, risk_pct=None):
    return AITradeDecision(
        symbol=symbol,
        timeframe="5m",
        bias="long" if "long" in action else "short" if "short" in action else "neutral",
        phase="trend",
        action=action,
        entry_price=entry,
        entry_zone=None,
        stop_loss=sl,
        take_profit=tp,
        risk_per_trade_pct=risk_pct,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="test",
        invalidation_conditions="N/A",
        management_instructions="hold",
        notes="test trade",
    )


def test_paper_broker_flooring_reject():
    # Define a profile with min_units and action = reject
    profile = _make_profile(min_units={"EURUSD": 1000}, below_min_unit_action="reject")
    
    # Mock load/save state
    original_load = PaperBroker._load_state
    original_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=10000.0)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    broker._save_state = lambda: None

    provider = MagicMock()
    ticker = MagicMock()
    ticker.last = 1.0700
    provider.get_ticker.return_value = ticker
    broker.market_provider = provider

    # Normal EURUSD decision where qty is below 1000
    # Price is 1.07, entry 1.0700, SL 1.2500, TP 0.8000 (Short) -> qty = 100 / 0.18 = 555.55
    decision = _make_decision("EURUSD", "enter_short", 1.0700, 1.2500, 0.8000)
    
    # Execute decision
    result, outcome = broker.execute_decision(decision)
    
    # Assert it was rejected/suppressed due to floor
    assert result.status == ExecutionStatus.RISK_SUPPRESSED
    assert "below min_unit floor" in result.reason
    assert outcome.status == ExecutionOutcomeType.BLOCKED_GUARD


def test_paper_broker_flooring_round_up():
    profile = _make_profile(min_units={"EURUSD": 1000}, below_min_unit_action="round_up")
    
    original_load = PaperBroker._load_state
    original_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=10000.0)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    broker._save_state = lambda: None

    provider = MagicMock()
    ticker = MagicMock()
    ticker.last = 1.0700
    provider.get_ticker.return_value = ticker
    broker.market_provider = provider

    decision = _make_decision("EURUSD", "enter_short", 1.0700, 1.2500, 0.8000)
    
    result, outcome = broker.execute_decision(decision)
    
    # Assert it was rounded up and executed
    assert result.status == ExecutionStatus.EXECUTED
    pos = broker.positions.get("EURUSD")
    assert pos is not None
    assert abs(pos["qty"]) == 1000


def test_safety_guard_spread_scaling():
    # Setup some dummy candles for snapshot
    from datetime import datetime
    candles = [Candle(timestamp=datetime.now(), open=1.07, high=1.071, low=1.069, close=1.07, volume=100)]
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )
    
    decision = _make_decision("EURUSD", "enter_long", 1.0700, 1.0680, 1.0740, risk_pct=0.02)
    
    # Mock get_active_wealth_modes to return empty list
    original_modes = SafetyGuard.get_active_wealth_modes
    SafetyGuard.get_active_wealth_modes = classmethod(lambda cls: [])
    
    # Register live spread provider callback that returns 0.00025 (2.5 bps)
    from tradebot_sci.utils.symbol_classifier import set_live_spread_provider
    set_live_spread_provider(lambda sym: 0.00025)
    
    try:
        # Augment entry decision
        aug_decision = SafetyGuard.augment_entry_decision(decision, score=80.0, htf_strength=0.5, snapshot=snapshot)
        
        # Spread scaling applies 0.8x to original risk (2% -> 1.6%)
        # Forced stability clamp not triggered with htf_strength=0.5
        assert aug_decision.risk_per_trade_pct == 0.016
        assert abs(aug_decision.risk_per_trade_pct - 0.016) < 1e-4
    finally:
        # Reset live spread provider and active wealth modes
        SafetyGuard.get_active_wealth_modes = original_modes
        import tradebot_sci.utils.symbol_classifier as sc
        sc._live_spread_provider = None


def test_safety_guard_forced_stability():
    from datetime import datetime
    candles = [Candle(timestamp=datetime.now(), open=1.07, high=1.071, low=1.069, close=1.07, volume=100)]
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )
    
    decision = _make_decision("EURUSD", "enter_long", 1.0700, 1.0680, 1.0740, risk_pct=0.02)
    
    # Mock get_active_wealth_modes to return empty list
    original_modes = SafetyGuard.get_active_wealth_modes
    SafetyGuard.get_active_wealth_modes = classmethod(lambda cls: [])
    
    # Spread is 0.0005 (5 bps), which is > elevated_spread_threshold of 3.0 bps.
    # This should trigger forced stability mode, which clamps risk to 1.0%
    from tradebot_sci.utils.symbol_classifier import set_live_spread_provider
    set_live_spread_provider(lambda sym: 0.0005)
    
    try:
        aug_decision = SafetyGuard.augment_entry_decision(decision, score=80.0, htf_strength=0.5, snapshot=snapshot)
        
        # Risk must be clamped to max 1.0% (0.01)
        assert aug_decision.risk_per_trade_pct <= 0.01
        assert "[SPREAD SCALING]" in aug_decision.notes
    finally:
        SafetyGuard.get_active_wealth_modes = original_modes
        import tradebot_sci.utils.symbol_classifier as sc
        sc._live_spread_provider = None
