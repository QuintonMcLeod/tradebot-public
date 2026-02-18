from __future__ import annotations

from typing import Iterable, Protocol

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult, ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.strategy.decisions import AITradeDecision


class IExchangeBroker(Protocol):
    """High-level broker interface used by the runtime loop.

    This intentionally mirrors the operations the loop needs (execute/cancel/flatten/state),
    so the strategy/ICC logic stays API-agnostic.
    """

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        ...

    def flatten_symbol(self, symbol: str) -> None:
        ...

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        ...

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        ...

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        ...

    def refresh_account_summary(self) -> None:
        ...

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        ...

    def summarize_pnl(self) -> None:
        ...

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        ...

    def sync_profile(self, profile) -> None:
        """Dynamically update the broker's profile settings (Hot-Reload)."""
        ...


class NoOpExchangeBroker:
    """A Null Object implementation of IExchangeBroker that does nothing."""

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        pass

    def flatten_symbol(self, symbol: str) -> None:
        pass

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        return None

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        # Return a neutral/skipped result
        return (
            ExecutionResult(status=ExecutionStatus.RISK_SUPPRESSED, symbol=decision.symbol, reason="NoOp Broker"),
            ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=decision.symbol, reason="NoOp Broker")
        )

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        return False, None, None

    def refresh_account_summary(self) -> None:
        pass

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        return []

    def summarize_pnl(self) -> None:
        pass

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return 0.0

    def sync_profile(self, profile) -> None:
        pass

    @property
    def profile(self):
        return None
    
    @property
    def position_hold_store(self):
        return None

