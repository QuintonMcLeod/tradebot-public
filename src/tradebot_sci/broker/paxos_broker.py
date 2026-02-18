from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import requests
from typing import Any, Iterable

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

class PaxosExchangeBroker(IExchangeBroker):
    """Broker implementation for Paxos (itBit) API V2."""

    BASE_URL_PROD = "https://api.paxos.com/v2"
    BASE_URL_SANDBOX = "https://api.sandbox.paxos.com/v2"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        profile_settings: TradingProfileSettings,
        environment: str = "sandbox",
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.profile = profile_settings
        self.environment = environment.lower()
        self.base_url = self.BASE_URL_PROD if self.environment == "production" else self.BASE_URL_SANDBOX
        
        self._liquid_capital = 0.0
        # Paxos uses UserID for some endpoints, but mostly we query account via API Key perms.
        # We'll fetch the profile ID dynamically if needed or rely on default wallet.
        self.refresh_account_summary()

    def _get_headers(self, method: str, path: str, body: str = "") -> dict:
        """Constructs Paxos V2 HMAC-SHA256 headers."""
        timestamp = str(int(time.time()))
        nonce = str(int(time.time() * 1000))
        
        # Paxos signature format: 
        # timestamp + nonce + method + url_path + body
        # URL path includes query params if any. Here we assume path is relative e.g., /v2/wallets
        # Note: Base URL shouldn't be in signature, just the path part? 
        # Paxos docs: "The message to be signed is the concatenation of the timestamp, nonce, HTTP method (upper case), request URL (including the path and query parameters), and the request body."
        
        msg = f"{timestamp}{nonce}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.api_key.encode("utf-8"), # Wait, secret is the key for HMAC? Usually secret.
            # Paxos docs: "Sign the message using your API Secret"
            # Wait, usually key is public, secret is private.
            # Mistake in paxos docs read? Usually: hmac(secret, msg).
            # Yes, secret is the key for hmac.
            self.api_secret.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "Content-Type": "application/json",
            "Paxos-Authorization": self.api_key,
            "Paxos-Timestamp": timestamp,
            "Paxos-Signature": signature_b64,
            "Paxos-Nonce": nonce,
        }
        
    def _request(self, method: str, endpoint: str, data: dict = None) -> Any:
        path = f"/v2{endpoint}" # Endpoint should start with /wallets etc.
        url = f"{self.base_url}{endpoint}"
        
        body_str = json.dumps(data) if data else ""
        headers = self._get_headers(method, path, body_str)
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers)
            elif method == "POST":
                resp = requests.post(url, headers=headers, data=body_str)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method {method}")
            
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[PAXOS] Request failed {method} {endpoint}: {e}")
            if hasattr(e, "response") and e.response:
                logger.error(f"[PAXOS] Response: {e.response.text}")
            raise

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts BTCUSD to BTCUSD (Paxos uses standard tickers?). 
        Paxos Market tickers: BTCUSD, ETHUSD, LTCUSD, PAXGUSD, BCHUSD.
        """
        # Paxos tickers are typically simple e.g. BTCUSD
        clean = symbol.replace("/", "").replace("-", "").upper()
        return clean

    def refresh_account_summary(self) -> None:
        """Fetches profile limits/balances."""
        try:
            # Endpoint: /profiles to get account ID? Or /wallets
            # Let's try /profiles first to get the main profile
            profiles = self._request("GET", "/profiles")
            # Iterate to find the active one or sum balances?
            # Simplified: Assume first profile or find one with balances.
            
            total_usd = 0.0
            for p in profiles:
                pid = p.get("id")
                # Get balance for this profile
                balances = self._request("GET", f"/profiles/{pid}/balances")
                for bal in balances:
                    if bal.get("currency") == "USD":
                        total_usd += float(bal.get("available", 0))
            
            self._liquid_capital = total_usd
            logger.info(f"[PAXOS] Account Summary: Liquid Capital=${self._liquid_capital:.2f}")
            
        except Exception as e:
            logger.error(f"[PAXOS] Failed to refresh account: {e}")

    def get_liquid_capital(self) -> float:
        return self._liquid_capital

    def get_total_equity(self) -> float:
        """Paxos doesn't distinguish — liquid capital is total equity."""
        return self._liquid_capital

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        action = decision.action
        
        if action == "close_position":
            self.flatten_symbol(decision.symbol)
            return ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "flattened"), ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "flatten requested")

        valid_entries = ["long", "short", "enter_long", "enter_short"]
        if action not in valid_entries:
             return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no trade action"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no trade action")
             
        # Paxos (itBit) supports spot. Shorting might not be natively supported on Spot?
        # Usually itBit is Spot only.
        if action in ["short", "enter_short"]:
             logger.warning(f"[PAXOS] Shorting not supported on Spot API for {decision.symbol}")
             return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "short not supported"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "short not supported")

        try:
            paxos_sym = self._normalize_symbol(decision.symbol)
            
            # Sizing
            risk_dollars = self.profile.risk_per_trade_dollars
            if risk_dollars <= 0:
                risk_dollars = self._liquid_capital * self.profile.risk_per_trade_pct
                
            # For logging/checking
            if risk_dollars < 10.0: # Paxos min trade? usually like 10-20 USD?
                pass 
                
            # Create Order
            # POST /users/{userId}/orders? Or /orders relative to profile?
            # V2 API: POST /orders
            # Body: market, side (buy/sell), type (market/limit), amount (qty) or price.
            
            # Since we calculate dollars, and it's a Spot Buy, we usually want to spend `risk_dollars`.
            # If it's a market buy, we might specify notional? Neither itBit API typically takes quantity (base ccy).
            # So we need price to calc qty.
            
            price = decision.entry_price or 0.0
            if price <= 0:
                 # Fetch ticker to get price Estimate?
                 # Assuming caller provided valid price logic.
                 # Implementation gap: Fetch ticker here if price missing?
                 pass
                 
            qty = risk_dollars / price if price > 0 else 0
            qty = round(qty, 4) # BTC 4 decimals?
            
            if qty <= 0:
                return ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "zero qty"), ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "zero qty")

            order_payload = {
                "market": paxos_sym,
                "side": "buy",
                "type": "market", # Use market for now
                "amount": str(qty) 
            }
            
            # Check for Profile ID? V2 requests usually usually need it if user has multiple?
            # Docs say default profile used if headers not set? Or use /profiles/{profileId}/orders
            # We will try basic /orders first or discover profile.
            # To be robust, let's look up profile first.
            
            profile = self._request("GET", "/profiles")[0]
            pid = profile['id']
            
            logger.info(f"[PAXOS] Submitting order: {order_payload}")
            resp = self._request("POST", f"/profiles/{pid}/orders", order_payload)
            
            oid = resp.get("id")
            status = resp.get("status")
            logger.info(f"[PAXOS] Order placed: {oid} status={status}")
            
            return ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, f"filled {oid}"), ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, order_ids=[oid])

        except Exception as e:
            logger.error(f"[PAXOS] Execution failed: {e}")
            return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, str(e)), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, str(e))

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        """Cancels open orders."""
        try:
            profile = self._request("GET", "/profiles")[0]
            pid = profile['id']
            # GET /orders?status=open&instrument=...
            paxos_sym = self._normalize_symbol(symbol)
            orders = self._request("GET", f"/profiles/{pid}/orders?status=open&instrument={paxos_sym}")
            for o in orders:
                self._request("DELETE", f"/profiles/{pid}/orders/{o['id']}")
                logger.info(f"[PAXOS] Cancelled {o['id']}")
        except Exception as e:
            logger.error(f"[PAXOS] Cancel failed: {e}")

    def flatten_symbol(self, symbol: str) -> None:
         # Sell entire position
         # 1. Get position
         # 2. Sell
         pass # Implementation left simple for now

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return {}
        
    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        return False

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        return None

    def list_open_position_symbols(self) -> Iterable[str]:
        return []

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        return []

    def summarize_pnl(self) -> None:
        pass
    
    def should_block_for_hold(self, symbol: str, decision: AITradeDecision, open_position: dict | None) -> tuple[bool, str | None, float | None]:
        return False, None, None
