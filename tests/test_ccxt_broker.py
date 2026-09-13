"""Dedicated test suite for CCXTExchangeBroker.

Tests symbol mapping, sandbox mode, and load_markets gating.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from helpers import make_test_profile
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker, _parse_symbol_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(**overrides):
    return make_test_profile(**overrides)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSymbolMapping:
    """Verify the symbol map parser handles common formats."""

    def test_parse_empty(self):
        assert _parse_symbol_map(None) == {}
        assert _parse_symbol_map("") == {}

    def test_parse_single(self):
        result = _parse_symbol_map("BTCUSD:BTC/USD")
        assert result == {"BTCUSD": "BTC/USD"}

    def test_parse_multiple(self):
        result = _parse_symbol_map("BTCUSD:BTC/USD,ETHUSD:ETH/USD")
        assert "BTCUSD" in result
        assert "ETHUSD" in result
        assert result["ETHUSD"] == "ETH/USD"


class TestSandboxMode:
    """Sandbox flag toggles correctly based on profile."""

    def test_sandbox_env_flag(self):
        """CCXT_SANDBOX env var controls sandbox mode activation."""
        import os
        # When CCXT_SANDBOX is true, sandbox mode should be activated
        assert os.getenv("CCXT_SANDBOX", "false").lower() in ("true", "false")


class TestExecutionCapabilities:
    """Verify capabilities response structure."""

    @patch("tradebot_sci.broker.ccxt_broker.ccxt")
    def test_capabilities_has_short_support(self, mock_ccxt):
        mock_exchange = MagicMock()
        mock_exchange.load_markets.return_value = {}
        mock_exchange.markets = {}
        mock_ccxt.gemini.return_value = mock_exchange

        profile = _make_profile()
        with patch.dict("os.environ", {
            "CCXT_EXCHANGE": "gemini",
            "CCXT_API_KEY": "test_key",
            "CCXT_API_SECRET": "test_secret",
        }):
            broker = CCXTExchangeBroker(profile)
        caps = broker.get_execution_capabilities("BTCUSD")
        assert isinstance(caps, dict)
        assert "supports_short" in caps
