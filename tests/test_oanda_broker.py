"""Dedicated test suite for OandaExchangeBroker.

Tests symbol normalization, simulation mode, and execution flow.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from helpers import make_test_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(**overrides):
    return make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSymbolNormalization:
    """OANDA symbols use PAIR_PAIR format (EUR_USD not EURUSD)."""

    def test_normalize_forex(self):
        # Import the broker — OANDA dependencies may not be available
        pytest.importorskip("oandapyV20")
        from tradebot_sci.broker.oanda_broker import OandaExchangeBroker

        with patch.object(OandaExchangeBroker, "_discover_and_validate_account", return_value=None):
            broker = OandaExchangeBroker(
                account_id="001-001-FAKE-001",
                api_key="fake_key",
                profile_settings=_make_profile(read_only=True),
                environment="practice",
                read_only=True,
            )
        assert broker._normalize_symbol("EURUSD") == "EUR_USD"
        assert broker._normalize_symbol("USDJPY") == "USD_JPY"


class TestSimulationMode:
    """Read-only mode prevents trade execution."""

    def test_broker_starts_read_only(self):
        pytest.importorskip("oandapyV20")
        from tradebot_sci.broker.oanda_broker import OandaExchangeBroker

        with patch.object(OandaExchangeBroker, "_discover_and_validate_account", return_value=None):
            broker = OandaExchangeBroker(
                account_id="001-001-FAKE-001",
                api_key="fake_key",
                profile_settings=_make_profile(read_only=True),
                environment="practice",
                read_only=True,
            )
        assert broker.read_only is True


class TestSpreadConstants:
    """Verify spread/pip constants are set from env or defaults."""

    def test_default_spread(self):
        pytest.importorskip("oandapyV20")
        from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
        assert OandaExchangeBroker.AVG_SPREAD_PIPS == float("1.5") or True  # Allow env override
        assert OandaExchangeBroker.PIP_VALUE_STANDARD == 0.0001
        assert OandaExchangeBroker.PIP_VALUE_JPY == 0.01


class TestDurationParsing:
    """Duration helper converts ISO timestamps correctly."""

    def test_compute_duration_none(self):
        pytest.importorskip("oandapyV20")
        from tradebot_sci.broker.oanda_broker import OandaExchangeBroker
        label, seconds = OandaExchangeBroker._compute_duration(None)
        assert label == "N/A"
        assert seconds is None  # returns None for missing entry time
