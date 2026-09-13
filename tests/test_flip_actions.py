import time
from types import SimpleNamespace

from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from helpers import make_test_profile
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import AITradeDecision


class _DummyIB:
    def sleep(self, seconds: float) -> None:
        return None


class _FlipExecutor(IbkrExecutor):
    def __init__(self) -> None:
        profile = make_test_profile(
            candle_timeframe="5m",
            market_poll_interval_seconds=10,
            ai_decision_interval_seconds=30,
        )
        super().__init__(
            ib_client=_DummyIB(),
            runtime_settings=profile._settings.runtime,
            profile_settings=profile,
        )
        self._symbol = "SPY"
        self._state = {"position_shares": 10.0}
        self.close_calls = 0
        self.enter_calls = 0
        self.enter_action = None
        self.close_kwargs = None
        self._flip_last_ts = {}
        self._flip_cooldown_seconds = 0

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return dict(self._state)

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        return None

    def _scale_or_close_stock(self, decision: AITradeDecision, **kwargs):
        self.close_calls += 1
        self.close_kwargs = dict(kwargs)
        self._state["position_shares"] = 0.0
        return (
            ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "closed"),
            ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "closed"),
        )

    def _enter_position_for_symbol(self, decision: AITradeDecision, **kwargs):
        self.enter_calls += 1
        self.enter_action = decision.action
        return (
            ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "entered"),
            ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "entered"),
        )


def _decision(action: str) -> AITradeDecision:
    return AITradeDecision(
        symbol="SPY",
        timeframe="5m",
        bias="long",
        phase="continuation",
        action=action,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        risk_per_trade_pct=0.01,
        max_position_size_pct=0.05,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="test",
        invalidation_conditions="n/a",
        management_instructions="n/a",
        notes="test",
    )


def test_flip_executes_close_and_reverse():
    executor = _FlipExecutor()
    decision = _decision("flip_to_short")
    result, outcome = executor._flip_position_for_symbol(decision)
    assert outcome.status == ExecutionOutcomeType.SUCCESS_SUBMITTED
    assert outcome.status != ExecutionOutcomeType.BLOCKED_EXISTING
    assert result.status == ExecutionStatus.EXECUTED
    assert executor.close_calls == 1
    assert executor.enter_calls == 1
    assert executor.enter_action == "enter_short"
    assert executor.close_kwargs is not None
    assert executor.close_kwargs.get("bypass_hold_guard") is True
    assert executor.close_kwargs.get("bypass_pdt_exit") is True


def test_flip_cooldown_blocks_when_pdt_guard_enabled():
    executor = _FlipExecutor()
    executor._pdt_guard_enabled = True
    executor._flip_cooldown_seconds = 600
    executor._flip_last_ts["SPY"] = time.time()
    decision = _decision("flip_to_short")
    result, outcome = executor._flip_position_for_symbol(decision)
    assert outcome.status == ExecutionOutcomeType.BLOCKED_GUARD
    assert result.status == ExecutionStatus.STAND_ASIDE


def test_flip_blocked_on_long_only_caps():
    decision = _decision("flip_to_short")
    blocked = validate_decision(
        decision,
        execution_capabilities={"long_only": True, "supports_short": False, "flip_allowed": True},
    )
    assert blocked.action == "stand_aside"
