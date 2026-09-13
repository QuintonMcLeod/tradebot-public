from datetime import datetime, timedelta, timezone
import pytest
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.profiles import build_profile
from tradebot_sci.ai.client import TradeSciAIClient


class FakeAIClient(TradeSciAIClient):
    def __init__(self):
        pass

    def generate_decision(self, context):  # type: ignore[override]
        return None


def _c(timestamp, price: float) -> Candle:
    return Candle(timestamp=timestamp, open=price, high=price+1, low=price-1, close=price, volume=1000)


def create_engine_and_run(
    monkeypatch,
    entry_time,
    current_time,
    current_price,
    entry_price,
    direction,
    exit_triggered=True,
    exit_emergency=False,
    profile_mods=None,
):
    # Set up basic candles ending at current_time
    def_candles = []
    for i in range(15):
        t = current_time - timedelta(minutes=5 * (14 - i))
        def_candles.append(_c(t, current_price))
    
    class FixedProvider:
        def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
            return MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                candles=def_candles,
                trend_htf=TrendState(direction="long", strength=1.0),
                trend_ltf=TrendState(direction="long", strength=1.0),
            )

    provider = FixedProvider()
    profile = build_profile("intraday")
    if profile_mods:
        for k, v in profile_mods.items():
            setattr(profile, k, v)

    engine = StrategyEngine(
        ai_client=FakeAIClient(),
        market_provider=provider,
        profile=profile,
        symbol="SPY",
    )
    
    if exit_triggered:
        exit_decision = close_position_decision(
            symbol="SPY",
            timeframe="5m",
            reason="Test exit",
            emergency_exit=exit_emergency
        )
    else:
        exit_decision = None

    import tradebot_sci.strategy.exit_logic as exit_logic_module
    monkeypatch.setattr(exit_logic_module, "run_universal_exit_logic", lambda *args, **kwargs: exit_decision)

    open_pos = {
        "symbol": "SPY",
        "side": direction,
        "entry_price": entry_price,
        "avg_price": entry_price,
        "entry_time": entry_time.isoformat(),
        "size": 1.0 if direction == "long" else -1.0,
    }

    # Run engine.decide with the open position and the snapshot
    snapshot = provider.get_latest_snapshot("SPY", profile.candle_timeframe)
    decision = engine.decide(
        timeframe=profile.candle_timeframe,
        open_position=open_pos,
        snapshot=snapshot
    )
    return decision


def test_negative_hold_blocked(monkeypatch):
    """Case 1: negative trade, younger than 45 minutes, non-emergency exit -> should be BLOCKED."""
    now = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    # Entry was 10 minutes ago (600s)
    entry_time = now - timedelta(minutes=10)
    
    # Long trade entered at 100.0, current price is 95.0 (in loss)
    decision = create_engine_and_run(
        monkeypatch=monkeypatch,
        entry_time=entry_time,
        current_time=now,
        current_price=95.0,
        entry_price=100.0,
        direction="long",
        exit_triggered=True,
        exit_emergency=False,
        profile_mods={
            "enable_hold_guard": False, # disable 15m hold guard to isolate negative hold guard
            "enable_negative_hold_guard": True,
            "negative_hold_seconds": 2700,
        }
    )
    # Since exit is blocked, decision should be hold (i.e. not close_position)
    assert decision is not None
    assert decision.action == "hold"


def test_negative_hold_allowed_after_expiry(monkeypatch):
    """Case 2: negative trade, older than 45 minutes -> should be ALLOWED."""
    now = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    # Entry was 50 minutes ago (3000s)
    entry_time = now - timedelta(minutes=50)
    
    decision = create_engine_and_run(
        monkeypatch=monkeypatch,
        entry_time=entry_time,
        current_time=now,
        current_price=95.0,
        entry_price=100.0,
        direction="long",
        exit_triggered=True,
        exit_emergency=False,
        profile_mods={
            "enable_hold_guard": False,
            "enable_negative_hold_guard": True,
            "negative_hold_seconds": 2700,
        }
    )
    assert decision is not None
    assert decision.action == "close_position"


def test_positive_hold_allowed(monkeypatch):
    """Case 3: positive trade, older than 15 minutes but younger than 45 minutes -> should be ALLOWED."""
    now = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    # Entry was 20 minutes ago (1200s)
    entry_time = now - timedelta(minutes=20)
    
    # Long trade entered at 100.0, current price is 105.0 (in profit)
    decision = create_engine_and_run(
        monkeypatch=monkeypatch,
        entry_time=entry_time,
        current_time=now,
        current_price=105.0,
        entry_price=100.0,
        direction="long",
        exit_triggered=True,
        exit_emergency=False,
        profile_mods={
            "enable_hold_guard": True,
            "hold_guard_seconds": 900, # 15 minutes
            "enable_negative_hold_guard": True,
            "negative_hold_seconds": 2700,
        }
    )
    assert decision is not None
    assert decision.action == "close_position"


def test_negative_hold_emergency_exit_allowed(monkeypatch):
    """Case 4: negative trade, younger than 45 minutes, but emergency exit -> should be ALLOWED."""
    now = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    # Entry was 10 minutes ago (600s)
    entry_time = now - timedelta(minutes=10)
    
    decision = create_engine_and_run(
        monkeypatch=monkeypatch,
        entry_time=entry_time,
        current_time=now,
        current_price=95.0,
        entry_price=100.0,
        direction="long",
        exit_triggered=True,
        exit_emergency=True, # emergency exit
        profile_mods={
            "enable_hold_guard": False,
            "enable_negative_hold_guard": True,
            "negative_hold_seconds": 2700,
        }
    )
    assert decision is not None
    assert decision.action == "close_position"
    assert decision.emergency_exit is True


def test_negative_hold_disabled(monkeypatch):
    """Case 5: negative trade, younger than 45 minutes, but negative hold guard is disabled -> should be ALLOWED."""
    now = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    # Entry was 20 minutes ago (1200s)
    entry_time = now - timedelta(minutes=20)
    
    decision = create_engine_and_run(
        monkeypatch=monkeypatch,
        entry_time=entry_time,
        current_time=now,
        current_price=95.0,
        entry_price=100.0,
        direction="long",
        exit_triggered=True,
        exit_emergency=False,
        profile_mods={
            "enable_hold_guard": False,
            "enable_negative_hold_guard": False, # disabled
            "negative_hold_seconds": 2700,
        }
    )
    assert decision is not None
    assert decision.action == "close_position"
