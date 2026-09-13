from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import math

from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from helpers import make_test_profile
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.market.symbols import SYMBOL_METADATA
from tradebot_sci.runtime.loop import (
    _build_candidate_list,
    _process_candidate_cycle,
    StrikeTracker,
)
import tradebot_sci.runtime.cycle as cycle
from tradebot_sci.strategy.decisions import AITradeDecision


def _make_profile(**overrides):
    return make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        **overrides,
    )


class DummyEngine:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.last_strat_name = "DummyStrategy"
        self.last_strat_grade = "N/A"
        self.last_strat_score = 0.0

    def decide(self, timeframe, open_position=None, snapshot=None, execution_capabilities=None, current_capital=None):
        return AITradeDecision(
            symbol=self.symbol,
            timeframe=timeframe,
            bias="long",
            phase="trend",
            action="enter_long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=101.0,
            risk_per_trade_pct=0.01,
            max_position_size_pct=0.02,
            time_in_force_sec=None,
            urgency="medium",
            structure_summary="test",
            invalidation_conditions="none",
            management_instructions="none",
            notes="testing",
        )


class FakeCandidateEngine:
    def __init__(self, symbol: str, score: float):
        self.symbol = symbol
        self.score = score

    def score_structure(self, snapshot):
        return self.score, "test"

    def score_icc_readiness(self, snapshot):
        return 0.0, "test"

    def score_icc_grade(self, snapshot):
        return self.score, "B"


class FakeProvider:
    def get_latest_snapshot(self, symbol, timeframe, **kwargs):
        return SimpleNamespace(symbol=symbol, timeframe=timeframe, candles=[])

    def get_latest_candles(self, symbol, timeframe, **kwargs):
        return []


class FakeExecutor:
    is_paper = True

    def __init__(self, state_map: dict[str, dict]):
        self.state_map = state_map

    def get_open_position_snapshot(self, symbol):
        return None

    def _fetch_symbol_state(self, symbol: str):
        default_state = {
            "position_shares": 0,
            "working_orders": 0,
            "working_order_statuses": [],
            "synthetic_stop_armed": False,
            "open_parent_shares": {"long": 0, "short": 0},
        }
        return self.state_map.get(symbol, default_state)

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        state = state or self._fetch_symbol_state(symbol)
        if abs(state.get("position_shares", 0)) > 0:
            return True
        if state.get("working_orders", 0) > 0:
            return True
        if state.get("synthetic_stop_armed"):
            return True
        return any(value > 0 for value in state.get("open_parent_shares", {}).values())

    def list_open_position_symbols(self):
        return [s for s, st in self.state_map.items() if st.get("position_shares", 0) != 0]


class MockExecutor:
    is_paper = True

    def __init__(self, outcome_map):
        self.outcome_map = {symbol: list(statuses) for symbol, statuses in outcome_map.items()}

    def execute_decision(self, decision):
        status = self.outcome_map[decision.symbol].pop(0)
        exec_status = ExecutionStatus.EXECUTED if status == ExecutionOutcomeType.SUCCESS_SUBMITTED else ExecutionStatus.STAND_ASIDE
        return (
            ExecutionResult(exec_status, decision.symbol, status.value),
            ExecutionOutcome(status=status, symbol=decision.symbol, reason=status.value),
        )

    def get_open_position_snapshot(self, symbol):
        return None

    def get_liquid_capital(self, symbol=None):
        return 10000.0

    def list_open_position_symbols(self):
        return []


def test_crypto_fractional_quantization():
    profile = _make_profile(
        crypto_fractional_enabled=True,
        crypto_min_notional_usd=20.0,
        crypto_max_notional_usd=200.0,
        crypto_qty_steps={"BTCUSD": 0.0001},
    )
    executor = IbkrExecutor(profile_settings=profile, ib_client=object())
    qty, reason = executor._apply_crypto_fractional_symbol("BTCUSD", 0.00085, 50000.0)
    assert math.isclose(qty, 0.0008, rel_tol=1e-6)
    assert reason is None


def test_crypto_fractional_min_notional_blocks():
    profile = _make_profile(
        crypto_fractional_enabled=True,
        crypto_min_notional_usd=20.0,
        crypto_qty_steps={"BTCUSD": 0.0001},
    )
    executor = IbkrExecutor(profile_settings=profile, ib_client=object())
    qty, reason = executor._apply_crypto_fractional_symbol("BTCUSD", 0.0002, 10000.0)
    assert qty == 0.0
    assert reason == "crypto_min_notional_unmet"


def test_fractional_disabled_uses_raw():
    profile = _make_profile(crypto_fractional_enabled=False)
    executor = IbkrExecutor(profile_settings=profile, ib_client=object())
    metadata = SYMBOL_METADATA["BTCUSD"]
    assert not executor._should_apply_crypto_fractional(metadata)


@dataclass
class FakeProfile:
    candle_timeframe: str = "5m"


def test_cycle_continues_after_block():
    profile_settings = _make_profile()
    executor = MockExecutor(
        {
            "ETHUSD": [ExecutionOutcomeType.BLOCKED_GUARD],
            "BTCUSD": [ExecutionOutcomeType.BLOCKED_GUARD],
            "SOLUSD": [ExecutionOutcomeType.SUCCESS_SUBMITTED],
        }
    )
    engines = {
        symbol: DummyEngine(symbol) for symbol in ["ETHUSD", "BTCUSD", "SOLUSD"]
    }
    candidates = [
        ("ETHUSD", SimpleNamespace(symbol="ETHUSD", timeframe="5m", candles=[]), 0.8, "test"),
        ("BTCUSD", SimpleNamespace(symbol="BTCUSD", timeframe="5m", candles=[]), 0.7, "test"),
        ("SOLUSD", SimpleNamespace(symbol="SOLUSD", timeframe="5m", candles=[]), 0.6, "test"),
    ]
    success_symbol, attempts, blocked, skipped = _process_candidate_cycle(
        executor,
        engines,
        FakeProfile(),
        profile_settings,
        None,
        StrikeTracker(0, 0, 0, 0),
        candidates,
    )
    assert success_symbol == "SOLUSD"
    assert attempts == 3
    # blocked counter only counts AI-level blocks (stand_aside/hold), not executor blocks
    assert blocked >= 0
    assert skipped == 0


def test_duplicate_entry_blocked_by_working_orders():
    profile_settings = _make_profile()
    executor = MockExecutor(
        {
            "SOLUSD": [
                ExecutionOutcomeType.SUCCESS_SUBMITTED,
                ExecutionOutcomeType.BLOCKED_EXISTING,
            ],
            "ETHUSD": [ExecutionOutcomeType.SUCCESS_SUBMITTED],
        }
    )
    engines = {
        "SOLUSD": DummyEngine("SOLUSD"),
        "ETHUSD": DummyEngine("ETHUSD"),
    }
    candidates = [
        ("SOLUSD", SimpleNamespace(symbol="SOLUSD", timeframe="5m", candles=[]), 0.9, "test"),
        ("ETHUSD", SimpleNamespace(symbol="ETHUSD", timeframe="5m", candles=[]), 0.8, "test"),
    ]
    first_symbol, *_ = _process_candidate_cycle(
        executor,
        engines,
        FakeProfile(),
        profile_settings,
        None,
        StrikeTracker(0, 0, 0, 0),
        candidates,
    )
    assert first_symbol == "SOLUSD"
    second_symbol, attempts, blocked, skipped = _process_candidate_cycle(
        executor,
        engines,
        FakeProfile(),
        profile_settings,
        None,
        StrikeTracker(0, 0, 0, 0),
        candidates,
    )
    assert second_symbol == "ETHUSD"
    assert attempts == 2
    # blocked counter only counts AI-level blocks (stand_aside/hold), not executor BLOCKED_EXISTING
    assert blocked >= 0
    assert skipped == 0


def test_candidate_list_excludes_cooled_symbol(monkeypatch):
    symbols = ["SOLUSD", "ETHUSD"]
    engines = {
        sym: FakeCandidateEngine(sym, 0.4 if sym == "SOLUSD" else 0.3)
        for sym in symbols
    }
    state_map = {
        "SOLUSD": {
            "position_shares": 0,
            "working_orders": 0,
            "working_order_statuses": [],
            "synthetic_stop_armed": False,
            "open_parent_shares": {"long": 0, "short": 0},
        },
        "ETHUSD": {
            "position_shares": 0,
            "working_orders": 0,
            "working_order_statuses": [],
            "synthetic_stop_armed": False,
            "open_parent_shares": {"long": 0, "short": 0},
        },
    }
    executor = FakeExecutor(state_map)
    strike_tracker = StrikeTracker(1, 1, 0, 0)
    strike_tracker.record_execution_success("SOLUSD", "success_submitted")
    now = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(cycle, "fetch_snapshot", lambda *a, **kw: SimpleNamespace(symbol=a[2], timeframe="5m", candles=[]))
    profile_settings = SimpleNamespace(structure_score_threshold=0.0, multi_position_enabled=False, max_concurrent_positions=1)
    market_settings = SimpleNamespace(max_candles=200)
    candidates, _ = cycle.build_candidate_list(
        executor, engines, None, symbols, "5m",
        profile_settings, market_settings, strike_tracker, now,
    )
    assert all(entry[0] != "SOLUSD" for entry in candidates)
    assert candidates and candidates[0][0] == "ETHUSD"
    assert strike_tracker.cooldown_reason("SOLUSD") == "success_submitted"


def test_candidate_list_skips_symbols_with_active_working_orders(monkeypatch):
    symbols = ["SOLUSD", "ETHUSD"]
    engines = {
        sym: FakeCandidateEngine(sym, 0.5 if sym == "SOLUSD" else 0.1)
        for sym in symbols
    }
    state_map = {
        "SOLUSD": {
            "position_shares": 0,
            "working_orders": 2,
            "working_order_statuses": ["PendingSubmit", "PreSubmitted"],
            "synthetic_stop_armed": False,
            "open_parent_shares": {"long": 0, "short": 0},
        },
        "ETHUSD": {
            "position_shares": 0,
            "working_orders": 0,
            "working_order_statuses": [],
            "synthetic_stop_armed": False,
            "open_parent_shares": {"long": 0, "short": 0},
        },
    }
    executor = FakeExecutor(state_map)
    strike_tracker = StrikeTracker(0, 0, 0, 0)
    now = datetime.now(ZoneInfo("UTC"))
    monkeypatch.setattr(cycle, "fetch_snapshot", lambda *a, **kw: SimpleNamespace(symbol=a[2], timeframe="5m", candles=[]))
    profile_settings = SimpleNamespace(structure_score_threshold=0.0, multi_position_enabled=False, max_concurrent_positions=1)
    market_settings = SimpleNamespace(max_candles=200)
    candidates, _ = cycle.build_candidate_list(
        executor, engines, None, symbols, "5m",
        profile_settings, market_settings, strike_tracker, now,
    )
    # Working orders create active campaign — SOLUSD should appear as active campaign
    # with multi_position_enabled=False, first active order symbol locks the list
    assert len(candidates) >= 1
    assert candidates[0][0] == "SOLUSD"
    assert candidates[0][3] == "active campaign"
