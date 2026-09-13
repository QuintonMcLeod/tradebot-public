from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import tradebot_sci.runtime.cycle as cycle
from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionOutcomeType, ExecutionResult, ExecutionStatus
from tradebot_sci.strategy.decisions import AITradeDecision


class DummyEngine:
    def __init__(self, symbol: str):
        self._symbol = symbol
        self.last_strat_name: str = "DummyStrategy"
        self.last_strat_grade: str = "N/A"
        self.last_strat_score: float = 0.0

    def score_structure(self, snapshot):  # noqa: ANN001
        return 1.0, "ok"

    def score_icc_readiness(self, snapshot):  # noqa: ANN001
        return 1.0, "ok"

    def score_icc_grade(self, snapshot):  # noqa: ANN001
        return 1.0, "B", "ok"

    def decide(self, timeframe, open_position=None, snapshot=None, execution_capabilities=None, current_capital=None):  # noqa: ANN001
        return AITradeDecision(
            symbol=self._symbol,
            timeframe=timeframe,
            bias="neutral",
            phase="trend",
            action="hold",
            entry_price=None,
            entry_zone=None,
            stop_loss=None,
            take_profit=None,
            risk_per_trade_pct=None,
            max_position_size_pct=None,
            time_in_force_sec=None,
            urgency="low",
            structure_summary="test",
            invalidation_conditions="N/A",
            management_instructions="hold",
            notes="test",
        )


class DummyExecutor:
    is_paper = True

    def __init__(self, open_sizes: dict[str, float]):
        self._open_sizes = open_sizes
        self.executed: list[str] = []

    def get_open_position_snapshot(self, symbol: str):
        size = self._open_sizes.get(symbol, 0.0)
        if abs(size) < 1e-8:
            return None
        return {"side": "long" if size > 0 else "short", "size": size, "avg_price": 1.0}

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return {"position_shares": self._open_sizes.get(symbol, 0.0)}

    def execute_decision(self, decision: AITradeDecision):
        self.executed.append(decision.symbol)
        return (
            ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "ok"),
            ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "ok"),
        )

    def get_liquid_capital(self, symbol: str = None):
        return 10000.0

    def list_open_position_symbols(self):
        return [s for s, size in self._open_sizes.items() if abs(size) > 1e-8]


def test_build_candidate_list_returns_all_open_positions(monkeypatch):
    monkeypatch.setattr(cycle, "fetch_snapshot", lambda *_args, **_kwargs: SimpleNamespace(symbol="TEST", timeframe="5m", candles=[]))
    executor = DummyExecutor({"AAA": 1.0, "BBB": 2.0})
    engines = {"AAA": DummyEngine("AAA"), "BBB": DummyEngine("BBB")}

    profile_settings = SimpleNamespace(
        structure_score_threshold=0.5,
        multi_position_enabled=True,
        max_concurrent_positions=5,
    )
    market_settings = SimpleNamespace(max_candles=200)

    candidates, _ = cycle.build_candidate_list(
        executor,
        engines,
        provider=None,
        symbols=["AAA", "BBB"],
        timeframe="5m",
        profile_settings=profile_settings,
        market_settings=market_settings,
        strike_tracker=None,
        now=datetime.now(timezone.utc),
    )
    # Both symbols have open positions — they should appear as existing positions
    assert len(candidates) >= 2
    assert all(c[3] == "existing position" for c in candidates)


def test_process_candidate_cycle_can_manage_multiple_positions(monkeypatch):
    monkeypatch.setattr(cycle, "validate_decision", lambda decision, **_kwargs: decision)
    executor = DummyExecutor({"AAA": 1.0, "BBB": 2.0})
    engines = {"AAA": DummyEngine("AAA"), "BBB": DummyEngine("BBB")}
    snap_a = SimpleNamespace(symbol="AAA", timeframe="5m", candles=[])
    snap_b = SimpleNamespace(symbol="BBB", timeframe="5m", candles=[])
    candidates = [("AAA", snap_a, 0.0, "existing position"), ("BBB", snap_b, 0.0, "existing position")]

    result = cycle.process_candidate_cycle(
        executor,
        engines,
        profile=type("P", (), {"candle_timeframe": "5m"})(),
        profile_settings=type("S", (), {"pair_selector_max_spread_bps": 25.0})(),
        settings=None,
        strike_tracker=None,
        candidates=candidates,
        stop_after_submit=False,
    )

    # DummyEngine.decide() returns action="hold" for existing positions,
    # which process_candidate_cycle counts as "blocked" (AI decided to hold).
    # Both candidates should be attempted.
    success_symbol, attempts, blocked, skipped = result
    assert attempts == 2
    assert blocked == 2  # Both "hold" decisions are counted as blocked
