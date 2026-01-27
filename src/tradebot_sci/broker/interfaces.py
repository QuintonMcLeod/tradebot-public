from __future__ import annotations

from typing import Iterable, Protocol

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult
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

    def _fetch_symbol_state(self, symbol: str) -> dict:
        ...

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        ...

