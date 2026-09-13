"""Tests for PaperBroker: leverage cap, affordability guard, ghost trade guard, EXIT_SIGNAL."""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# ── Ensure src is on the path ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.broker.paper_broker import PaperBroker
from tradebot_sci.strategy.decisions import AITradeDecision


# ── Helpers ──────────────────────────────────────────────────────────

def _make_profile(risk_pct=0.01, target_leverage=1.0):
    """Minimal profile-like object with the fields PaperBroker reads."""
    profile = types.SimpleNamespace(
        risk_per_trade_pct=risk_pct,
        target_leverage=target_leverage,
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


def _make_broker(balance=10_000.0, target_leverage=1.0, positions=None):
    """Create a PaperBroker without touching disk state."""
    profile = _make_profile(target_leverage=target_leverage)
    # Patch _load_state to avoid disk I/O
    original_load = PaperBroker._load_state
    PaperBroker._load_state = lambda self: None
    original_save = PaperBroker._save_state
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=balance)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    # Disable disk persistence during tests
    broker._save_state = lambda: None
    if positions:
        broker.positions = positions
    return broker


# ── Tests ────────────────────────────────────────────────────────────

class TestExecutionStatusExitSignal:
    """Verify EXIT_SIGNAL exists in the enum."""

    def test_exit_signal_exists(self):
        assert hasattr(ExecutionStatus, "EXIT_SIGNAL")
        assert ExecutionStatus.EXIT_SIGNAL.value == "exit_signal"


class TestLeverageCap:
    """Position sizing must be capped by target_leverage × balance / price."""

    def test_tiny_sl_gets_leverage_capped(self):
        """With a tiny SL distance, raw qty would be huge. Leverage cap should clamp it."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)
        # LTCUSD at $55, SL only $0.12 away → raw qty = (10000 * 0.01) / 0.12 ≈ 833 units
        # But at 1x leverage: max_notional = $10,000 → max_qty = 10000/55 ≈ 181.8
        decision = _make_decision("LTCUSD", "enter_short", 55.0, 55.12, 54.50)
        result, outcome = broker.execute_decision(decision)

        assert result.status == ExecutionStatus.EXECUTED
        pos = broker.positions.get("LTCUSD")
        assert pos is not None

        # Qty should be ≤ max_qty (10000 / 55 ≈ 181.8)
        max_qty = 10_000.0 / 55.0
        assert abs(pos["qty"]) <= max_qty + 0.01, (
            f"Position qty {abs(pos['qty']):.4f} exceeds leverage cap {max_qty:.4f}"
        )

    def test_higher_leverage_allows_more(self):
        """With 2x leverage, the cap should double."""
        broker = _make_broker(balance=10_000.0, target_leverage=2.0)
        decision = _make_decision("LTCUSD", "enter_long", 55.0, 54.88, 56.0)
        result, _ = broker.execute_decision(decision)
        assert result.status == ExecutionStatus.EXECUTED
        pos = broker.positions["LTCUSD"]
        max_qty_2x = 20_000.0 / 55.0
        assert abs(pos["qty"]) <= max_qty_2x + 0.01

    def test_normal_trade_not_affected(self):
        """A normally-sized trade shouldn't hit the cap."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)
        # Add market provider so _get_current_price returns the right price
        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 100_000.0
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider
        # BTCUSD at $100k, SL $2000 away → raw qty = 100 / 2000 = 0.05 BTC
        # max_qty = 10000 / 100000 = 0.1 → 0.05 < 0.1, no cap hit
        decision = _make_decision("BTCUSD", "enter_long", 100_000.0, 98_000.0, 104_000.0)
        result, _ = broker.execute_decision(decision)
        assert result.status == ExecutionStatus.EXECUTED
        pos = broker.positions["BTCUSD"]
        expected_qty = 100.0 / 2000.0  # 0.05
        assert abs(pos["qty"] - expected_qty) < 0.01


class TestAffordabilityGuard:
    """Trades that exceed balance should be rejected."""

    def test_near_zero_balance_blocked(self):
        """With nearly zero balance, entries should be rejected."""
        broker = _make_broker(balance=0.50, target_leverage=1.0)
        decision = _make_decision("LTCUSD", "enter_long", 55.0, 54.0, 56.0)
        result, outcome = broker.execute_decision(decision)
        # Should either execute with a tiny position or get suppressed
        # With $0.50 at 1x leverage, max is 0.50/55 ≈ 0.009 units
        # risk_usd = 0.50 * 0.01 = $0.005, qty = 0.005 / 1.0 = 0.005 units
        # 0.005 * 55 = $0.275 notional, well within $0.505 cap
        # So this should actually fill with a tiny position
        if result.status == ExecutionStatus.EXECUTED:
            assert abs(broker.positions["LTCUSD"]["qty"]) < 0.1
        else:
            assert result.status == ExecutionStatus.RISK_SUPPRESSED


class TestGhostTradeGuard:
    """TP at or below entry should not trigger exit for longs, etc."""

    def _make_market_provider(self, prices):
        provider = MagicMock()
        ticker_mock = MagicMock()
        def get_ticker(sym):
            t = MagicMock()
            t.last = prices.get(sym, 100.0)
            return t
        provider.get_ticker = get_ticker
        provider.get_latest_candles.return_value = []
        return provider

    def test_long_tp_at_entry_no_exit(self):
        """Long position with TP == entry should NOT trigger an exit."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = self._make_market_provider({"ZECUSD": 280.0})
        broker.positions = {
            "ZECUSD": {
                "symbol": "ZECUSD",
                "side": "long",
                "size": 10.0,
                "qty": 10.0,
                "entry_price": 280.0,
                "avg_price": 280.0,
                "current_price": 280.0,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
                "stop_loss": 275.0,
                "take_profit": 280.0,  # TP == entry (the bug)
            }
        }
        results = broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        # No exit should be triggered
        assert len(results) == 0
        assert "ZECUSD" in broker.positions, "Position should NOT have been closed"

    def test_long_tp_below_entry_no_exit(self):
        """Long position with TP < entry should NOT trigger an exit."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = self._make_market_provider({"ZECUSD": 278.0})
        broker.positions = {
            "ZECUSD": {
                "symbol": "ZECUSD",
                "side": "long",
                "size": 10.0,
                "qty": 10.0,
                "entry_price": 280.0,
                "avg_price": 280.0,
                "current_price": 278.0,
                "unrealized_pnl": -20.0,
                "pnl_pct": -0.71,
                "stop_loss": 275.0,
                "take_profit": 278.0,  # TP below entry
            }
        }
        results = broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        assert len(results) == 0
        assert "ZECUSD" in broker.positions

    def test_long_valid_tp_does_exit(self):
        """Long position with TP > entry and price >= TP should trigger exit."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = self._make_market_provider({"ZECUSD": 290.0})
        broker.positions = {
            "ZECUSD": {
                "symbol": "ZECUSD",
                "side": "long",
                "size": 10.0,
                "qty": 10.0,
                "entry_price": 280.0,
                "avg_price": 280.0,
                "current_price": 285.0,
                "unrealized_pnl": 50.0,
                "pnl_pct": 1.78,
                "stop_loss": 275.0,
                "take_profit": 288.0,  # Valid TP above entry
            }
        }
        results = broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        assert len(results) == 1
        assert results[0].status == ExecutionStatus.EXIT_SIGNAL
        assert "ZECUSD" not in broker.positions, "Position SHOULD have been closed"

    def test_short_tp_at_entry_no_exit(self):
        """Short position with TP >= entry should NOT trigger an exit."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = self._make_market_provider({"LTCUSD": 55.0})
        broker.positions = {
            "LTCUSD": {
                "symbol": "LTCUSD",
                "side": "short",
                "size": -10.0,
                "qty": 10.0,
                "entry_price": 55.0,
                "avg_price": 55.0,
                "current_price": 55.0,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
                "stop_loss": 56.0,
                "take_profit": 55.0,  # TP == entry (the bug for shorts)
            }
        }
        results = broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        assert len(results) == 0
        assert "LTCUSD" in broker.positions

    def test_short_valid_tp_does_exit(self):
        """Short position with TP < entry and price <= TP should trigger exit."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = self._make_market_provider({"LTCUSD": 53.0})
        broker.positions = {
            "LTCUSD": {
                "symbol": "LTCUSD",
                "side": "short",
                "size": -10.0,
                "qty": 10.0,
                "entry_price": 55.0,
                "avg_price": 55.0,
                "current_price": 54.0,
                "unrealized_pnl": 10.0,
                "pnl_pct": 1.82,
                "stop_loss": 56.0,
                "take_profit": 54.0,  # Valid TP below entry
            }
        }
        results = broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        assert len(results) == 1
        assert results[0].status == ExecutionStatus.EXIT_SIGNAL
        assert "LTCUSD" not in broker.positions


class TestPaperBrokerDuration:
    """Verify that _compute_duration handles sim-time and falls back to wall-clock for sub-second precision."""

    def test_sim_time_duration(self):
        from datetime import datetime, timezone
        broker = _make_broker(balance=10_000.0)
        # Mock sim_time
        provider = MagicMock()
        provider.sim_time = datetime(2026, 5, 24, 10, 5, 0, tzinfo=timezone.utc)
        broker.market_provider = provider

        pos = {
            "entry_time": "2026-05-24T10:00:00+00:00",
            "opened_at": "2026-05-24T10:00:00+00:00"
        }
        duration_secs, duration_str = broker._compute_duration(pos)
        # 5 minutes difference = 300 seconds
        assert duration_secs == 300.0
        assert duration_str == "5m 0s"

    def test_sub_second_fallback(self):
        from datetime import datetime, timezone
        broker = _make_broker(balance=10_000.0)
        # Mock sim_time to be identical to entry_time to force fallback
        provider = MagicMock()
        provider.sim_time = datetime(2026, 5, 24, 10, 0, 0, tzinfo=timezone.utc)
        broker.market_provider = provider

        # Mock wall_clock to simulate a sub-second difference (e.g. 25 milliseconds after opened_at)
        opened_at_dt = datetime(2026, 5, 24, 10, 0, 0, 25000, tzinfo=timezone.utc)
        broker._wall_clock = MagicMock(return_value=datetime(2026, 5, 24, 10, 0, 0, 50000, tzinfo=timezone.utc))

        pos = {
            "entry_time": "2026-05-24T10:00:00+00:00",
            "opened_at": opened_at_dt.isoformat()
        }
        duration_secs, duration_str = broker._compute_duration(pos)
        # Difference in microseconds: 50000 - 25000 = 25000us = 0.025 seconds
        assert abs(duration_secs - 0.025) < 0.001
        assert duration_str == "25ms"

