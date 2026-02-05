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
from tradebot_sci.broker.trade_result_store import TradeResultStore, TradeResult

logger = logging.getLogger(__name__)

class OandaExchangeBroker(IExchangeBroker):
    """Broker implementation for OANDA v20 API."""

    def __init__(
        self,
        account_id: str,
        api_key: str,
        profile_settings: TradingProfileSettings,
        environment: str = "practice",
        read_only: bool = True,
        trade_results: TradeResultStore | None = None
    ):
        if not HAS_OANDA:
            raise ImportError("OANDA dependencies missing. Please install oandapyV20.")
        
        # Suppress noisy library logging (especially the 404 spam)
        logging.getLogger("oandapyV20.oandapyV20").setLevel(logging.CRITICAL)
        
        self.client = oandapyV20.API(access_token=api_key, environment=environment)
        self.account_id = account_id
        self.profile = profile_settings
        self.read_only = read_only
        self.trade_results = trade_results
        self._liquid_capital = 0.0
        self.refresh_account_summary()

    def sync_profile(self, profile: TradingProfileSettings) -> None:
        """Update internal profile pointer to latest settings (Hot-Reload)."""
        logger.info(f"[OANDA] Syncing new Profile settings... (Risk: ${getattr(profile, 'risk_per_trade_dollars', 'N/A')})")
        self.profile = profile

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts EURUSD to EUR_USD, handles Crypto mappings."""
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        # Standard OANDA pairs: XXX_YYY
        if len(sym) == 6:
            return f"{sym[:3]}_{sym[3:]}"
        
        # Crypto handling (BTCUSD -> BTC_USD, BTCUSDT -> BTC_USDT etc)
        if sym.endswith("USD") and len(sym) > 3:
            return f"{sym[:-3]}_{sym[-3:]}"
        if sym.endswith("USDT") and len(sym) > 4:
            return f"{sym[:-4]}_{sym[-4:]}"
            
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

    def get_liquid_capital(self, symbol: str | None = None) -> float:
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
                
                # [ANTIGRAVITY FIX] Calculate PnL and Log for GUI
                pnl_val = float(pos.get("unrealizedPL", 0.0)) # Since we are closing at current market price
                # For Oanda, we can try to find the actual realized PnL in the response
                resp = r_close.response
                if "longOrderFillTransaction" in resp:
                    pnl_val = float(resp["longOrderFillTransaction"].get("pl", 0.0))
                elif "shortOrderFillTransaction" in resp:
                    pnl_val = float(resp["shortOrderFillTransaction"].get("pl", 0.0))
                
                # Calculate Pct
                units = abs(float(pos.get("long", {}).get("units", 0)) + float(pos.get("short", {}).get("units", 0)))
                avg_price = float(pos.get("long", {}).get("averagePrice", 0)) if units > 0 else float(pos.get("short", {}).get("averagePrice", 0))
                pnl_pct = 0.0
                if units > 0 and avg_price > 0:
                    pnl_pct = (pnl_val / (avg_price * units)) * 100

                pnl_str = f"{'+' if pnl_val >= 0 else ''}${pnl_val:.2f}"
                logger.info(f"[EXIT] Manual/Signal: {symbol} {pnl_str} (Pct={pnl_pct:.2f}%)")
                
                # Add to TradeResultStore
                if self.trade_results:
                    from datetime import datetime, timezone
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=datetime.now(timezone.utc).isoformat(),
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_val,
                        is_win=pnl_val > 0,
                        tier="100%",
                        capital_at_close=self._liquid_capital
                    ))

                logger.info(f"[OANDA] Flattened {symbol}. Response: {resp}")
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
            # [ANTIGRAVITY FIX] Add aliases 'entry_price' and 'direction' for strategy compatibility
            side = "long" if units > 0 else "short"
            avg_price = float(pos.get("long", {}).get("averagePrice", 0)) if units > 0 else float(pos.get("short", {}).get("averagePrice", 0))
            
            # [ANTIGRAVITY FIX] Fetch SL/TP and Entry Time from trade details
            stop_loss = None
            take_profit = None
            entry_time = None
            try:
                trade_ids = pos.get("long" if side == "long" else "short", {}).get("tradeIDs", [])
                if trade_ids:
                    # Get details of the first (primary) trade
                    r_trade = trades.TradeDetails(self.account_id, tradeID=trade_ids[0])
                    self.client.request(r_trade)
                    trade = r_trade.response.get("trade", {})
                    if "stopLossOrder" in trade:
                        stop_loss = float(trade["stopLossOrder"].get("price", 0))
                    if "takeProfitOrder" in trade:
                        take_profit = float(trade["takeProfitOrder"].get("price", 0))
                    if "openTime" in trade:
                        entry_time = trade["openTime"] # ISO format OANDA string
            except Exception as e:
                logger.debug(f"[OANDA] Could not fetch SL/TP or Entry Time for {symbol}: {e}")
            
            result = {
                "symbol": symbol.upper(),
                "size": units,
                "side": side,
                "direction": side, # Alias
                "avg_price": avg_price,
                "entry_price": avg_price, # Alias
                "entry_time": entry_time, # [ANTIGRAVITY] Added entry time
                "unrealized_pnl": float(pos.get("unrealizedPL", 0))
            }
            
            if stop_loss and stop_loss > 0:
                result["stop_loss"] = stop_loss
            if take_profit and take_profit > 0:
                result["take_profit"] = take_profit
            
            return result
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
            units = risk_amount / stop_dist
            
            # [ANTIGRAVITY] Leverage-based sizing Cap
            # Prevent units from exceeding account_equity * target_leverage
            target_leverage = getattr(self.profile, "target_leverage", 1.0)
            if target_leverage > 0:
                max_notional = self._liquid_capital * target_leverage
                max_units = max_notional / price if price > 0 else 0
                if abs(units) > max_units and max_units > 0:
                    logger.warning(f"[OANDA] Sizing Cap: Calculated units {abs(units):.2f} exceeds leverage cap {max_units:.2f} (Leverage={target_leverage}x)")
                    units = max_units if units > 0 else -max_units

            if is_short:
                units = -units
            
            # Crypto might require more than 0 decimals, Forex usually whole units?
            # Actually OANDA supports fractional units regardless of class if using v20?
            # Let's keep 4 decimals for crypto, whole for forex to be safe.
            is_crypto = any(c in decision.symbol.upper() for c in ["BTC", "ETH", "SOL", "ADA", "LTC"])
            if is_crypto:
                units = round(units, 4)
            else:
                units = int(units)
            
            # Allow fractional units for crypto
            min_size = 0.0001 if is_crypto else 1
            if abs(units) < min_size:
                logger.warning(f"[OANDA] Calculated units too small: {units} for {decision.symbol} (min={min_size})")
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
            fmt = ".5f" if not is_crypto else ".2f"
            if "JPY" in decision.symbol: fmt = ".3f" # JPY pairs use 3 decimals
            
            if stop_price:
                order_data["order"]["stopLossOnFill"] = {"price": f"{stop_price:{fmt}}"}
            if take_profit:
                order_data["order"]["takeProfitOnFill"] = {"price": f"{take_profit:{fmt}}"}

            # Refresh account summary to get latest margin info
            self.refresh_account_summary()
            
            # Additional Margin Logging
            try:
                r_summary = accounts.AccountSummary(self.account_id)
                self.client.request(r_summary)
                summ = r_summary.response.get("account", {})
                margin_used = summ.get("marginUsed", "0")
                margin_avail = summ.get("marginAvailable", "0")
                margin_rate = summ.get("marginRate", "0")
                logger.info(f"[OANDA] Pre-order Margin Check: Used=${margin_used}, Available=${margin_avail}, Leverage={1/float(margin_rate) if float(margin_rate) > 0 else 'N/A'}:1")
            except Exception as e:
                logger.warning(f"[OANDA] Could not fetch detailed margin info: {e}")

            logger.info(f"[OANDA] Placing {decision.action} order for {decision.symbol}: {units} units")
            # [ANTIGRAVITY FIX] Log specific tags for GUI parsing (Arrows & Tables)
            logger.info(f"[ENTRY] {decision.symbol} side={'buy' if units > 0 else 'sell'} amount={abs(units)}")
            r = orders.OrderCreate(self.account_id, data=order_data)
            self.client.request(r)

            
            res = r.response
            if "orderFillTransaction" in res:
                fill = res["orderFillTransaction"]
                avg_fill = float(fill.get("price") or 0.0)
                if avg_fill > 0:
                    logger.info(f"[FILL] {decision.symbol} @ {avg_fill} (ID: {fill['id']})")
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
