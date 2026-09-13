import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from helpers import make_test_profile
from tradebot_sci.strategy.safety_guard import SafetyGuard, AssetClass
from tradebot_sci.config.models import (
    Settings,
    AppSettings,
    LoggingSettings,
    AISettings,
    MarketSettings,
    RuntimeSettings,
    RiskSettings,
    SafetySettings,
)
from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState

class MockAIClient:
    def __init__(self):
        self.calls = 0

    def generate_text(self, messages):
        self.calls += 1
        return "SAFE"

@pytest.fixture(autouse=True)
def cleanup_safety_state():
    """Reset SafetyGuard state before each test to ensure test isolation."""
    state = SafetyGuard._state
    state.global_positions.clear()
    state.daily_start_capital.clear()
    state.daily_pnl.clear()
    state.last_reset_date.clear()
    state.trade_timestamps.clear()
    state.sentiment_cache.clear()
    state.hwm_capital.clear()
    state.drawdown_pause_until.clear()
    state.symbol_exit_cooldown.clear()
    state.symbol_loss_streaks.clear()
    state.regime_flip_cooldown.clear()

def test_update_daily_stats_sim_time():
    """Verify _update_daily_stats correctly tracks days using simulated EST time."""
    asset_class = AssetClass.FOREX
    
    # 1. First tick on Day 1 (Feb 18, 2026 10:00 EST / 15:00 UTC)
    t1 = datetime(2026, 2, 18, 15, 0, tzinfo=timezone.utc)
    SafetyGuard._update_daily_stats(10000.0, asset_class, now=t1)
    
    assert SafetyGuard._state.daily_start_capital[asset_class] == 10000.0
    assert SafetyGuard._state.daily_pnl[asset_class] == 0.0
    assert SafetyGuard._state.last_reset_date[asset_class] == datetime(2026, 2, 18).date()
    
    # 2. Update capital on same day
    SafetyGuard._update_daily_stats(9800.0, asset_class, now=t1 + timedelta(hours=2))
    assert SafetyGuard._state.daily_pnl[asset_class] == -200.0
    assert SafetyGuard._state.last_reset_date[asset_class] == datetime(2026, 2, 18).date()
    
    # 3. Transition to Day 2 (Feb 19, 2026 09:00 EST / 14:00 UTC)
    t2 = datetime(2026, 2, 19, 14, 0, tzinfo=timezone.utc)
    SafetyGuard._update_daily_stats(9800.0, asset_class, now=t2)
    
    # Verify stats reset for the new day
    assert SafetyGuard._state.daily_start_capital[asset_class] == 9800.0
    assert SafetyGuard._state.daily_pnl[asset_class] == 0.0
    assert SafetyGuard._state.last_reset_date[asset_class] == datetime(2026, 2, 19).date()

def test_register_trade_completion_sim_time():
    """Verify register_trade_completion handles day boundaries and updates correctly."""
    symbol = "EURUSD"
    asset_class = AssetClass.FOREX
    
    # Set initial start date
    SafetyGuard._state.last_reset_date[asset_class] = datetime(2026, 2, 18).date()
    SafetyGuard._state.daily_pnl[asset_class] = -100.0
    
    # Complete a trade on the next simulated day (Feb 19)
    sim_time = datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc)
    SafetyGuard.register_trade_completion(symbol, is_win=True, pnl_usd=150.0, sim_time=sim_time)
    
    # Should detect the new day, reset daily pnl to 0.0, and then apply the pnl_usd
    assert SafetyGuard._state.last_reset_date[asset_class] == datetime(2026, 2, 19).date()
    assert SafetyGuard._state.daily_pnl[asset_class] == 150.0

def test_notify_entry_sim_time():
    """Verify notify_entry respects simulated timestamps."""
    symbol = "EURUSD"
    asset_class = AssetClass.FOREX
    
    sim_time = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)
    SafetyGuard.notify_entry(symbol, sim_time=sim_time)
    
    timestamps = SafetyGuard._state.trade_timestamps[asset_class]
    assert len(timestamps) == 1
    assert timestamps[0] == sim_time

def test_ai_sentiment_shield_bypass_in_replay():
    """Verify AI Sentiment Shield is bypassed when the snapshot is historical (replay mode)."""
    symbol = "EURUSD"
    timeframe = "5m"
    
    # Create an old historical snapshot (simulated time)
    historical_time = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)
    candles = [Candle(timestamp=historical_time, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)]
    snapshot = MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        ltf_candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0),
    )
    
    # Configure safety settings to enable Sentiment Shield
    profile = make_test_profile(
        candle_timeframe=timeframe,
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
    )
    settings = Settings(
        app=AppSettings(profile_name="default"),
        logging=LoggingSettings(),
        ai=AISettings(),
        market=MarketSettings(),
        runtime=RuntimeSettings(),
        risk=RiskSettings(),
        safety=SafetySettings(
            safety_sentiment_shield_enabled=True,
            safety_leverage_sentry_enabled=False
        ),
        profiles={"default": profile},
    )
    
    ai_client = MockAIClient()
    
    # Perform safety check
    decision = SafetyGuard.check_entry_safety(
        symbol=symbol,
        timeframe=timeframe,
        current_capital=10000.0,
        snapshot=snapshot,
        ai_client=ai_client,
        settings=settings
    )
    
    # Since simulated time is historical (Feb 2026 is far in the past), AI shield must be bypassed.
    # Therefore, generate_text should NOT be called.
    assert ai_client.calls == 0
    assert decision is None

def test_register_trade_completion_pnl_updates():
    """Verify register_trade_completion correctly accumulates PnL when pnl_usd is explicitly provided."""
    symbol = "USDJPY"
    asset_class = AssetClass.FOREX
    sim_time = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)
    
    SafetyGuard._state.last_reset_date[asset_class] = sim_time.date()
    SafetyGuard._state.daily_pnl[asset_class] = 0.0
    
    # Win trade
    SafetyGuard.register_trade_completion(symbol, is_win=True, pnl_usd=50.0, sim_time=sim_time)
    assert SafetyGuard._state.daily_pnl[asset_class] == 50.0
    
    # Loss trade
    SafetyGuard.register_trade_completion(symbol, is_win=False, pnl_usd=-20.0, sim_time=sim_time)
    assert SafetyGuard._state.daily_pnl[asset_class] == 30.0
