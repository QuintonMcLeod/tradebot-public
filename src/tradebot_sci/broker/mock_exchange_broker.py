from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from tradebot_sci.broker.order_models import OrderRequest, OrderSide, OrderState, OrderStatus, OrderType
from tradebot_sci.config.broker import BrokerSettings
from tradebot_sci.config.models import RuntimeSettings, TradingProfileSettings
from tradebot_sci.market.models import Ticker
from tradebot_sci.strategy.decisions import AITradeDecision

logger = logging.getLogger(__name__)


class MockExchangeBroker:
    """Safe placeholder broker for the `market.exchange_provider=alternative` path.

    It never reaches out to a real venue. It exists so the runtime can run end-to-end
    while the real alternative exchange integration is implemented.
    """

    def __init__(
        self,
        broker_settings: BrokerSettings | None,
        runtime: RuntimeSettings,
        profile_settings: TradingProfileSettings,
        allowed_symbols: set[str] | None = None,
    ) -> None:
        self.broker_settings = broker_settings
        self.runtime = runtime
        self.profile_settings = profile_settings
        self.allowed_symbols = allowed_symbols
        self._orders: dict[int, OrderState] = {}
        self._next_order_id = 1
        self._positions: dict[str, dict] = {}
        self._scale_in_counts: dict[str, int] = {}

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        symbol_key = symbol.upper()
        cancelled = 0
        for order in list(self._orders.values()):
            if order.request.symbol != symbol_key:
                continue
            if order.status != OrderStatus.OPEN:
                continue
            order.status = OrderStatus.CANCELED
            order.updated_at = datetime.now(timezone.utc)
            order.reason = "cancel_all_orders_for_symbol"
            cancelled += 1
        logger.info("[MOCK_BROKER] cancel_all_orders_for_symbol symbol=%s cancelled=%s", symbol_key, cancelled)

    def get_execution_capabilities(self, symbol: str) -> dict:
        return {
            "venue": "MOCK",
            "venue_name": "MOCK",
            "asset_class": "unknown",
            "exchange": "mock",
            "long_only": False,
            "supports_short": True,
            "supports_bracket_children": True,
            "supports_native_brackets": True,
            "supports_native_stops": True,
            "requires_synthetic_stops": False,
        }

    def flatten_symbol(self, symbol: str) -> None:
        symbol_key = symbol.upper()
        if symbol_key in self._positions:
            self._positions.pop(symbol_key, None)
        self._scale_in_counts[symbol_key] = 0
        self.cancel_all_orders_for_symbol(symbol_key)
        logger.info("[MOCK_BROKER] flatten_symbol symbol=%s", symbol_key)

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        symbol_key = symbol.upper()
        pos = self._positions.get(symbol_key)
        if not pos:
            self._scale_in_counts[symbol_key] = 0
            return None
        merged = {**pos}
        merged["scale_ins_taken"] = int(self._scale_in_counts.get(symbol_key, 0))
        merged["max_scale_ins_per_leg"] = int(getattr(self.runtime, "max_scale_ins_per_leg", 2))
        # Mock broker stores htf_neutral_bars/pyramid_count directly in position dict
        merged["htf_neutral_bars"] = int(merged.get("htf_neutral_bars", 0))
        merged["pyramid_count"] = int(merged.get("pyramid_count", 1))
        return merged

    def update_position_metadata(self, symbol: str, snapshot) -> None:
        """Update position metadata like htf_neutral_bars counter (mock implementation)."""
        symbol_key = symbol.upper()
        pos = self._positions.get(symbol_key)
        if not pos:
            return

        # Update HTF neutral bar counter
        if snapshot and hasattr(snapshot, "trend_htf") and snapshot.trend_htf:
            from tradebot_sci.market.trend_enums import TrendDirection
            if snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
                pos["htf_neutral_bars"] = pos.get("htf_neutral_bars", 0) + 1
            else:
                pos["htf_neutral_bars"] = 0

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        symbol_key = decision.symbol.upper()
        if self.allowed_symbols is not None and symbol_key not in self.allowed_symbols:
            return (
                ExecutionResult(
                    status=ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG,
                    symbol=symbol_key,
                    reason="symbol not allowed in this run",
                ),
                ExecutionOutcome(
                    status=ExecutionOutcomeType.BLOCKED_SYMBOL_NOT_ALLOWED,
                    symbol=symbol_key,
                    reason="symbol not allowed",
                ),
            )

        if decision.action in {"stand_aside", "hold"}:
            return (
                ExecutionResult(status=ExecutionStatus.STAND_ASIDE, symbol=symbol_key, reason="stand aside"),
                ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=symbol_key, reason="stand aside"),
            )

        if decision.action in {"flip_to_long", "flip_to_short"}:
            pos = self._positions.get(symbol_key)
            if not pos or float(pos.get("size", 0.0)) == 0.0:
                return (
                    ExecutionResult(status=ExecutionStatus.STAND_ASIDE, symbol=symbol_key, reason="no position to flip"),
                    ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=symbol_key, reason="no position to flip"),
                )
            current_side = pos.get("side")
            target_side = "long" if decision.action == "flip_to_long" else "short"
            if current_side == target_side:
                return (
                    ExecutionResult(status=ExecutionStatus.STAND_ASIDE, symbol=symbol_key, reason="already on target side"),
                    ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=symbol_key, reason="already on target side"),
                )
            self.flatten_symbol(symbol_key)
            decision = decision.copy(update={"action": "enter_long" if target_side == "long" else "enter_short"})

        if decision.action == "close_position":
            self.flatten_symbol(symbol_key)
            return (
                ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=symbol_key, reason="flattened (mock)"),
                ExecutionOutcome(status=ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol=symbol_key, reason="flattened"),
            )

        if decision.action == "scale_out":
            pos = self._positions.get(symbol_key)
            if not pos:
                return (
                    ExecutionResult(status=ExecutionStatus.STAND_ASIDE, symbol=symbol_key, reason="no position"),
                    ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=symbol_key, reason="no position"),
                )
            new_size = float(pos.get("size", 0.0)) * (1.0 - float(self.runtime.scale_out_fraction))
            if abs(new_size) < float(self.runtime.min_position_size_to_scale):
                self.flatten_symbol(symbol_key)
            else:
                pos["size"] = new_size
            return (
                ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=symbol_key, reason="scaled out (mock)"),
                ExecutionOutcome(status=ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol=symbol_key, reason="scaled out"),
            )

        if decision.action == "scale_in":
            max_adds = int(getattr(self.runtime, "max_scale_ins_per_leg", 2))
            if max_adds <= 0:
                return (
                    ExecutionResult(status=ExecutionStatus.RISK_SUPPRESSED, symbol=symbol_key, reason="scale_in disabled"),
                    ExecutionOutcome(status=ExecutionOutcomeType.BLOCKED_GUARD, symbol=symbol_key, reason="scale_in disabled"),
                )
            current_adds = int(self._scale_in_counts.get(symbol_key, 0))
            if current_adds >= max_adds:
                return (
                    ExecutionResult(status=ExecutionStatus.RISK_SUPPRESSED, symbol=symbol_key, reason="max scale_in reached"),
                    ExecutionOutcome(status=ExecutionOutcomeType.BLOCKED_GUARD, symbol=symbol_key, reason="max scale_in reached"),
                )

        if decision.action in {"enter_long", "enter_short", "scale_in"}:
            # Maker-first execution policy (mock):
            # - low urgency -> post-only limit at best bid/ask (resting)
            # - high urgency -> market (fill immediately)
            qty = 1.0
            if decision.action == "scale_in" and symbol_key in self._positions:
                qty = abs(float(self._positions[symbol_key].get("size", 1.0))) + 1.0

            side = OrderSide.BUY if decision.action != "enter_short" else OrderSide.SELL
            urgency = (decision.urgency or "low").lower()
            ticker = getattr(self, "_last_ticker", {}).get(symbol_key) if hasattr(self, "_last_ticker") else None
            maker_enabled = bool(getattr(self.profile_settings, "maker_first_enabled", True))
            use_maker = maker_enabled and urgency in {"low", "medium"}

            if use_maker and ticker and ticker.bid is not None and ticker.ask is not None:
                mid = (ticker.bid + ticker.ask) / 2.0
                offset_bps = float(getattr(self.profile_settings, "maker_first_offset_bps", 0.0))
                offset = mid * (offset_bps / 10_000.0)
                price = (ticker.bid - offset) if side == OrderSide.BUY else (ticker.ask + offset)
                req = OrderRequest(
                    symbol=symbol_key,
                    side=side,
                    order_type=OrderType.LIMIT,
                    qty=qty,
                    price=price,
                    post_only=True,
                )
                order = self._create_order(req)
                if decision.action == "scale_in":
                    current_adds = int(self._scale_in_counts.get(symbol_key, 0))
                    self._scale_in_counts[symbol_key] = current_adds + 1
                return (
                    ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=symbol_key, reason="maker order placed (mock)"),
                    ExecutionOutcome(
                        status=ExecutionOutcomeType.SUCCESS_SUBMITTED,
                        symbol=symbol_key,
                        reason="maker order placed (mock)",
                        order_ids=[order.order_id],
                    ),
                )

            # taker-style market fill
            fill_price = float(decision.entry_price) if decision.entry_price is not None else None
            req = OrderRequest(
                symbol=symbol_key,
                side=side,
                order_type=OrderType.MARKET,
                qty=qty,
            )
            order = self._create_order(req)
            self._fill_order(order.order_id, fill_price=fill_price)
            if decision.action == "scale_in":
                self._scale_in_counts[symbol_key] = current_adds + 1
            return (
                ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=symbol_key, reason="taker order filled (mock)"),
                ExecutionOutcome(
                    status=ExecutionOutcomeType.SUCCESS_SUBMITTED,
                    symbol=symbol_key,
                    reason="taker order filled (mock)",
                    order_ids=[order.order_id],
                ),
            )

        return (
            ExecutionResult(status=ExecutionStatus.ERROR, symbol=symbol_key, reason=f"unsupported action={decision.action}"),
            ExecutionOutcome(status=ExecutionOutcomeType.ERROR, symbol=symbol_key, reason="unsupported action"),
        )

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        return False, None, None

    def refresh_account_summary(self) -> None:
        return

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        # In alternative/mock mode, use this hook to:
        # - track latest ticker for maker-first pricing
        # - cancel stale resting entry orders
        # - simulate fills when price crosses resting limits
        self._last_ticker = getattr(self, "_last_ticker", {})
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=int(getattr(self.profile_settings, "order_timeout_seconds", 30)))
        results: list[ExecutionResult] = []

        symbols = set(self._positions.keys()) | {order.request.symbol for order in self._orders.values()}
        if self.allowed_symbols:
            symbols |= {s.upper() for s in self.allowed_symbols}
        for sym in symbols:
            ticker = getattr(market_provider, "get_ticker", lambda *_: None)(sym)
            if ticker:
                self._last_ticker[sym] = ticker

        for order in list(self._orders.values()):
            if order.status != OrderStatus.OPEN:
                continue
            age = now - order.created_at
            if age > timeout:
                order.status = OrderStatus.CANCELED
                order.updated_at = now
                order.reason = "timeout"
                results.append(ExecutionResult(status=ExecutionStatus.STAND_ASIDE, symbol=order.request.symbol, reason="order timeout"))
                continue
            ticker = self._last_ticker.get(order.request.symbol)
            if not ticker or ticker.last is None or order.request.price is None:
                continue
            last = float(ticker.last)
            if order.request.side == OrderSide.BUY and last <= float(order.request.price):
                self._fill_order(order.order_id, fill_price=order.request.price)
                results.append(ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=order.request.symbol, reason="maker fill (mock)"))
            if order.request.side == OrderSide.SELL and last >= float(order.request.price):
                self._fill_order(order.order_id, fill_price=order.request.price)
                results.append(ExecutionResult(status=ExecutionStatus.EXECUTED, symbol=order.request.symbol, reason="maker fill (mock)"))

        return results

    def summarize_pnl(self) -> None:
        logger.info("[MOCK_BROKER] summarize_pnl positions=%s orders=%s", len(self._positions), len(self._orders))

    def _fetch_symbol_state(self, symbol: str) -> dict:
        pos = self._positions.get(symbol.upper())
        size = float(pos.get("size", 0.0)) if pos else 0.0
        return {
            "position_shares": size,
            "working_orders": sum(
                1 for o in self._orders.values() if o.request.symbol == symbol.upper() and o.status == OrderStatus.OPEN
            ),
            "synthetic_stop_armed": False,
            "open_parent_shares": {},
        }

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        state = state or self._fetch_symbol_state(symbol)
        return abs(state.get("position_shares", 0.0)) > 0.0 or state.get("working_orders", 0) > 0

    def _create_order(self, request: OrderRequest) -> OrderState:
        order_id = self._next_order_id
        self._next_order_id += 1
        now = datetime.now(timezone.utc)
        state = OrderState(
            order_id=order_id,
            request=request,
            status=OrderStatus.OPEN,
            created_at=now,
            updated_at=now,
        )
        self._orders[order_id] = state
        return state

    def _fill_order(self, order_id: int, *, fill_price: float | None) -> None:
        order = self._orders.get(order_id)
        if not order or order.status != OrderStatus.OPEN:
            return
        now = datetime.now(timezone.utc)
        order.status = OrderStatus.FILLED
        order.updated_at = now
        order.filled_qty = order.request.qty
        order.avg_fill_price = fill_price

        symbol = order.request.symbol
        signed_qty = order.request.qty if order.request.side == OrderSide.BUY else -order.request.qty
        existing = self._positions.get(symbol)
        new_size = signed_qty + (float(existing.get("size", 0.0)) if existing else 0.0)
        side = "long" if new_size > 0 else "short" if new_size < 0 else "flat"
        self._positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "size": new_size,
            "avg_price": fill_price,
            "opened_at": (existing.get("opened_at") if existing else now.isoformat()),
        }
