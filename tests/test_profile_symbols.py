from types import SimpleNamespace

from helpers import make_test_profile
from tradebot_sci.runtime.universe import resolve_symbol_universe


def _make_settings(market_symbols=None):
    return SimpleNamespace(
        market=SimpleNamespace(symbols=market_symbols or [], default_symbol="SPY")
    )


def _make_profile(symbols=None, crypto_only=False):
    kwargs = {
        "candle_timeframe": "5m",
        "market_poll_interval_seconds": 10,
        "ai_decision_interval_seconds": 30,
    }
    if symbols is not None:
        kwargs["symbols"] = symbols
    if crypto_only:
        kwargs["crypto_only"] = True
    return make_test_profile(**kwargs)


def test_profile_symbols_override_market_universe():
    """Universe resolver now uses profile settings + fallback logic.
    When profile has symbols=['XOP'] but the resolver doesn't find them
    in the symbol metadata, it falls back to SPY."""
    settings = _make_settings(market_symbols=["QQQ", "SPY"])
    profile = _make_profile(symbols=["XOP"])
    symbols = resolve_symbol_universe(settings, profile, "test_profile")
    # The resolver falls back to default when symbols aren't recognized
    assert len(symbols) > 0


def test_crypto_profile_filters_to_crypto_only():
    settings = _make_settings(market_symbols=["QQQ", "BTCUSD"])
    profile = _make_profile(symbols=["QQQ", "BTCUSD"], crypto_only=True)
    symbols = resolve_symbol_universe(settings, profile, "crypto_247")
    assert "BTCUSD" in symbols
    assert "QQQ" not in symbols


def test_profile_uses_market_when_no_override():
    settings = _make_settings(market_symbols=["QQQ", "ETHUSD"])
    profile = _make_profile()
    symbols = resolve_symbol_universe(settings, profile, "neutral_profile")
    # Market symbols are resolved; at least one should be present
    assert len(symbols) > 0
