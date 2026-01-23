from __future__ import annotations

import logging
from typing import Any, Iterable

try:
    import oandapyV20
    import oandapyV20.endpoints.accounts as accounts
    import oandapyV20.endpoints.orders as orders
    import oandapyV20.endpoints.positions as oanda_positions
    import oandapyV20.endpoints.trades as trades
    HAS_OANDA = True
except ImportError:
    HAS_OANDA = False
from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci.config.models import TradingProfileSettings
from tradebot_sci.strategy.decisions import AITradeDecision

logger = logging.getLogger(__name__)

class OandaExchangeBroker(IExchangeBroker):
    """Broker implementation for OANDA v20 API."""

    def __init__(
        self,
        account_id: str,
        api_key: str,
        profile_settings: TradingProfileSettings,
        environment: str = "practice",
        read_only: bool = True
    ):
        if not HAS_OANDA:
            raise ImportError("OANDA dependencies missing. Please install oandapyV20.")
        
        # Suppress noisy library logging (especially the 404 spam)
        logging.getLogger("oandapyV20.oandapyV20").setLevel(logging.CRITICAL)
        
        self.client = oandapyV20.API(access_token=api_key, environment=environment)
        self.account_id = account_id
        self.profile = profile_settings
        self.read_only = read_only
        self._liquid_capital = 0.0
        self.refresh_account_summary()

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts EURUSD to EUR_USD."""
        sym = symbol.upper().replace("/", "").replace("-", "")
        if len(sym) == 6:
            return f"{sym[:3]}_{sym[3:]}"
        return sym

    def refresh_account_summary(self) -> None:
        """Fetches latest balance and NAV."""
        try:
            r = accounts.AccountSummary(self.account_id)
            self.client.request(r)
            summary = r.response.get("account", {})
            self._liquid_capital = float(summary.get("NAV", 0.0))
            logger.info(f"[OANDA] Account Summary: Balance={summary.get('balance')}, NAV={self._liquid_capital}")
        except Exception as e:
            logger.error(f"[OANDA] Failed to refresh account summary: {e}")

    def get_liquid_capital(self) -> float:
        return self._liquid_capital

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        """OANDA doesn't have 'resting' orders in the same way for market trades, but we cancel pending limit orders."""
        if self.read_only:
            logger.warning(f"[OANDA] Read-only mode: skipping cancel_all_orders for {symbol}")
            return
        
        try:
            # First, find pending orders for this symbol
            r = orders.OrdersPending(self.account_id)
            self.client.request(r)
            for order in r.response.get("orders", []):
                if order.get("instrument") == self._normalize_symbol(symbol):
                    cancel_r = orders.OrderCancel(self.account_id, orderID=order["id"])
                    self.client.request(cancel_r)
                    logger.info(f"[OANDA] Cancelled pending order {order['id']} for {symbol}")
        except Exception as e:
            logger.error(f"[OANDA] Failed to cancel orders for {symbol}: {e}")

    def flatten_symbol(self, symbol: str) -> None:
        """Closes any open positions for the symbol."""
        if self.read_only:
            logger.warning(f"[OANDA] Read-only mode: skipping flatten for {symbol}")
            return

        try:
            oanda_sym = self._normalize_symbol(symbol)
            # OANDA specific: close position requires specifying long/short units
            data = {"longUnits": "ALL"} # Or specify shortUnits
            # First check what's open
            r_pos = oanda_positions.PositionDetails(self.account_id, instrument=oanda_sym)
            self.client.request(r_pos)
            pos = r_pos.response.get("position", {})
            
            close_data = {}
            if float(pos.get("long", {}).get("units", 0)) > 0:
                close_data["longUnits"] = "ALL"
            if float(pos.get("short", {}).get("units", 0)) < 0:
                close_data["shortUnits"] = "ALL"
            
            if close_data:
                r_close = oanda_positions.PositionClose(self.account_id, instrument=oanda_sym, data=close_data)
                self.client.request(r_close)
                logger.info(f"[OANDA] Flattened {symbol}")
        except Exception as e:
            logger.error(f"[OANDA] Failed to flatten {symbol}: {e}")

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        try:
            oanda_sym = self._normalize_symbol(symbol)
            r = oanda_positions.PositionDetails(self.account_id, instrument=oanda_sym)
            self.client.request(r)
            pos = r.response.get("position", {})
            
            long_units = float(pos.get("long", {}).get("units", 0))
            short_units = float(pos.get("short", {}).get("units", 0))
            
            units = long_units + short_units
            if abs(units) < 1e-8:
                return None
            
            # Use project-standard keys: size, side, avg_price, unrealized_pnl
            return {
                "symbol": symbol.upper(),
                "size": units,
                "side": "long" if units > 0 else "short",
                "avg_price": float(pos.get("long", {}).get("averagePrice", 0)) if units > 0 else float(pos.get("short", {}).get("averagePrice", 0)),
                "unrealized_pnl": float(pos.get("unrealizedPL", 0))
            }
        except Exception:
            return None

    def list_open_position_symbols(self) -> list[str]:
        """Returns list of canonical symbols with open positions."""
        try:
            r = oanda_positions.OpenPositions(self.account_id)
            self.client.request(r)
            symbols = []
            for pos in r.response.get("positions", []):
                oanda_sym = pos.get("instrument")
                # De-normalize: EUR_USD -> EURUSD
                clean_sym = oanda_sym.replace("_", "").upper()
                symbols.append(clean_sym)
            logger.debug(f"[OANDA] Discovered open symbols: {symbols}")
            return symbols
        except Exception as e:
            logger.error(f"[OANDA] Failed to list open positions: {e}")
            return []

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        if self.read_only:
            logger.warning(f"[OANDA] Read-only mode: skipping execution for {decision.symbol}")
            return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "read-only mode"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "read-only")

        action = decision.action
        
        if action == "close_position":
            self.flatten_symbol(decision.symbol)
            return ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "flattened"), ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "flatten requested")

        entry_actions = {"long", "short", "enter_long", "enter_short", "scale_in", "add_to_position", "flip_to_long", "flip_to_short"}
        if action not in entry_actions:
             return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no trade action"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no trade action")

        is_short = action in ["short", "enter_short", "flip_to_short"]

        try:
            oanda_sym = self._normalize_symbol(decision.symbol)
            
            # Sizing calculation
            # For OANDA, units are usually base currency (e.g., 1000 for 1000 EUR in EURUSD)
            # risk_per_trade_dollars / (stop_distance)
            price = decision.entry_price
            stop_price = decision.stop_loss
            take_profit = decision.take_profit
            
            if not price or not stop_price:
                 return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "missing price or SL"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "missing price or SL")
                
            stop_dist = abs(price - stop_price)
            if stop_dist < 1e-8:
                 return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "stop distance too small"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "stop distance too small")
                
            risk_amount = self.profile.risk_per_trade_dollars
            if risk_amount <= 0:
                risk_amount = self._liquid_capital * self.profile.risk_per_trade_pct
                
            # units = risk / stop_dist
            units = int(risk_amount / stop_dist)
            if is_short:
                units = -units
            
            if abs(units) < 1:
                logger.warning(f"[OANDA] Calculated units too small: {units} for {decision.symbol}")
                return ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "units too small"), ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "units too small")

            # Prepare Order
            order_data = {
                "order": {
                    "units": str(units),
                    "instrument": oanda_sym,
                    "timeInForce": "IOC",
                    "type": "MARKET",
                    "positionFill": "DEFAULT"
                }
            }
            
            # Attach SL/TP if provided
            if stop_price:
                order_data["order"]["stopLossOnFill"] = {"price": f"{stop_price:.5f}"}
            if take_profit:
                order_data["order"]["takeProfitOnFill"] = {"price": f"{take_profit:.5f}"}

            logger.info(f"[OANDA] Placing {decision.action} order for {decision.symbol}: {units} units")
            r = orders.OrderCreate(self.account_id, data=order_data)
            self.client.request(r)
            
            res = r.response
            if "orderFillTransaction" in res:
                fill = res["orderFillTransaction"]
                logger.info(f"[OANDA] Order filled: {fill['id']} at {fill['price']}")
                return ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, f"filled {fill['id']}"), ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, order_ids=[fill['id']])
            else:
                logger.warning(f"[OANDA] Order not filled immediately: {res}")
                return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "not filled immediately"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "not filled immediately")

        except Exception as e:
            logger.error(f"[OANDA] Execution failed for {decision.symbol}: {e}")
            return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, str(e)), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, str(e))

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        # Simple implementation: block if we already have a position and it's not a scale-in
        if open_position and decision.action in ["long", "short"]:
            return True, "Already in position", None
        return False, None, None

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        """OANDA handles stops on-server, so we don't need synthetic stops unless we want to."""
        return []

    def summarize_pnl(self) -> None:
        pass

    def _fetch_symbol_state(self, symbol: str) -> dict:
        pos = self.get_open_position_snapshot(symbol)
        return {"position": pos} if pos else {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        pos = self.get_open_position_snapshot(symbol)
        return pos is not None
