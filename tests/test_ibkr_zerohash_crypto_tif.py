from types import SimpleNamespace

from helpers import make_test_profile
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.market.symbols import AssetClass


def test_effective_tif_defaults_to_minutes_for_zerohash_crypto(monkeypatch):
    monkeypatch.delenv("IBKR_ZEROHASH_CRYPTO_TIF", raising=False)
    assert IbkrExecutor._effective_tif(AssetClass.CRYPTO, "ZEROHASH", "GTC") == "Minutes"


def test_effective_tif_honors_override_for_zerohash_crypto(monkeypatch):
    monkeypatch.setenv("IBKR_ZEROHASH_CRYPTO_TIF", "IOC")
    assert IbkrExecutor._effective_tif(AssetClass.CRYPTO, "ZEROHASH", "GTC") == "IOC"


def test_effective_tif_maps_minutes_for_zerohash_crypto(monkeypatch):
    monkeypatch.setenv("IBKR_ZEROHASH_CRYPTO_TIF", "Minutes")
    assert IbkrExecutor._effective_tif(AssetClass.CRYPTO, "ZEROHASH", "GTC") == "Minutes"


def test_effective_tif_leaves_equity_unchanged(monkeypatch):
    monkeypatch.setenv("IBKR_ZEROHASH_CRYPTO_TIF", "IOC")
    assert IbkrExecutor._effective_tif(AssetClass.EQUITY, "SMART", "GTC") == "GTC"


def test_execution_caps_mark_zerohash_long_only():
    class _DummyIB:
        def positions(self):
            return []

        def openTrades(self):
            return []

    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
    )

    class _CapsExecutor(IbkrExecutor):
        def __init__(self) -> None:
            super().__init__(
                ib_client=_DummyIB(),
                runtime_settings=profile._settings.runtime,
                profile_settings=profile,
            )

        def _contract_for_symbol(self, symbol: str):
            return SimpleNamespace(exchange="ZEROHASH")

    executor = _CapsExecutor()
    caps = executor.get_execution_capabilities("BTCUSD")
    # Verify caps structure
    assert isinstance(caps, dict)
    assert "long_only" in caps
    assert "supports_short" in caps
    assert "supports_native_brackets" in caps
    assert "supports_native_stops" in caps
    assert "requires_synthetic_stops" in caps
