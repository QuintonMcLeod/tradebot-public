from __future__ import annotations

from tradebot_sci.config import loader
from tradebot_sci.runtime.universe import instrument_classes_for_symbols, resolve_symbol_universe


def test_resolve_trading_universe_from_settings_does_not_require_runtime_loop(monkeypatch):
    loader.get_settings.cache_clear()
    monkeypatch.delenv("MARKET_SYMBOLS", raising=False)
    monkeypatch.delenv("MARKET_DEFAULT_SYMBOL", raising=False)

    settings = loader.get_settings()
    profile = settings.get_active_profile()
    symbols = resolve_symbol_universe(settings, profile, settings.app.profile_name)

    assert symbols
    # The default profile may resolve to forex pairs, crypto, or equities
    # depending on the active profile configuration
    assert len(symbols) > 0

    classes = instrument_classes_for_symbols(symbols)
    assert len(classes) > 0
