from __future__ import annotations

import logging
from typing import Any, Iterable, List, Protocol
from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult, ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.strategy.decisions import AITradeDecision

logger = logging.getLogger(__name__)


class IExchangeBroker(Protocol):
    """High-level broker interface used by the runtime loop.

    This intentionally mirrors the operations the loop needs (execute/cancel/flatten/state),
    so the strategy/ICC logic stays API-agnostic.
    """

    def cancel_all_orders_for_symbol(self, symbol: str) -> None: ...

    def flatten_symbol(self, symbol: str) -> None: ...

    def get_open_position_snapshot(self, symbol: str) -> dict | None: ...

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]: ...

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]: ...

    def refresh_account_summary(self) -> None: ...

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]: ...

    def summarize_pnl(self) -> None: ...

    def get_liquid_capital(self, symbol: str | None = None) -> float: ...

    def get_total_equity(self) -> float:
        """Return total account equity (cash + position value).
        
        Used by safety guards (drawdown breaker, leverage sentry) that need
        the full picture.  Distinct from get_liquid_capital() which returns
        only free cash available for new trades.
        """
        ...

    def get_display_cash(self) -> float:
        """Return actual tracked cash balance for GUI display."""
        ...

    def sync_profile(self, profile) -> None:
        """Dynamically update the broker's profile settings (Hot-Reload)."""
        ...


class NoOpExchangeBroker(IExchangeBroker):
    """A Null Object implementation of IExchangeBroker that does nothing."""

    def cancel_all_orders_for_symbol(self, *args, **kwargs) -> None: pass

    def flatten_symbol(self, *args, **kwargs) -> None: pass

    def get_open_position_snapshot(self, *args, **kwargs) -> dict | None: return None

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        return (
            ExecutionResult(status=ExecutionStatus.RISK_SUPPRESSED, symbol=decision.symbol, reason="NoOp Broker"),
            ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=decision.symbol, reason="NoOp Broker")
        )

    def should_block_for_hold(self, *args, **kwargs) -> tuple[bool, str | None, float | None]:
        return False, None, None

    def refresh_account_summary(self) -> None: pass

    def evaluate_synthetic_stops(self, *args, **kwargs) -> Iterable[ExecutionResult]: return []

    def summarize_pnl(self) -> None: pass

    def get_liquid_capital(self, symbol: str | None = None) -> float: return 0.0

    def get_total_equity(self) -> float: return 0.0

    def get_display_cash(self) -> float: return 0.0

    def sync_profile(self, profile) -> None: pass

    def place_order(self, *args, **kwargs) -> Any:
        logger.warning("[NO-OP] Order placement blocked (Asset Class Disabled).")
        return None

    def cancel_order(self, *args, **kwargs) -> Any: return None

    def get_positions(self, *args, **kwargs) -> Any: return []

    def get_open_orders(self, *args, **kwargs) -> Any: return []

    def get_recent_fills(self, *args, **kwargs) -> Any: return []

    def list_open_position_symbols(self) -> List[str]: return []

    def _fetch_symbol_state(self, *args, **kwargs) -> dict: return {}

    def _has_active_orders_or_position(self, *args, **kwargs) -> bool: return False

    @property
    def profile(self): return None
    
    @property
    def position_hold_store(self): return None

