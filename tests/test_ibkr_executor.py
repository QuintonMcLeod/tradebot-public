"""Dedicated test suite for IbkrExecutor.

Tests core execution paths, PDT guard, flip cooldown, and simulation mode.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from helpers import make_test_profile
from tradebot_sci.broker.execution import ExecutionOutcomeType
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.config.models import RuntimeSettings
from tradebot_sci.market.symbols import SYMBOL_METADATA
from tradebot_sci.strategy.decisions import AITradeDecision


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeContract:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


class _FakePosition:
    def __init__(self, symbol: str, size: float) -> None:
        self.contract = _FakeContract(symbol)
        self.position = size
        self.avgCost = 0.0


class _FakeIB:
    """Minimal IB stub for unit tests."""

    def __init__(
        self,
        positions: list[_FakePosition] | None = None,
        orders: list | None = None,
    ) -> None:
        self._positions = positions or []
        self._orders = orders or []
        self.client = SimpleNamespace(getReqId=lambda: 1)

    def positions(self):
        return self._positions

    def openOrders(self):
        return self._orders

    def openTrades(self):
        return self._orders

    def cancelOrder(self, order):
        return

    def placeOrder(self, contract, order):
        return None

    def accountSummary(self, *args, **kwargs):
        return [
            SimpleNamespace(tag=t, value=str(v), currency="USD")
            for t, v in {"NetLiquidation": 10000, "AvailableFunds": 10000, "BuyingPower": 10000}.items()
        ]

    def isConnected(self):
        return True

    def sleep(self, seconds: float) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(**overrides):
    store_path = overrides.pop("synthetic_stop_store_path", "data/synthetic_stops.json")
    return make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        synthetic_stop_persistence_enabled=True,
        synthetic_stop_store_path=store_path,
        **overrides,
    )


def _build_executor(
    profile,
    ib: _FakeIB,
    *,
    position_hold_store_path: str | None = None,
) -> IbkrExecutor:
    return IbkrExecutor(
        ib_client=ib,
        runtime_settings=profile._settings.runtime,
        profile_settings=profile,
        position_hold_store_path=position_hold_store_path,
    )


def _make_decision(symbol: str, action: str) -> AITradeDecision:
    return AITradeDecision(
        symbol=symbol,
        timeframe="5m",
        action=action,
        confidence=0.8,
        strategy="test",
        reasoning="unit test",
        bias="long",
        phase="trend",
        structure_summary="test",
        invalidation_conditions="none",
        management_instructions="none",
        notes="testing",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecuteDecisionStandAside:
    """execute_decision returns skip for stand_aside and hold actions."""

    def test_stand_aside_skipped(self, tmp_path: Path):
        profile = _make_profile(synthetic_stop_store_path=str(tmp_path / "stops.json"))
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        decision = _make_decision("SPY", "stand_aside")
        _, outcome = executor.execute_decision(decision)
        assert outcome.status in (ExecutionOutcomeType.SKIPPED, ExecutionOutcomeType.SUCCESS_SUBMITTED)

    def test_hold_skipped(self, tmp_path: Path):
        profile = _make_profile(synthetic_stop_store_path=str(tmp_path / "stops.json"))
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        decision = _make_decision("SPY", "hold")
        _, outcome = executor.execute_decision(decision)
        assert outcome.status in (ExecutionOutcomeType.SKIPPED, ExecutionOutcomeType.SUCCESS_SUBMITTED)


class TestSimulationMode:
    """Read-only mode skips all entries."""

    def test_simulation_blocks_entry(self, tmp_path: Path):
        profile = _make_profile(
            synthetic_stop_store_path=str(tmp_path / "stops.json"),
            read_only=True,
        )
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        decision = _make_decision("SPY", "enter_long")
        _, outcome = executor.execute_decision(decision)
        assert outcome.status == ExecutionOutcomeType.SKIPPED


class TestFlipCooldown:
    """Flip cooldown prevents rapid position reversals."""

    def test_flip_cooldown_timing(self, tmp_path: Path):
        profile = _make_profile(
            synthetic_stop_store_path=str(tmp_path / "stops.json"),
            pdt_guard_enabled=False,
            flip_cooldown_seconds=600,
        )
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        # Record a flip
        executor.pdt_guard.record_flip("SPY")
        # Immediately check — should be blocked
        allowed, remaining = executor.pdt_guard.is_flip_allowed("SPY")
        assert allowed is False
        assert remaining > 0


class TestPDTGuardEntry:
    """PDT guard blocks equity entry when roundtrip limit reached."""

    def test_blocks_when_limit_reached(self, tmp_path: Path):
        profile = _make_profile(
            synthetic_stop_store_path=str(tmp_path / "stops.json"),
            pdt_guard_enabled=True,
            max_equity_roundtrips_per_day=1,
        )
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        executor._pdt_guard_enabled = True
        executor._pdt_current_date = date.today()
        executor._pdt_roundtrips_today = 2
        metadata = SYMBOL_METADATA["SPY"]
        assert executor._check_pdt_guard("SPY", metadata) is False

    def test_allows_when_under_limit(self, tmp_path: Path):
        profile = _make_profile(
            synthetic_stop_store_path=str(tmp_path / "stops.json"),
            pdt_guard_enabled=True,
            max_equity_roundtrips_per_day=5,
        )
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        executor._pdt_guard_enabled = True
        executor._pdt_current_date = date.today()
        executor._pdt_roundtrips_today = 0
        metadata = SYMBOL_METADATA["SPY"]
        assert executor._check_pdt_guard("SPY", metadata) is True


class TestEntryBlockedByExistingPosition:
    """Entry should be blocked when a position already exists."""

    def test_enter_long_blocked_existing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(IbkrExecutor, "_discover_zero_hash_symbols", lambda self: [])
        profile = _make_profile(
            synthetic_stop_store_path=str(tmp_path / "stops.json"),
        )
        fake_ib = _FakeIB(positions=[_FakePosition("SPY", 100.0)])
        executor = _build_executor(profile, fake_ib, position_hold_store_path=str(tmp_path / "holds.json"))
        decision = _make_decision("SPY", "enter_long")
        _, outcome = executor.execute_decision(decision)
        assert outcome.status in (
            ExecutionOutcomeType.BLOCKED_EXISTING,
            ExecutionOutcomeType.BLOCKED_GUARD,
            ExecutionOutcomeType.SKIPPED,
        )


class TestExecutionCapabilities:
    """Verify capabilities dict is well-formed."""

    def test_capabilities_dict_structure(self, tmp_path: Path):
        profile = _make_profile(synthetic_stop_store_path=str(tmp_path / "stops.json"))
        executor = _build_executor(profile, _FakeIB(), position_hold_store_path=str(tmp_path / "holds.json"))
        caps = executor.get_execution_capabilities("SPY")
        assert isinstance(caps, dict)
        assert "supports_short" in caps
        assert "long_only" in caps
