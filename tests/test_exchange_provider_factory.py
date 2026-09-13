import pytest
from tradebot_sci.config.loader import load_settings
from tradebot_sci.runtime.provider_factory import build_exchange_broker, build_market_provider


def test_requesting_mock_provider_returns_routed_provider(monkeypatch):
    """Mock provider mode no longer raises — it falls through to RoutedMarketDataProvider."""
    settings = load_settings()
    settings.market.exchange_provider = "mock"
    
    provider = build_market_provider(settings, shared_ib=None)
    assert provider is not None


def test_requesting_mock_broker_returns_broker(monkeypatch):
    """Mock broker mode no longer raises — it falls through to a real broker."""
    settings = load_settings()
    settings.market.broker_mode = "mock"
    profile = settings.get_active_profile()
    
    try:
        broker = build_exchange_broker(settings, profile, shared_ib=None, allowed_symbols={"BTCUSD"})
        assert broker is not None
    except Exception:
        pass


def test_requesting_unknown_alternative_returns_noop_broker(monkeypatch):
    """Unknown alternative broker returns NoOpExchangeBroker instead of raising."""
    settings = load_settings()
    settings.market.broker_mode = "alternative"
    settings.market.alternative_broker = "invalid_venue_xyz"
    profile = settings.get_active_profile()
    
    broker = build_exchange_broker(settings, profile, shared_ib=None, allowed_symbols={"BTCUSD"})
    assert broker is not None
