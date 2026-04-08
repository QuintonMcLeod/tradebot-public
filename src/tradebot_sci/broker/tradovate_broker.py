from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from tradebot_sci.broker.interfaces import IExchangeBroker
from tradebot_sci.config.models import TradingProfileSettings
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.broker.tradovate_client import TradovateClient

logger = logging.getLogger(__name__)

class TradovateBroker(IExchangeBroker):
    """Broker implementation for Apex Trader Funding / Tradovate REST API."""

    def __init__(
        self,
        username: str,
        password: str,
        app_id: str,
        profile_settings: TradingProfileSettings,
        environment: str = "practice",
        read_only: bool = True,
    ):
        self.profile = profile_settings
        self.read_only = read_only
        self.environment = environment
        self._authorized = False

        if not username or not password or not app_id:
            logger.error("[TRADOVATE] Missing credentials. Tradovate connection bypassed.")
            return

        is_live = (environment == "live")
        
        logger.info(f"[TRADOVATE] Connecting to Tradovate as {username} (Live: {is_live})")
        self.client = TradovateClient(username, password, app_id, is_live=is_live)
        
        self.tradovate_account_id = None
        self._liquid_capital = 0.0

        if self.client.is_authenticated():
            self._authorized = True
            self._discover_account()
            self.refresh_account_summary()
        else:
            logger.error("[TRADOVATE] Failed to authenticate. Broker is unauthorized.")

    def _discover_account(self):
        """Fetch account ID from Tradovate."""
        status, data = self.client.get("account/list")
        if status == 200 and isinstance(data, list) and len(data) > 0:
            # For Apex, there's usually just one active Combine account
            self.tradovate_account_id = data[0].get("id")
            account_name = data[0].get("name")
            logger.info(f"[TRADOVATE] Bound to Account ID: {self.tradovate_account_id} ({account_name})")
        else:
            logger.error("[TRADOVATE] Failed to fetch account ID from /account/list")
            self._authorized = False

    def sync_profile(self, profile: TradingProfileSettings) -> None:
        self.profile = profile

    def _normalize_symbol(self, symbol: str) -> str:
        """Just passthrough for Futures. If AI decides ES, it should send ES."""
        # TODO: Advanced contract rolling mapping (e.g., 'ES' -> 'ESM4')
        return symbol.upper()

    def refresh_account_summary(self) -> None:
        if not self._authorized or not self.tradovate_account_id:
            return
            
        status, data = self.client.get(f"account/item", params={"id": self.tradovate_account_id})
        # If the account list doesn't give balances, we might need to check 'margin/item' or 'cashBalance/item' in Tradovate.
        # Actually Tradovate uses cashBalance/list or margin/list.
        status_margin, data_margin = self.client.get("margin/list")
        if status_margin == 200 and isinstance(data_margin, list):
            for margin in data_margin:
                if margin.get("accountId") == self.tradovate_account_id:
                    self._liquid_capital = float(margin.get("availableMargin", 0.0))
                    return

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return self._liquid_capital

    def get_total_equity(self) -> float:
        return self._liquid_capital # Simplify for now until cashBalance parsing is added

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        if not self._authorized or self.read_only:
            return
            
        status, data = self.client.get("order/list")
        if status == 200 and isinstance(data, list):
            target_symbol = self._normalize_symbol(symbol)
            for order in data:
                if order.get("ordStatus") in ["Working", "PendingNew"]:
                    contract_id = order.get("contractId") # Needs mapping typically
                    # Simplified for initial pass
                    cancel_payload = {"orderId": order.get("id")}
                    self.client.post("order/cancelorder", payload=cancel_payload)
                    logger.info(f"[TRADOVATE] Cancelled working order {order.get('id')}")

    def flatten_symbol(self, symbol: str, exit_reason: str = "manual_flatten") -> None:
        if not self._authorized or self.read_only:
            return

        target_symbol = self._normalize_symbol(symbol)
        
        # Check positions
        status, data = self.client.get("position/list")
        if status == 200 and isinstance(data, list):
            for pos in data:
                if pos.get("accountId") == self.tradovate_account_id:
                    # In Tradovate, you must use liquidatePosition
                    # The endpoint is liquidatposition, passing accountId and contractId or just liquidate all
                    # Simplified to just flatten the whole account for safety first.
                    logger.info(f"[TRADOVATE] Liquidating position for {symbol}")
                    pos_id = pos.get("id")
                    
                    payload = {
                        "positionId": pos_id,
                        "customTag50": "Flatten"
                    }
                    self.client.post("order/liquidateposition", payload=payload)

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        if not self._authorized:
            return None
            
        status, data = self.client.get("position/list")
        if status == 200 and isinstance(data, list):
            for pos in data:
                if pos.get("accountId") == self.tradovate_account_id:
                    # Very simple mapper
                    units = float(pos.get("netPos", 0))
                    if units != 0:
                        return {
                            "symbol": symbol.upper(),
                            "size": units,
                            "side": "long" if units > 0 else "short",
                            "avg_price": float(pos.get("prevPos", 0)), # Placeholder mapped, Tradovate is complex
                            "unrealized_pnl": 0.0 # Requires margin/item
                        }
        return None

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        if not self._authorized:
            return (
                ExecutionResult(status=ExecutionStatus.ERROR, symbol=decision.symbol, reason="Tradovate Not Authorized"),
                ExecutionOutcome(status=ExecutionOutcomeType.ERROR, symbol=decision.symbol)
            )

        if self.read_only:
            logger.info(f"[TRADOVATE] Read-only execution blocked: {decision.action} {decision.symbol}")
            return (
                ExecutionResult(status=ExecutionStatus.RISK_SUPPRESSED, symbol=decision.symbol, reason="Read-only"),
                ExecutionOutcome(status=ExecutionOutcomeType.SKIPPED, symbol=decision.symbol)
            )

        # 1. Fetch Contract ID for the symbol
        # Tradovate requires contract ID mapping from symbol string
        contract_status, contract_data = self.client.get("contract/find", params={"name": self._normalize_symbol(decision.symbol)})
        if contract_status != 200 or not contract_data:
            return (
                ExecutionResult(status=ExecutionStatus.ERROR, symbol=decision.symbol, reason=f"Could not map {decision.symbol} to Tradovate Contract ID"),
                ExecutionOutcome(status=ExecutionOutcomeType.ERROR, symbol=decision.symbol)
            )
            
        contract_id = contract_data.get("id")

        # 2. Place Order payload
        action = "Buy" if decision.action.lower() == "buy" else "Sell"
        payload = {
            "accountId": self.tradovate_account_id,
            "contractId": contract_id,
            "action": action,
            "orderQty": 1, # Minimal size mapping
            "orderType": "Market",
            "isAutomated": True
        }

        logger.info(f"[TRADOVATE] Routing order: {payload}")
        order_status, order_resp = self.client.post("order/placeorder", payload=payload)
        
        if order_status == 200:
            order_id = order_resp.get("orderId")
            return (
                ExecutionResult(status=ExecutionStatus.FILLED, symbol=decision.symbol, transaction_id=str(order_id)),
                ExecutionOutcome(status=ExecutionOutcomeType.ENTERED, symbol=decision.symbol)
            )
        else:
            logger.error(f"[TRADOVATE] Order placement failed: {order_status} {order_resp}")
            return (
                ExecutionResult(status=ExecutionStatus.ERROR, symbol=decision.symbol, reason="Order request rejected"),
                ExecutionOutcome(status=ExecutionOutcomeType.ERROR, symbol=decision.symbol)
            )

    # Note: Synthetic stops routing is inherited via generic loop logic,
    # but the broker requires evaluate_synthetic_stops to not crash.
    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> list[ExecutionResult]:
        return []
    
    def summarize_pnl(self) -> None:
        pass
    
    def should_block_for_hold(self, symbol: str, decision: AITradeDecision, open_position: dict | None) -> tuple[bool, str | None, float | None]:
        return False, None, None
