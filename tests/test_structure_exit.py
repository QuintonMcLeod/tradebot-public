"""Tests for structure invalidation exit in ICC Core strategy."""

import pytest
from unittest.mock import MagicMock
from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState
from tradebot_sci.strategy.variants.icc_core import ICCCoreStrategy


def _make_candles_with_breakdown(direction: str = "long"):
    """Create candle series where price breaks below swing low (long) or above swing high (short).

    Uses oscillating price action to create clear swing points, then a sharp
    breakdown/breakout that should trigger detect_structure_invalidation.
    """
    candles = []

    if direction == "long":
        # Uptrend with oscillating swing lows, then crash below
        prices = [
            100, 102, 104, 103, 101,   # swing low ~101
            103, 105, 107, 106, 104,   # swing low ~104
            106, 108, 110, 109, 107,   # swing low ~107
            109, 111, 113, 112, 110,   # swing low ~110
            112, 114, 116, 115, 113,   # swing low ~113
            115, 117, 119, 118, 116,   # swing low ~116
            118, 120, 122, 121, 119,   # swing low ~119
            121, 123, 125, 124, 122,   # swing low ~122
            118, 114, 110, 106, 102,   # crash through all swing lows
        ]
    else:
        # Downtrend with oscillating swing highs, then breakout above
        prices = [
            200, 198, 196, 197, 199,   # swing high ~199
            197, 195, 193, 194, 196,   # swing high ~196
            194, 192, 190, 191, 193,   # swing high ~193
            191, 189, 187, 188, 190,   # swing high ~190
            188, 186, 184, 185, 187,   # swing high ~187
            185, 183, 181, 182, 184,   # swing high ~184
            182, 180, 178, 179, 181,   # swing high ~181
            179, 177, 175, 176, 178,   # swing high ~178
            182, 186, 190, 194, 198,   # breakout through all swing highs
        ]

    for p in prices:
        candles.append(Candle(
            timestamp="2026-02-09T00:00:00Z",
            open=p - 0.5, high=p + 1.0, low=p - 1.0, close=float(p), volume=1000
        ))
    return candles


def _make_snapshot(candles, symbol="EUR_USD", timeframe="5m"):
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        trend_htf=TrendState(direction="bullish", strength=0.7),
        trend_ltf=TrendState(direction="bullish", strength=0.6),
    )


class TestICCCoreStructureExit:
    """ICCCoreStrategy should close positions when structure is invalidated."""

    def test_long_structure_invalidation_triggers_exit(self):
        candles = _make_candles_with_breakdown("long")
        snapshot = _make_snapshot(candles)
        position = {
            "direction": "long",
            "size": 1000,
            "entry_price": 110.0,
            "unrealized_pnl": -50.0,
            "stop_loss": 100.0,
            "entry_time": "2020-01-01T00:00:00Z"
        }

        strategy = ICCCoreStrategy()
        decision = strategy.check_exit_signal(snapshot, position, gates={})

        assert decision is not None
        assert decision.action == "close_position"
        assert "Structure Invalidation" in (decision.notes or "")

    def test_short_structure_invalidation_triggers_exit(self):
        candles = _make_candles_with_breakdown("short")
        snapshot = _make_snapshot(candles)
        position = {
            "direction": "short",
            "size": -1000,
            "entry_price": 190.0,
            "unrealized_pnl": -50.0,
            "stop_loss": 200.0,
            "entry_time": "2020-01-01T00:00:00Z"
        }

        strategy = ICCCoreStrategy()
        decision = strategy.check_exit_signal(snapshot, position, gates={})

        assert decision is not None
        assert decision.action == "close_position"
        assert "Structure Invalidation" in (decision.notes or "")
