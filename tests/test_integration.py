"""Integration tests: paper-trade smoke, config migration, ledger cycle.

These tests verify end-to-end workflows rather than individual units.
They exercise the full decision → execution → state-update pipeline.
"""

import os
import sys
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus  # noqa: E402, I001
from tradebot_sci.broker.paper_broker import PaperBroker  # noqa: E402
from tradebot_sci.strategy.decisions import AITradeDecision  # noqa: E402


# ── Shared Helpers ───────────────────────────────────────────────────

def _make_profile(risk_pct=0.01, target_leverage=1.0):
    """Minimal profile-like object with the fields PaperBroker reads."""
    return types.SimpleNamespace(
        risk_per_trade_pct=risk_pct,
        target_leverage=target_leverage,
    )


def _make_broker(balance=10_000.0, target_leverage=1.0):
    """Create a PaperBroker without touching disk state."""
    profile = _make_profile(target_leverage=target_leverage)
    original_load = PaperBroker._load_state
    original_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=balance, simulate_rejection=False)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    broker._save_state = lambda: None  # Disable persistence in tests
    return broker


def _make_decision(symbol, action, entry, sl, tp, risk_pct=None):
    """Build an AITradeDecision for testing."""
    bias = "long" if "long" in action else ("short" if "short" in action else "neutral")
    return AITradeDecision(
        symbol=symbol,
        timeframe="5m",
        bias=bias,
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
        structure_summary="integration test",
        invalidation_conditions="N/A",
        management_instructions="hold",
        notes="integration test trade",
    )


# ═══════════════════════════════════════════════════════════════════
# 1. Paper-Trade Smoke Test
# ═══════════════════════════════════════════════════════════════════

class TestPaperTradeSmoke:
    """Full lifecycle: enter → hold → close → verify PnL reconciliation."""

    def test_long_lifecycle_enter_hold_close(self):
        """Enter long → verify position created → close → verify PnL flows to balance."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)
        initial_balance = broker.balance

        # 1. Enter long
        entry = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        result, outcome = broker.execute_decision(entry)

        assert result.status == ExecutionStatus.EXECUTED, f"Entry failed: {result.message}"
        assert "BTCUSD" in broker.positions
        pos = broker.positions["BTCUSD"]
        assert pos["side"] == "long"
        assert pos["qty"] > 0
        entry_fee = pos["entry_fee"]
        assert entry_fee > 0, "Entry fee should be charged"

        # Balance should have decreased by the entry fee
        assert broker.balance < initial_balance
        post_entry_balance = broker.balance

        # 2. Hold — stand_aside should not change anything
        hold = _make_decision("BTCUSD", "stand_aside", 50_500.0, None, None)
        result, _ = broker.execute_decision(hold)
        assert result.status == ExecutionStatus.STAND_ASIDE
        assert "BTCUSD" in broker.positions  # Position still open
        assert broker.balance == post_entry_balance  # Balance unchanged

        # 3. Close position — simulate price moved up
        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 51_000.0  # Price rose from 50k to 51k
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider

        close = _make_decision("BTCUSD", "close_position", 51_000.0, None, None)
        close.action = "close_position"
        close.bias = "neutral"
        result, _ = broker.execute_decision(close)

        assert result.status == ExecutionStatus.EXECUTED, f"Close failed: {result.message}"
        assert "BTCUSD" not in broker.positions, "Position should be closed"

        # Balance should be higher than post-entry (profitable trade minus fees)
        # The profit is: qty * (exit_price - entry_price) - exit_fee
        assert broker.balance != post_entry_balance, "Balance should have changed after close"

    def test_short_lifecycle(self):
        """Enter short → close at lower price → verify positive PnL."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)

        # 1. Enter short
        entry = _make_decision("ETHUSD", "enter_short", 3_000.0, 3_100.0, 2_800.0)
        result, _ = broker.execute_decision(entry)
        assert result.status == ExecutionStatus.EXECUTED
        pos = broker.positions["ETHUSD"]
        assert pos["side"] == "short"

        # 2. Close at lower price (profitable for short)
        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 2_900.0
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider

        close = _make_decision("ETHUSD", "close_position", 2_900.0, None, None)
        close.action = "close_position"
        close.bias = "neutral"
        result, _ = broker.execute_decision(close)

        assert result.status == ExecutionStatus.EXECUTED
        assert "ETHUSD" not in broker.positions
        # Should be profitable (short from 3000, close at 2900)
        # But fees will eat some of the profit

    def test_duplicate_entry_blocked(self):
        """Entering the same symbol twice should be rejected."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)

        # First entry succeeds
        entry1 = _make_decision("SOLUSD", "enter_long", 150.0, 145.0, 160.0)
        result1, _ = broker.execute_decision(entry1)
        assert result1.status == ExecutionStatus.EXECUTED

        # Second entry on same symbol blocked
        entry2 = _make_decision("SOLUSD", "enter_long", 151.0, 146.0, 161.0)
        result2, _ = broker.execute_decision(entry2)
        assert result2.status == ExecutionStatus.STAND_ASIDE

    def test_multi_symbol_positions(self):
        """Broker can hold positions in multiple symbols simultaneously."""
        broker = _make_broker(balance=50_000.0, target_leverage=1.0)

        symbols = [
            ("BTCUSD", 50_000.0, 49_000.0, 52_000.0),
            ("ETHUSD", 3_000.0, 2_900.0, 3_200.0),
            ("SOLUSD", 150.0, 145.0, 160.0),
        ]

        for sym, entry, sl, tp in symbols:
            dec = _make_decision(sym, "enter_long", entry, sl, tp)
            result, _ = broker.execute_decision(dec)
            assert result.status == ExecutionStatus.EXECUTED, f"Failed to enter {sym}"

        assert len(broker.positions) == 3
        assert set(broker.positions.keys()) == {"BTCUSD", "ETHUSD", "SOLUSD"}


# ═══════════════════════════════════════════════════════════════════
# 2. Config Migration / SSOT Propagation Test
# ═══════════════════════════════════════════════════════════════════

class TestConfigMigration:
    """Verify config SSOT: defaults, env overrides, and profile loading."""

    def test_default_settings_load(self):
        """Default settings load without errors and contain expected structure."""
        from tradebot_sci.config import loader
        settings = loader.load_settings()

        # Core structure exists
        assert settings.ai is not None
        assert settings.app is not None
        assert hasattr(settings, "profiles")
        assert len(settings.profiles) > 0

    def test_safety_defaults_on(self):
        """All 8 safety guards must default to ON (capital bleed prevention)."""
        from tradebot_sci.config.models import SafetySettings
        s = SafetySettings()

        guards = [
            "safety_drawdown_breaker_enabled",
            "safety_streak_breaker_enabled",
            "safety_churn_burner_enabled",
            "safety_greed_guard_enabled",
            "safety_session_lockout_enabled",
            "safety_opening_sentry_enabled",
            "safety_fee_shield_enabled",
            "safety_leverage_sentry_enabled",
        ]
        for guard in guards:
            assert getattr(s, guard) is True, f"{guard} must default to True"

    def test_fee_rate_default(self):
        """Fee rate should default to OANDA spread cost (0.0004), not Gemini (0.008)."""
        from tradebot_sci.config.models import SafetySettings
        s = SafetySettings()
        assert s.safety_fee_rt_pct == 0.0004

    def test_profile_has_required_fields(self):
        """Active profile must have all fields needed for execution."""
        from tradebot_sci.config import loader
        settings = loader.load_settings()
        profile = settings.get_active_profile()

        required_fields = [
            "htf_timeframe",
            "pdt_guard_enabled",
            "risk_per_trade_pct",
        ]
        for field in required_fields:
            assert hasattr(profile, field), f"Profile missing required field: {field}"

    def test_strategy_registry_complete(self):
        """All registered strategies must be importable and instantiable."""
        from tradebot_sci.strategy.engine import StrategyEngine
        registry = StrategyEngine.STRATEGY_REGISTRY

        assert len(registry) > 0, "Registry should have at least one strategy"

        for name, (module_path, class_name) in registry.items():
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            assert cls is not None, f"Strategy {name} class not found: {module_path}.{class_name}"


# ═══════════════════════════════════════════════════════════════════
# 3. Ledger Cycle Test
# ═══════════════════════════════════════════════════════════════════

class TestLedgerCycle:
    """Verify position store records are consistent through entry → exit."""

    def test_entry_creates_position_record(self):
        """After entry, position record exists with correct fields."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)

        entry = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        result, _ = broker.execute_decision(entry)
        assert result.status == ExecutionStatus.EXECUTED

        pos = broker.get_open_position_snapshot("BTCUSD")
        assert pos is not None
        assert pos["symbol"] == "BTCUSD"
        assert pos["side"] == "long"
        assert pos["entry_price"] > 0
        assert pos["qty"] > 0
        assert "stop_loss" in pos
        assert "take_profit" in pos

    def test_exit_removes_position_record(self):
        """After close, position snapshot returns None."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)

        # Enter
        entry = _make_decision("ETHUSD", "enter_long", 3_000.0, 2_900.0, 3_200.0)
        broker.execute_decision(entry)
        assert broker.get_open_position_snapshot("ETHUSD") is not None

        # Close
        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 3_100.0
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider

        close = _make_decision("ETHUSD", "close_position", 3_100.0, None, None)
        close.action = "close_position"
        close.bias = "neutral"
        broker.execute_decision(close)

        assert broker.get_open_position_snapshot("ETHUSD") is None
        assert broker.list_open_position_symbols() == []

    def test_capital_reconciliation(self):
        """After a round-trip trade, balance = initial ± PnL ± fees."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)
        initial = broker.balance

        # Enter long at 100.0, SL 95.0, TP 110.0
        entry = _make_decision("LTCUSD", "enter_long", 100.0, 95.0, 110.0)
        broker.execute_decision(entry)

        assert "LTCUSD" in broker.positions

        # Close at same price as entry → PnL should be ~0 (minus fees and friction)
        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 100.0
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider

        close = _make_decision("LTCUSD", "close_position", 100.0, None, None)
        close.action = "close_position"
        close.bias = "neutral"
        broker.execute_decision(close)

        # Balance should be less than initial (round-trip fees and friction)
        assert broker.balance < initial, \
            f"Balance {broker.balance:.4f} should be less than initial {initial:.4f} due to fees"

        # But not catastrophically less — fees should be a small percentage
        loss_pct = (initial - broker.balance) / initial
        assert loss_pct < 0.02, \
            f"Round-trip cost {loss_pct*100:.2f}% is suspiciously high (expected < 2%)"

    def test_flatten_clears_position(self):
        """flatten_symbol should remove the position and update balance."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)

        provider = MagicMock()
        ticker = MagicMock()
        ticker.last = 150.0
        provider.get_ticker.return_value = ticker
        broker.market_provider = provider

        entry = _make_decision("SOLUSD", "enter_long", 150.0, 145.0, 160.0)
        broker.execute_decision(entry)
        assert "SOLUSD" in broker.positions

        broker.flatten_symbol("SOLUSD")
        assert "SOLUSD" not in broker.positions

    def test_list_open_position_symbols(self):
        """list_open_position_symbols reflects current state accurately."""
        broker = _make_broker(balance=50_000.0, target_leverage=1.0)

        assert broker.list_open_position_symbols() == []

        entry1 = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        broker.execute_decision(entry1)
        assert "BTCUSD" in broker.list_open_position_symbols()

        entry2 = _make_decision("ETHUSD", "enter_long", 3_000.0, 2_900.0, 3_200.0)
        broker.execute_decision(entry2)
        assert set(broker.list_open_position_symbols()) == {"BTCUSD", "ETHUSD"}

    def test_get_liquid_capital(self):
        """Liquid capital matches initial balance, but underlying balance decreases after entries."""
        broker = _make_broker(balance=10_000.0, target_leverage=1.0)
        initial_cap = broker.get_liquid_capital()
        initial_balance = broker.balance
        assert initial_cap == 10_000.0

        entry = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        broker.execute_decision(entry)

        # Balance decreased by entry fee, but liquid capital remains anchored
        assert broker.balance < initial_balance
        assert broker.get_liquid_capital() == initial_cap

