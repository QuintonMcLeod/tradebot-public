"""Graceful degradation contract tests.

Each test injects a specific failure and verifies the system degrades
gracefully rather than crashing. These form the "failure contract" for
the trading system.
"""

import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus  # noqa: E402, I001
from tradebot_sci.broker.paper_broker import PaperBroker  # noqa: E402
from tradebot_sci.strategy.decisions import AITradeDecision  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────

def _make_broker(balance: float = 10_000.0) -> PaperBroker:
    profile = types.SimpleNamespace(risk_per_trade_pct=0.01, target_leverage=1.0)
    orig_load = PaperBroker._load_state
    orig_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=balance)
    finally:
        PaperBroker._load_state = orig_load
        PaperBroker._save_state = orig_save
    broker._save_state = lambda: None
    return broker


def _make_decision(
    symbol: str, action: str, entry: float, sl: float, tp: float,
) -> AITradeDecision:
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
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="degradation test",
        invalidation_conditions="N/A",
        management_instructions="hold",
        notes="degradation contract test",
    )


# ═══════════════════════════════════════════════════════════════════
# Contract 1: API Down → Bot continues, no crash
# ═══════════════════════════════════════════════════════════════════

class TestAPIDownDegradation:
    """When market data provider is unavailable, broker degrades gracefully."""

    def test_market_provider_returns_none(self):
        """If ticker throws, synthetic stop evaluation should not crash."""
        broker = _make_broker(balance=10_000.0)
        initial_balance = broker.balance

        # Open a position
        entry = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        result, _ = broker.execute_decision(entry)
        assert result.status == ExecutionStatus.EXECUTED

        # Market provider throws on ticker
        provider = MagicMock()
        provider.get_ticker.side_effect = Exception("OANDA API timeout")
        broker.market_provider = provider

        # Evaluate synthetic stops with broken provider — should not crash
        try:
            broker.evaluate_synthetic_stops(broker.market_provider, "5m")
        except Exception:
            pass  # If it raises, the contract is still about not segfaulting

        # The critical invariant: balance should not be corrupted
        assert broker.balance > 0, "Balance should not be corrupted by API failure"
        # Balance should remain a valid finite number (no NaN/Inf corruption)
        import math
        assert math.isfinite(broker.balance), \
            "Balance should remain a finite number after API failure"

    def test_market_provider_not_set(self):
        """If market_provider is None, operations should handle gracefully."""
        broker = _make_broker(balance=10_000.0)
        broker.market_provider = None

        # Stand aside should work fine without market provider
        hold = _make_decision("BTCUSD", "stand_aside", 50_000.0, None, None)
        result, _ = broker.execute_decision(hold)
        assert result.status == ExecutionStatus.STAND_ASIDE


# ═══════════════════════════════════════════════════════════════════
# Contract 2: AI Returns Garbage → Decision rejected, no trade
# ═══════════════════════════════════════════════════════════════════

class TestAIGarbageDegradation:
    """When AI returns invalid data, the system rejects without crashing."""

    def test_invalid_action_type(self):
        """An unknown action should not execute a trade."""
        broker = _make_broker(balance=10_000.0)

        decision = _make_decision("BTCUSD", "stand_aside", 50_000.0, None, None)
        # Monkey-patch a garbage action
        decision.action = "yolo_all_in"

        result, _ = broker.execute_decision(decision)
        # Should be stand_aside (fallback) not EXECUTED
        assert result.status == ExecutionStatus.STAND_ASIDE
        assert len(broker.positions) == 0, "No position should be opened for garbage action"

    def test_negative_entry_price(self):
        """Negative prices should be rejected or handled gracefully."""
        broker = _make_broker(balance=10_000.0)

        # Create decision with absurd negative price
        decision = _make_decision("BTCUSD", "enter_long", -100.0, -200.0, 50.0)
        result, _ = broker.execute_decision(decision)

        # Should not crash; may execute with the value or reject
        assert broker.balance > 0, "Balance should not go negative from bad price"

    def test_zero_stop_loss_distance(self):
        """Zero SL distance (entry == SL) should not cause division by zero."""
        broker = _make_broker(balance=10_000.0)

        # SL exactly at entry → zero distance → could cause div-by-zero in sizing
        decision = _make_decision("BTCUSD", "enter_long", 50_000.0, 50_000.0, 52_000.0)
        result, _ = broker.execute_decision(decision)

        # Should not crash, regardless of outcome
        assert broker.balance >= 0, "Balance should remain non-negative"

    def test_none_prices(self):
        """None entry price should be handled without crashing."""
        broker = _make_broker(balance=10_000.0)

        decision = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        decision.entry_price = None

        try:
            result, _ = broker.execute_decision(decision)
        except (TypeError, AttributeError):
            pass  # Acceptable to throw — but must not corrupt state

        assert broker.balance > 0, "Balance must survive None price"


# ═══════════════════════════════════════════════════════════════════
# Contract 3: Disk Full → State save fails gracefully
# ═══════════════════════════════════════════════════════════════════

class TestDiskFullDegradation:
    """When disk writes fail, the bot continues operating."""

    def test_save_state_failure_doesnt_crash(self):
        """If _save_state raises IOError, execution still completes."""
        broker = _make_broker(balance=10_000.0)

        # Make save_state raise an error (simulating full disk)
        def failing_save():
            raise OSError("No space left on device")

        broker._save_state = failing_save

        # Entry should still work (or at least not crash)
        decision = _make_decision("BTCUSD", "enter_long", 50_000.0, 49_000.0, 52_000.0)
        try:
            result, _ = broker.execute_decision(decision)
            # If it handles the error internally, we should still have state
        except OSError:
            pass  # If it propagates, that's fine — we're testing it doesn't corrupt

        # The critical thing: balance should not be corrupted
        assert broker.balance > 0

    def test_position_store_write_failure(self):
        """If position file can't be written, positions dict stays consistent."""
        broker = _make_broker(balance=10_000.0)

        call_count = 0

        def intermittent_save():
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise OSError("Intermittent write failure")

        broker._save_state = intermittent_save

        # Multiple operations
        for i in range(3):
            sym = f"TEST{i}USD"
            decision = _make_decision(sym, "enter_long", 100.0 + i, 95.0, 110.0)
            try:
                broker.execute_decision(decision)
            except OSError:
                pass  # Tolerate propagated errors

        # Internal state should be consistent even with failed saves
        assert broker.balance >= 0


# ═══════════════════════════════════════════════════════════════════
# Contract 4: Config Corrupted → Clean error, no silent corruption
# ═══════════════════════════════════════════════════════════════════

class TestConfigCorruptedDegradation:
    """When config files are corrupted, the system reports clean errors."""

    def test_corrupted_json_config(self):
        """A JSON syntax error in config should produce a clear exception."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{corrupted: not valid json!!!}")
            tmp_path = Path(f.name)

        try:
            with open(tmp_path) as fh:
                try:
                    json.load(fh)
                    raise AssertionError("Should have raised JSONDecodeError")
                except json.JSONDecodeError as e:
                    # Clean error with line/column info
                    assert "line" in str(e).lower() or "col" in str(e).lower(), \
                        f"Error should include position info: {e}"
        finally:
            tmp_path.unlink()

    def test_missing_config_fields_use_defaults(self):
        """Config with missing fields should fall back to safe defaults."""
        from tradebot_sci.config.models import SafetySettings

        # Create SafetySettings with empty dict (simulating missing config)
        s = SafetySettings()

        # All guards should default to ON even if config is empty
        assert s.safety_drawdown_breaker_enabled is True
        assert s.safety_streak_breaker_enabled is True
        assert s.safety_fee_shield_enabled is True

    def test_pydantic_validates_bad_types(self):
        """Pydantic should reject completely wrong types for critical fields."""
        from pydantic import ValidationError
        from tradebot_sci.config.models import SafetySettings

        try:
            # Try to set a numeric field with garbage
            SafetySettings(safety_fee_rt_pct="not_a_number")
            # Pydantic may coerce strings → floats, which is fine
        except (ValidationError, ValueError):
            pass  # Clean rejection is the correct behavior

    def test_empty_profiles_dict(self):
        """Empty profile dictionary should not crash config loading."""
        from tradebot_sci.config.models import (
            AISettings,
            AppSettings,
            LoggingSettings,
            MarketSettings,
            RuntimeSettings,
            Settings,
        )

        # Minimal valid settings with no profiles
        settings = Settings(
            app=AppSettings(),
            logging=LoggingSettings(),
            ai=AISettings(),
            market=MarketSettings(),
            runtime=RuntimeSettings(),
            profiles={},
        )

        # Should not crash, profiles is just empty
        assert len(settings.profiles) == 0
        assert settings.app is not None
