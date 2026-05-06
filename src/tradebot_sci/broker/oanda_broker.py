from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tradebot_sci import paths as _paths
from typing import Any, Iterable

try:
    import oandapyV20
    import oandapyV20.endpoints.accounts as accounts
    import oandapyV20.endpoints.orders as orders
    import oandapyV20.endpoints.positions as oanda_positions
    import oandapyV20.endpoints.trades as trades
    import oandapyV20.endpoints.pricing as pricing
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

    # Spread cost awareness — OANDA uses spread-only pricing (no commissions).
    # Fallback average spread in pips; used when live pricing API is unavailable.
    AVG_SPREAD_PIPS = float(os.getenv("OANDA_AVG_SPREAD_PIPS", "1.5"))
    # How long a cached live spread reading remains valid (seconds)
    _SPREAD_TTL = 30.0
    # Pip value multiplier: 0.0001 for most pairs, 0.01 for JPY pairs
    PIP_VALUE_STANDARD = 0.0001
    PIP_VALUE_JPY = 0.01

    def __init__(
        self,
        account_id: str,
        api_key: str,
        profile_settings: TradingProfileSettings,
        environment: str = "practice",
        read_only: bool = True,
        trade_results: TradeResultStore | None = None,
        position_hold_store_path: str | None = None
    ):
        if not HAS_OANDA:
            raise ImportError("OANDA dependencies missing. Please install oandapyV20.")
        
        # Suppress noisy library logging (especially the 404 spam)
        logging.getLogger("oandapyV20.oandapyV20").setLevel(logging.CRITICAL)
        
        self.client = oandapyV20.API(access_token=api_key, environment=environment, request_params={"timeout": 10})
        self.account_id = account_id
        _masked_key = ('***' + api_key[-6:]) if len(api_key) > 6 else '***'
        logger.info(
            f"[OANDA] Broker init: account={account_id}, "
            f"env={environment}, key={_masked_key}, read_only={read_only}"
        )
        self.profile = profile_settings
        self.read_only = read_only
        self.trade_results = trade_results
        # Shared position_hold_store for strategy tracking & re-entry cooldown
        self.position_hold_store = None
        if position_hold_store_path:
            from tradebot_sci.broker.position_hold_store import PositionHoldStore
            self.position_hold_store = PositionHoldStore(position_hold_store_path)
        self._liquid_capital = 0.0
        self._authorized = True  # Will be set to False if API key is invalid
        self._tracked_positions: dict[str, dict] = {}  # symbol -> position snapshot
        self._prev_balance: float | None = None  # for PnL calc on vanished positions
        self._exit_cooldowns: dict[str, float] = {}  # symbol -> timestamp of last exit
        self.REENTRY_COOLDOWN = float(os.getenv("OANDA_REENTRY_COOLDOWN", "300"))  # 5 min default
        self._spread_cache: dict[str, tuple[float, float]] = {}  # symbol -> (spread_pips, timestamp)
        # Sunday early session block: spreads are 5-15 pips during first N hours after Sunday open (5 PM ET)
        self.SUNDAY_BLOCK_HOURS = int(os.getenv("OANDA_SUNDAY_BLOCK_HOURS", "3"))
        # Whether to use LIMIT FOK orders instead of MARKET IOC (reduces slippage)
        self.USE_LIMIT_ORDERS = os.getenv("OANDA_USE_LIMIT_ORDERS", "true").lower() in ("true", "1", "yes")
        self.LIMIT_ORDER_BUFFER_PIPS = float(os.getenv("OANDA_LIMIT_BUFFER_PIPS", "0.5"))
        self._tracked_path = _paths.DATA_DIR / "oanda_tracked_positions.json"
        self._load_tracked_positions()

        # ── Account validation & auto-discovery ──
        # OANDA API keys can access multiple sub-accounts (Primary, MT4, etc).
        # If the provided account_id fails or returns $0, discover all accounts
        # and pick the one with the highest balance.
        try:
            self._discover_and_validate_account(environment)
        except Exception as e:
            logger.error(f"[OANDA] ⚠ Account connection failed or credentials invalid: {e}")
            self._authorized = False

        if not self._authorized or self._liquid_capital == 0:
            logger.warning("[OANDA] ⚠ Could not validate or discover a funded OANDA account id. Broker will be marked unauthorized.")
            self._authorized = False

        if self._authorized:
            self._bootstrap_tracked_positions()

    def _discover_and_validate_account(self, environment: str) -> None:
        """Validate the configured account and auto-discover if needed."""
        # Try the configured account first
        if self.account_id:
            self.refresh_account_summary()
            if self._liquid_capital > 0:
                return  # Account works and has funds

            # Account returned $0 — could be wrong sub-account
            logger.warning(
                f"[OANDA] Account {self.account_id} returned $0 NAV. "
                f"Scanning all accounts under this API key..."
            )

        # ── Discover all accounts under this API key ──
        try:
            r = accounts.AccountList()
            self.client.request(r)
            acct_list = r.response.get("accounts", [])

            if not acct_list:
                logger.error("[OANDA] No accounts found for this API key!")
                return

            logger.info(f"[OANDA] Found {len(acct_list)} account(s) under this API key:")

            best_id = None
            best_nav = 0.0

            for acct in acct_list:
                acct_id = acct.get("id", "")
                tags = acct.get("tags", [])
                tag_str = ", ".join(tags) if tags else "no tags"

                # Fetch summary for each account to find the funded one
                try:
                    r_summary = accounts.AccountSummary(acct_id)
                    self.client.request(r_summary)
                    summary = r_summary.response.get("account", {})
                    nav = float(summary.get("NAV", 0.0))
                    balance = float(summary.get("balance", 0.0))
                    currency = summary.get("currency", "USD")
                    effective_value = nav if nav > 0 else balance

                    logger.info(
                        f"  → {acct_id} [{tag_str}] "
                        f"Balance={balance:.2f} NAV={nav:.2f} {currency}"
                    )

                    if effective_value > best_nav:
                        best_nav = effective_value
                        best_id = acct_id
                except Exception as e:
                    logger.warning(f"  → {acct_id} [{tag_str}] ⚠ Could not fetch summary: {e}")

            # Auto-select the best-funded account
            if best_id and best_id != self.account_id and best_nav > 0:
                logger.info(
                    f"[OANDA] Auto-selected account {best_id} "
                    f"(NAV=${best_nav:.2f}) over configured {self.account_id or '(none)'}"
                )
                self.account_id = best_id
                self.refresh_account_summary()
            elif best_id and best_nav > 0:
                # Same account but maybe balance field instead of NAV
                self.account_id = best_id
                self._liquid_capital = best_nav
                logger.info(f"[OANDA] Using account {best_id} with capital ${best_nav:.2f}")
            else:
                logger.error(
                    "[OANDA] No funded accounts found! All accounts returned $0. "
                    "Check your API key permissions and environment (practice vs live)."
                )
                self._authorized = False

        except Exception as e:
            logger.error(f"[OANDA] Account discovery failed: {e}")
            self._authorized = False
            raise RuntimeError(f"Failed to discover funded accounts: {e}")

    def sync_profile(self, profile: TradingProfileSettings) -> None:
        """Update internal profile pointer to latest settings (Hot-Reload)."""
        logger.info(f"[OANDA] Syncing new Profile settings... (Risk: ${getattr(profile, 'risk_per_trade_dollars', 'N/A')})")
        self.profile = profile

    @staticmethod
    def _compute_duration(entry_time_str: str | None) -> tuple[str, float | None]:
        """Compute human-readable duration AND raw seconds from ISO entry time to now."""
        if not entry_time_str:
            return "N/A", None
        try:
            # OANDA timestamps: "2026-02-14T16:03:52.123456789Z"
            clean = entry_time_str.replace("Z", "+00:00")
            # Truncate nanoseconds to microseconds for fromisoformat
            if "." in clean:
                dot_idx = clean.index(".")
                plus_idx = clean.index("+", dot_idx) if "+" in clean[dot_idx:] else len(clean)
                frac = clean[dot_idx+1:plus_idx]
                frac = frac[:6]  # Keep only microseconds
                clean = clean[:dot_idx+1] + frac + clean[plus_idx:]
            entry_dt = datetime.fromisoformat(clean)
            now = datetime.now(timezone.utc)
            total_secs = (now - entry_dt).total_seconds()
            if total_secs < 0:
                return "N/A", None
            secs_int = int(total_secs)
            mins, secs = divmod(secs_int, 60)
            if mins >= 60:
                hrs, mins = divmod(mins, 60)
                return f"{hrs}h {mins}m {secs}s", total_secs
            return f"{mins}m {secs}s", total_secs
        except Exception:
            return "N/A", None

    @classmethod
    def _format_duration(cls, entry_time_str: str | None) -> str:
        """Compute human-readable duration from ISO entry time to now."""
        dur_str, _ = cls._compute_duration(entry_time_str)
        return dur_str

    # ── Tracked Position Persistence ──────────────────────────────────

    def _load_tracked_positions(self) -> None:
        """Load tracked positions from disk (survives restarts)."""
        if self._tracked_path.exists():
            try:
                with self._tracked_path.open("r") as f:
                    self._tracked_positions = json.load(f)
                logger.info(f"[OANDA] Loaded {len(self._tracked_positions)} tracked position(s) from disk")
            except Exception as e:
                logger.warning(f"[OANDA] Failed to load tracked positions: {e}")

    def _save_tracked_positions(self) -> None:
        """Persist tracked positions to disk."""
        try:
            self._tracked_path.parent.mkdir(parents=True, exist_ok=True)
            with self._tracked_path.open("w") as f:
                json.dump(self._tracked_positions, f, indent=2)
        except Exception as e:
            logger.error(f"[OANDA] Failed to save tracked positions: {e}")

    def _bootstrap_tracked_positions(self) -> None:
        """Seed tracked positions from OANDA's current open positions on startup,
        and backfill [EXIT] lines for positions that closed while bot was offline."""
        try:
            current_symbols = set(self.list_open_position_symbols())

            # ── Add new open positions to tracking ──
            bootstrapped = 0
            for sym in current_symbols:
                if sym not in self._tracked_positions:
                    snap = self.get_open_position_snapshot(sym)
                    if snap and abs(snap.get("size", 0)) > 1e-8:
                        self._tracked_positions[sym] = snap
                        bootstrapped += 1
            if bootstrapped:
                logger.info(f"[OANDA] Bootstrapped {bootstrapped} position(s) for exit tracking: {list(current_symbols)}")

            # ── Backfill exits for positions that vanished while bot was offline ──
            stale = [s for s in self._tracked_positions if s not in current_symbols]
            if stale:
                # Load set of already-backfilled trade IDs to prevent duplicates
                bf_path = _paths.DATA_DIR / "oanda_backfilled_trades.json"
                backfilled_ids: set = set()
                if bf_path.exists():
                    try:
                        backfilled_ids = set(json.loads(bf_path.read_text()))
                    except Exception:
                        pass

                for sym in stale:
                    prev = self._tracked_positions[sym]
                    try:
                        r_closed = trades.TradesList(
                            self.account_id,
                            params={"state": "CLOSED", "instrument": self._normalize_symbol(sym), "count": 10}
                        )
                        closed_resp = self.client.request(r_closed)
                        closed_trades = closed_resp.get("trades", [])

                        for ct in closed_trades:
                            trade_id = ct.get("id", "")
                            if trade_id in backfilled_ids:
                                continue  # Already logged

                            gross_pnl = float(ct.get("realizedPL", 0))
                            financing = float(ct.get("financing", 0))
                            dividend = float(ct.get("dividendAdjustment", 0))
                            pnl = gross_pnl + financing + dividend

                            initial_units = float(ct.get("initialUnits", 0))
                            price = float(ct.get("price", 0))
                            pnl_pct = 0.0
                            if initial_units != 0 and price > 0:
                                pnl_pct = (pnl / (abs(initial_units) * price)) * 100
                            side = "SHORT" if initial_units < 0 else "LONG"

                            pip_value = self.PIP_VALUE_JPY if "JPY" in sym.upper() else self.PIP_VALUE_STANDARD
                            est_spread = abs(initial_units) * self.get_live_spread(sym) * pip_value * 2
                            if "JPY" in sym.upper() and price > 0:
                                est_spread /= price  # Convert JPY spread to USD
                            duration_str = self._format_duration(ct.get("openTime"))

                            pnl_sign = '+' if pnl >= 0 else '-'
                            pnl_str = f"{pnl_sign}${abs(pnl):.2f}"
                            logger.info(
                                f"[EXIT] OANDA SL/TP: {sym} {pnl_str} "
                                f"(Pct={pnl_pct:.2f}%) position={side} | "
                                f"Duration={duration_str} | "
                                f"Est. Spread Cost: ${est_spread:.4f}"
                            )
                            backfilled_ids.add(trade_id)
                            logger.info(f"[OANDA] Backfilled missed exit: {sym} trade#{trade_id} PnL=${pnl:.4f}")

                    except Exception as e:
                        err_msg = str(e).lower()
                        if "authorization" in err_msg or "403" in err_msg or "insufficient" in err_msg:
                            logger.debug(f"[OANDA] Backfill skipped for {sym} (API key lacks trade history permission)")
                        else:
                            logger.warning(f"[OANDA] Backfill query failed for {sym}: {e}")

                    del self._tracked_positions[sym]

                # Save backfilled IDs to prevent duplicates on next restart
                try:
                    bf_path.parent.mkdir(parents=True, exist_ok=True)
                    bf_path.write_text(json.dumps(list(backfilled_ids)))
                except Exception:
                    pass

            # ── Catch-all legacy backfill removed ──
            # (Previously it duplicated normally-closed live trades on restart 
            # because it blindly queried the last 50 closed trades).
            self._save_tracked_positions()
        except Exception as e:
            err_msg = str(e).lower()
            if "authorization" in err_msg or "403" in err_msg or "insufficient" in err_msg:
                logger.debug(f"[OANDA] Bootstrap skipped (API key lacks required permissions — non-critical)")
            else:
                logger.warning(f"[OANDA] Bootstrap tracked positions failed: {e}")

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

    # ── Live Spread Fetcher ──────────────────────────────────────
    def get_live_spread(self, symbol: str) -> float:
        """Return the current spread for *symbol* in pips.

        Uses OANDA's Pricing API (``GET /v3/accounts/{id}/pricing``) to fetch
        the real-time bid/ask spread.  Results are cached for ``_SPREAD_TTL``
        seconds to avoid hammering the API.

        Falls back to ``AVG_SPREAD_PIPS`` if the API call fails.
        """
        now = time.time()
        cached = self._spread_cache.get(symbol)
        if cached:
            spread_pips, ts = cached
            if now - ts < self._SPREAD_TTL:
                return spread_pips

        # Fetch live pricing
        try:
            oanda_sym = self._normalize_symbol(symbol)
            params = {"instruments": oanda_sym}
            r = pricing.PricingInfo(self.account_id, params=params)
            resp = self.client.request(r)
            prices = resp.get("prices", [])
            if prices:
                p = prices[0]
                # Use top-of-book bid/ask (first bucket)
                bids = p.get("bids", [])
                asks = p.get("asks", [])
                if bids and asks:
                    bid = float(bids[0].get("price", 0))
                    ask = float(asks[0].get("price", 0))
                    if bid > 0 and ask > 0:
                        pip_val = self.PIP_VALUE_JPY if "JPY" in symbol.upper() else self.PIP_VALUE_STANDARD
                        spread_pips = (ask - bid) / pip_val
                        self._spread_cache[symbol] = (spread_pips, now)
                        logger.debug(
                            f"[SPREAD] Live: {symbol} bid={bid:.5f} ask={ask:.5f} "
                            f"spread={spread_pips:.2f} pips"
                        )
                        return spread_pips

            # Response was empty or malformed — fall through to fallback
            logger.warning(f"[SPREAD] Empty pricing response for {symbol}, using fallback {self.AVG_SPREAD_PIPS} pips")
        except Exception as e:
            logger.warning(f"[SPREAD] API error for {symbol}: {e}, using fallback {self.AVG_SPREAD_PIPS} pips")

        # Fallback to static default
        return self.AVG_SPREAD_PIPS

    def get_live_spread_as_pct(self, symbol: str) -> float | None:
        """Return the current round-trip spread cost as a decimal fraction.

        This is the callback registered into ``symbol_classifier`` so that
        ``get_fee_for_symbol()`` can use real-time data instead of static
        estimates.  Returns ``None`` if the live lookup fails, signalling
        the classifier to use its static fallback.
        """
        try:
            oanda_sym = self._normalize_symbol(symbol)
            params = {"instruments": oanda_sym}
            r = pricing.PricingInfo(self.account_id, params=params)
            resp = self.client.request(r)
            prices = resp.get("prices", [])
            if prices:
                p = prices[0]
                bids = p.get("bids", [])
                asks = p.get("asks", [])
                if bids and asks:
                    bid = float(bids[0].get("price", 0))
                    ask = float(asks[0].get("price", 0))
                    mid = (bid + ask) / 2
                    if mid > 0:
                        # Round-trip spread cost as fraction of price (x2 for entry+exit)
                        return ((ask - bid) / mid) * 2
        except Exception:
            pass
        return None  # Signal: use static fallback

    def refresh_account_summary(self) -> None:
        """Fetches latest balance and NAV."""
        if not self._authorized:
            return
        try:
            r = accounts.AccountSummary(self.account_id)
            self.client.request(r)
            summary = r.response.get("account", {})
            nav = float(summary.get("NAV", 0.0))
            balance = float(summary.get("balance", 0.0))
            margin_avail = float(summary.get("marginAvailable", 0.0))
            # Prefer NAV > balance > marginAvailable (some practice accounts report differently)
            self._liquid_capital = nav if nav > 0 else (balance if balance > 0 else margin_avail)
            logger.info(f"[OANDA] Account Summary: Balance={balance}, NAV={nav}, Capital=${self._liquid_capital:.2f}")
        except Exception as e:
            err_msg = str(e).lower()
            if "authorization" in err_msg or "403" in err_msg or "invalid value" in err_msg or "insufficient" in err_msg:
                logger.error(f"[OANDA] Account summary authorization failed: {e}")
                self._authorized = False
                raise RuntimeError(f"OANDA API key or Account ID is rejected by server: {e}")
            else:
                logger.error(f"[OANDA] Failed to refresh account summary: {e}")

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return self._liquid_capital

    def get_total_balance_value(self) -> float:
        """Returns total account NAV (used by controller for state broadcasts)."""
        self.refresh_account_summary()
        return self._liquid_capital

    def get_total_equity(self) -> float:
        """Return total account equity (NAV) for safety guards."""
        return self.get_total_balance_value()

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

    def flatten_symbol(self, symbol: str, exit_reason: str = "manual_flatten") -> None:
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
            long_units = float(pos.get("long", {}).get("units", 0))
            short_units = float(pos.get("short", {}).get("units", 0))
            if long_units > 0:
                close_data["longUnits"] = "ALL"
            if short_units < 0:
                close_data["shortUnits"] = "ALL"
            side = "SHORT" if short_units < 0 else "LONG"
            
            if close_data:
                r_close = oanda_positions.PositionClose(self.account_id, instrument=oanda_sym, data=close_data)
                self.client.request(r_close)
                resp = r_close.response

                # Check if OANDA cancelled the close (e.g., MARKET_HALTED on weekends)
                if "longOrderCancelTransaction" in resp or "shortOrderCancelTransaction" in resp:
                    cancel_reason = (
                        resp.get("longOrderCancelTransaction", {}).get("reason")
                        or resp.get("shortOrderCancelTransaction", {}).get("reason")
                        or "unknown"
                    )
                    logger.warning(f"[OANDA] Close order for {symbol} was CANCELLED by OANDA (reason: {cancel_reason}). Position remains open.")
                    return
                
                # Calculate PnL and Log for GUI
                pnl_val = float(pos.get("unrealizedPL", 0.0)) # Since we are closing at current market price
                # For Oanda, we can try to find the actual realized PnL in the response
                fill_event = resp.get("longOrderFillTransaction") or resp.get("shortOrderFillTransaction")
                if fill_event:
                    gross_pl = float(fill_event.get("pl", 0.0))
                    financing = float(fill_event.get("financing", 0.0))
                    dividend = float(fill_event.get("dividendAdjustment", 0.0))
                    pnl_val = gross_pl + financing + dividend
                
                # Calculate Pct
                units = abs(float(pos.get("long", {}).get("units", 0)) + float(pos.get("short", {}).get("units", 0)))
                avg_price = float(pos.get("long", {}).get("averagePrice", 0)) if units > 0 else float(pos.get("short", {}).get("averagePrice", 0))
                pnl_pct = 0.0
                if units > 0 and avg_price > 0:
                    pnl_pct = (pnl_val / (avg_price * units)) * 100

                # Estimate round-trip spread cost for transparency
                pip_value = self.PIP_VALUE_JPY if "JPY" in symbol.upper() else self.PIP_VALUE_STANDARD
                est_spread_cost = units * self.get_live_spread(symbol) * pip_value * 2  # x2 for entry + exit
                if "JPY" in symbol.upper() and avg_price > 0:
                    est_spread_cost /= avg_price  # Convert JPY spread to USD

                # Compute duration from tracked position entry time
                prev_pos = self._tracked_positions.get(symbol, {})
                entry_time_str = prev_pos.get("entry_time")
                duration_str, duration_secs = self._compute_duration(entry_time_str)

                pnl_sign = '+' if pnl_val >= 0 else '-'
                pnl_str = f"{pnl_sign}${abs(pnl_val):.2f}"
                logger.info(f"[EXIT] Manual/Signal: {symbol} {pnl_str} (Pct={pnl_pct:.2f}%) position={side} | Duration={duration_str} | Live Spread Cost: ${est_spread_cost:.4f} ({self.get_live_spread(symbol):.1f} pips)")
                # Record exit for re-entry cooldown (losses only — wins can re-enter immediately)
                if pnl_val <= 0:
                    self._exit_cooldowns[symbol] = time.time()
                # Register with SafetyGuard for Streak Breaker & Exit Cooldown
                try:
                    from tradebot_sci.strategy.safety_guard import SafetyGuard
                    is_win = pnl_val > 0
                    SafetyGuard.register_trade_completion(symbol, is_win)
                    logger.info(f"[STREAK] Registered {'WIN' if is_win else 'LOSS'} for {symbol} (streak count: {SafetyGuard._state.symbol_loss_streaks.get(symbol, 0)})")
                except Exception as e:
                    logger.error(f"[STREAK] Failed to register trade completion for {symbol}: {e}")
                
                # Read strategy from hold store before removing
                _exit_strategy = None
                if self.position_hold_store:
                    _hold_rec = self.position_hold_store.get(symbol)
                    _exit_strategy = _hold_rec.strategy if _hold_rec else None
                    self.position_hold_store.record_exit_with_result(symbol, is_win=pnl_val > 0, strategy=_exit_strategy)
                    self.position_hold_store.remove(symbol)  # clean up record

                # Add to TradeResultStore
                if self.trade_results:
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=datetime.now(timezone.utc).isoformat(),
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_val,
                        is_win=pnl_val > 0,
                        tier="100%",
                        capital_at_close=self._liquid_capital,
                        opened_at=entry_time_str,
                        duration_seconds=duration_secs,
                        strategy=_exit_strategy or "unknown",
                        exit_reason=exit_reason,
                        side=side.lower(),
                        spread_cost=est_spread_cost,
                    ))

                logger.info(f"[OANDA] Flattened {symbol}. Response: {resp}")
                # Remove from tracked so synthetic stop scanner doesn't double-fire
                self._tracked_positions.pop(symbol, None)
                self._save_tracked_positions()
        except Exception as e:
            logger.error(f"[OANDA] Failed to flatten {symbol}: {e}")

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        if not getattr(self, "_authorized", True):
            return None
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
            # Add aliases 'entry_price' and 'direction' for strategy compatibility
            side = "long" if units > 0 else "short"
            avg_price = float(pos.get("long", {}).get("averagePrice", 0)) if units > 0 else float(pos.get("short", {}).get("averagePrice", 0))
            
            # Fetch SL/TP and Entry Time from trade details
            stop_loss = None
            take_profit = None
            entry_time = None
            original_entry_price = None
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
                    if "price" in trade:
                        original_entry_price = float(trade["price"])
            except Exception as e:
                logger.debug(f"[OANDA] Could not fetch SL/TP or Entry Time for {symbol}: {e}")
            
            result = {
                "symbol": symbol.upper(),
                "size": units,
                "side": side,
                "direction": side, # Alias
                "avg_price": avg_price,
                "entry_price": avg_price, # Alias
                "entry_time": entry_time, # Added entry time
                "unrealized_pnl": float(pos.get("unrealizedPL", 0))
            }

            if original_entry_price is not None:
                result["original_entry_price"] = original_entry_price
            
            if stop_loss and stop_loss > 0:
                result["stop_loss"] = stop_loss
            if take_profit and take_profit > 0:
                result["take_profit"] = take_profit
            
            return result
        except Exception:
            return None

    def modify_stop_loss(self, symbol: str, new_stop: float) -> bool:
        """Move the stop-loss on the primary open trade for *symbol*.

        Uses the OANDA v20 TradeCRCDO endpoint to replace the
        existing stop-loss order with a new price.

        Returns True if the modification succeeded, False otherwise.
        """
        if not self._authorized:
            logger.warning("[OANDA] Cannot modify SL: not authorized")
            return False
        try:
            instrument = self._normalize_symbol(symbol)
            r_pos = oanda_positions.PositionDetails(self.account_id, instrument)
            self.client.request(r_pos)
            pos = r_pos.response.get("position", {})
            long_units = float(pos.get("long", {}).get("units", 0))
            short_units = float(pos.get("short", {}).get("units", 0))
            side = "long" if abs(long_units) > abs(short_units) else "short"
            trade_ids = pos.get(side, {}).get("tradeIDs", [])
            if not trade_ids:
                logger.warning(f"[OANDA] modify_stop_loss: no trade IDs for {symbol}")
                return False

            # Determine price format (JPY pairs use 3 decimals, others use 5)
            fmt = ".3f" if "JPY" in instrument else ".5f"

            # Modify all open trades for this symbol (usually just 1)
            for tid in trade_ids:
                data = {
                    "stopLoss": {"price": f"{new_stop:{fmt}}"}
                }
                r_mod = trades.TradeCRCDO(
                    accountID=self.account_id,
                    tradeID=tid,
                    data=data,
                )
                self.client.request(r_mod)
                logger.info(
                    f"[OANDA] STOP MODIFIED {symbol} trade#{tid}: "
                    f"new SL={new_stop:{fmt}}"
                )
            return True
        except Exception as e:
            logger.error(
                f"[OANDA] Failed to modify stop for {symbol}: {e}",
                exc_info=True,
            )
            return False

    def enable_native_trailing_stop(self, symbol: str, distance: float) -> bool:
        """Enable OANDA's server-side trailing stop on all trades for *symbol*.

        Uses the OANDA v20 TradeCRCDO endpoint to replace/add a
        ``trailingStopLoss`` attached to the trade.  The server tracks
        it at tick-level precision, far tighter than the bot's 60-90s
        scan cycle.

        Args:
            symbol: Canonical symbol (e.g. "NZDUSD")
            distance: Trailing distance in price units (NOT pips).
                      For EURUSD 15-pip trail: 0.0015
                      For USDJPY 15-pip trail: 0.15

        Returns True if at least one trade was modified, False otherwise.
        """
        if not self._authorized:
            logger.warning("[OANDA] Cannot enable trailing stop: not authorized")
            return False
        try:
            instrument = self._normalize_symbol(symbol)
            r_pos = oanda_positions.PositionDetails(self.account_id, instrument)
            self.client.request(r_pos)
            pos = r_pos.response.get("position", {})
            long_units = float(pos.get("long", {}).get("units", 0))
            short_units = float(pos.get("short", {}).get("units", 0))
            side = "long" if abs(long_units) > abs(short_units) else "short"
            trade_ids = pos.get(side, {}).get("tradeIDs", [])
            if not trade_ids:
                logger.warning(f"[OANDA] enable_trailing_stop: no trade IDs for {symbol}")
                return False

            fmt = ".3f" if "JPY" in instrument else ".5f"
            success = False
            for tid in trade_ids:
                data = {
                    "trailingStopLoss": {"distance": f"{distance:{fmt}}"}
                }
                # Remove fixed SL when enabling trailing SL
                r_mod = trades.TradeCRCDO(
                    accountID=self.account_id,
                    tradeID=tid,
                    data=data,
                )
                self.client.request(r_mod)
                logger.info(
                    f"[OANDA] TRAILING STOP enabled {symbol} trade#{tid}: "
                    f"distance={distance:{fmt}}"
                )
                success = True
            return success
        except Exception as e:
            logger.error(
                f"[OANDA] Failed to enable trailing stop for {symbol}: {e}",
                exc_info=True,
            )
            return False

    def list_open_position_symbols(self) -> list[str]:
        if not self._authorized:
            return []
        """Returns list of canonical symbols with open positions."""
        if not self._authorized:
            return list(self._tracked_positions.keys())
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
        if not self._authorized:
            return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "OANDA unauthorized"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "OANDA unauthorized")
        if self.read_only:
            logger.warning(f"[OANDA] Read-only mode: skipping execution for {decision.symbol}")
            return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "read-only mode"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "read-only")

        action = decision.action
        
        if action == "close_position":
            # Propagate the strategy/safety-guard reason so the ledger
            # records WHY the position was closed (instead of generic
            # "manual_flatten" for every exit).
            reason = (getattr(decision, 'reason', None)
                      or getattr(decision, 'notes', None)
                      or getattr(decision, 'structure_summary', None)
                      or "signal_close")
            self.flatten_symbol(decision.symbol, exit_reason=reason)
            return ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "flattened"), ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "flatten requested")

        if action in ("scale_out", "scale_out_leg"):
            # ── PARTIAL CLOSE: close a fraction of the open position ──
            reason = (getattr(decision, 'reason', None)
                      or getattr(decision, 'notes', None)
                      or getattr(decision, 'structure_summary', None)
                      or "scale_out")
            pos = self.get_open_position_snapshot(decision.symbol)
            if not pos or abs(pos.get("size", 0)) < 1e-8:
                logger.info(f"[OANDA] scale_out: no position for {decision.symbol}")
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no position to scale out"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no position")
                )
            current_size = abs(pos.get("size", 0))
            # RTFM: 95% guillotine — close 95% at -0.3R
            close_fraction = 0.95
            close_units = int(current_size * close_fraction)
            if close_units < 1:
                # Position too small to partial — flatten entirely
                self.flatten_symbol(decision.symbol, exit_reason=reason)
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "flattened (too small for partial)"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "flatten (dust)")
                )
            # Partial close via OANDA PositionClose endpoint
            try:
                import oandapyV20.endpoints.positions as oanda_positions
                oanda_sym = self._normalize_symbol(decision.symbol)
                side = pos.get("side") or pos.get("direction") or "long"
                if side == "long":
                    close_data = {"longUnits": str(close_units)}
                else:
                    close_data = {"shortUnits": str(close_units)}
                r_close = oanda_positions.PositionClose(
                    self.account_id, instrument=oanda_sym, data=close_data
                )
                self.client.request(r_close)
                resp = r_close.response
                logger.info(
                    f"[OANDA] SCALE OUT {decision.symbol}: closed {close_units} of "
                    f"{int(current_size)} units ({close_fraction:.0%}) — {reason}"
                )
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, f"scale_out {close_fraction:.0%}"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, f"partial close {close_units} units")
                )
            except Exception as e:
                logger.error(f"[OANDA] scale_out failed for {decision.symbol}: {e}", exc_info=True)
                return (
                    ExecutionResult(ExecutionStatus.PROVIDER_ERROR, decision.symbol, f"scale_out error: {e}"),
                    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"scale_out error: {e}")
                )

        entry_actions = {"long", "short", "enter_long", "enter_short", "scale_in", "add_to_position", "flip_to_long", "flip_to_short"}
        if action not in entry_actions:
             return ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no trade action"), ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no trade action")

        # Guard: block duplicate entries for symbols already held.
        # Matches IBKR's guard at _enter_position_for_symbol L729.
        # Without this, the bot re-submits MARKET orders every scan cycle for
        # symbols it already holds, causing FIFO_VIOLATION rejections on OANDA US
        # and occasional micro-position SL deaths.
        if action not in {"scale_in", "add_to_position"}:
            if self._has_active_orders_or_position(decision.symbol):
                logger.info(f"[OANDA] [BLOCKED] Existing position for {decision.symbol}; skipping duplicate entry")
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "existing position"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_EXISTING, decision.symbol, "existing position")
                )

        # Re-entry cooldown — prevent churn after SL/TP exits
        if action not in {"scale_in", "add_to_position"} and decision.symbol in self._exit_cooldowns:
            elapsed = time.time() - self._exit_cooldowns[decision.symbol]
            remaining = self.REENTRY_COOLDOWN - elapsed
            if remaining > 0:
                logger.info(
                    f"[OANDA] [COOLDOWN] {decision.symbol}: blocked re-entry, "
                    f"{remaining:.0f}s remaining of {self.REENTRY_COOLDOWN:.0f}s cooldown"
                )
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, f"re-entry cooldown ({remaining:.0f}s)"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"re-entry cooldown")
                )
            else:
                del self._exit_cooldowns[decision.symbol]

        # ── SUNDAY EARLY SESSION GUARD ─────────────────────────────
        # OANDA spreads balloon to 5-15 pips during the first few hours
        # after the Sunday forex open (5 PM ET). Block new entries during
        # this window to avoid getting eaten alive by spread costs.
        if action not in {"scale_in", "add_to_position"} and self.SUNDAY_BLOCK_HOURS > 0:
            et_tz = timezone(timedelta(hours=-4))  # Eastern Time (EDT)
            now_et = datetime.now(et_tz)
            if now_et.weekday() == 6:  # Sunday
                market_open_hour = 17  # 5 PM ET
                hours_since_open = now_et.hour - market_open_hour if now_et.hour >= market_open_hour else -1
                if 0 <= hours_since_open < self.SUNDAY_BLOCK_HOURS:
                    remaining_hrs = self.SUNDAY_BLOCK_HOURS - hours_since_open
                    logger.warning(
                        f"[OANDA] [BLOCKED] Sunday early session — spreads unreliable. "
                        f"{remaining_hrs}h remaining until normal trading "
                        f"(block window: Sun {market_open_hour}:00-{market_open_hour + self.SUNDAY_BLOCK_HOURS}:00 ET)"
                    )
                    return (
                        ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, f"Sunday spread block ({remaining_hrs}h)"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"Sunday early session")
                    )

        is_short = action in ["short", "enter_short", "flip_to_short"]

        try:
            oanda_sym = self._normalize_symbol(decision.symbol)
            
            # Sizing calculation
            # For OANDA, units are usually base currency (e.g., 1000 for 1000 EUR in EURUSD)
            # risk_per_trade_dollars / (stop_distance)
            price = decision.entry_price
            stop_price = decision.stop_loss
            take_profit = decision.take_profit


            # SL/TP mirror experiment removed (trend bug confirmed & fixed)
            
            if not price or not stop_price:
                 return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "missing price or SL"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "missing price or SL")
                
            if action in {"scale_in", "add_to_position"}:
                original_risk_dist = None
                if hasattr(self, "position_hold_store") and self.position_hold_store:
                    record = self.position_hold_store.get(decision.symbol)
                    if record and getattr(record, "initial_risk", None):
                        original_risk_dist = float(record.initial_risk)
                
                if original_risk_dist and original_risk_dist > 1e-6:
                    stop_dist = original_risk_dist
                    logger.debug(f"[OANDA] Sizing Pyramid using ORIGINAL SL distance: {stop_dist:.5f}")
                else:
                    stop_dist = abs(price - stop_price)
            else:
                stop_dist = abs(price - stop_price)

            if stop_dist < 1e-8:
                 return ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "stop distance too small"), ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "stop distance too small")

            # Guard: reject trades where SL is too tight for forex spreads.
            # OANDA spread is 1-2 pips on majors; at 3 pips the spread alone
            # eats 100% of the SL distance.  10 pips gives ~6.7× breathing room
            # (spread ≈ 30% of SL), so the trade can actually move in our favour.
            MIN_SL_PIPS = 5
            is_jpy = "JPY" in decision.symbol.upper()
            min_sl_dist = MIN_SL_PIPS * (0.01 if is_jpy else 0.0001)
            
            # Exempt Pyramiding from strict entry minimums
            if action not in {"scale_in", "add_to_position"}:
                if stop_dist < min_sl_dist:
                    logger.warning(
                        f"[OANDA] [BLOCKED] SL too tight for {decision.symbol}: "
                        f"{stop_dist:.5f} < min {min_sl_dist:.5f} ({MIN_SL_PIPS} pips)"
                    )
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "SL too tight"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"SL distance {stop_dist:.5f} < min {min_sl_dist:.5f}")
                    )

            # Widen effective stop distance by estimated spread cost.
            # This prevents the bot from sizing too aggressively by accounting for the
            # spread that will be eaten on entry (and again on exit via SL/TP).
            pip_value = self.PIP_VALUE_JPY if "JPY" in decision.symbol.upper() else self.PIP_VALUE_STANDARD
            live_spread = self.get_live_spread(decision.symbol)
            spread_cost = live_spread * pip_value

            # ── SPREAD GATE: Block when spread eats too much of the risk ──
            # If round-trip spread > X% of stop distance, the trade starts
            # so far underwater it's almost guaranteed to lose.
            # Example: AUDJPY spread $24 on $58 stop = 42% → BLOCKED.
            if action not in {"scale_in", "add_to_position"}:
                max_spread_pct = getattr(self.profile, "spread_gate_max_pct", 0.30)
                if stop_dist > 0:
                    spread_pct = spread_cost / stop_dist
                    if spread_pct > max_spread_pct:
                        logger.warning(
                            f"[OANDA] [BLOCKED] Spread too wide for {decision.symbol}: "
                            f"spread={live_spread:.1f} pips ({spread_cost:.5f}) = "
                            f"{spread_pct:.0%} of SL distance {stop_dist:.5f} "
                            f"(max {max_spread_pct:.0%})"
                        )
                        return (
                            ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, f"spread {spread_pct:.0%} > {max_spread_pct:.0%} of SL"),
                            ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"spread {spread_pct:.0%} of SL ({live_spread:.1f} pips)")
                        )

            effective_stop_dist = stop_dist + spread_cost

            # ── JPY QUOTE CONVERSION ─────────────────────────────────
            # For JPY-quoted pairs (USDJPY, EURJPY, etc.), stop_dist is
            # in JPY, but risk_amount is in USD.  Convert stop_dist to
            # USD-per-unit so the formula gives correct units.
            is_jpy_quote = "JPY" in decision.symbol.upper()
            if is_jpy_quote and price > 0:
                effective_stop_dist = effective_stop_dist / price

            logger.debug(
                f"[OANDA] Spread buffer: raw_stop_dist={stop_dist:.5f} + "
                f"spread={spread_cost:.5f} = effective={effective_stop_dist:.8f}"
                f"{' (JPY→USD converted)' if is_jpy_quote else ''}"
            )

            # ── CAPITAL STALENESS GUARD ───────────────────────────────
            # If _liquid_capital is very low, force a refresh before sizing.
            # Prevents stale cached values from API failures.
            if self._liquid_capital < 100.0:
                logger.warning(
                    f"[OANDA] ⚠ Capital is suspiciously low (${self._liquid_capital:.2f}). "
                    f"Forcing account refresh before sizing..."
                )
                self.refresh_account_summary()
                if self._liquid_capital < 100.0:
                    logger.critical(
                        f"[OANDA] Capital still ${self._liquid_capital:.2f} after refresh! "
                        f"Blocking trade to prevent micro-sizing."
                    )
                    return (
                        ExecutionResult(ExecutionStatus.ERROR, decision.symbol, f"capital too low: ${self._liquid_capital:.2f}"),
                        ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"capital too low: ${self._liquid_capital:.2f}")
                    )

            # ── Prop Firm Auto-Sizer ──
            prop_tier = float(getattr(self.profile, "prop_challenge_tier_usd", 0.0))
            prop_loss = float(getattr(self.profile, "prop_challenge_max_loss_pct", 0.0))
            
            if prop_tier > 0 and prop_loss <= 0:
                prop_loss = 0.04 if prop_tier <= 50000 else 0.03
                
            if prop_tier > 0 and prop_loss > 0:
                sizing_capital = prop_tier * prop_loss
                logger.info(f"[OANDA] [PROP FIRM SIZER] True Equity scaling active: ${sizing_capital:,.2f}")
            else:
                sizing_capital = self._liquid_capital

            # 1. Prioritize explicit dollar risk from the strategy (if provided)
            risk_amount = decision.risk_per_trade_dollars or 0.0

            # 2. Handle Pyramiding scale_in relative risk
            # A scale_in passes risk_per_trade_pct (e.g. 0.3 for 30%)
            # We want 30% of the ORIGINAL trade's risk, not 30% of the entire account capital!
            if action in {"scale_in", "add_to_position"} and risk_amount <= 0:
                original_risk = self.profile.risk_per_trade_dollars
                if original_risk <= 0:
                    original_risk = sizing_capital * self.profile.risk_per_trade_pct
                
                scale_fraction = float(decision.risk_per_trade_pct) if decision.risk_per_trade_pct else 0.5
                risk_amount = original_risk * scale_fraction
                logger.debug(f"[OANDA] Scale-In Sizing: original_risk={original_risk:.2f}, fraction={scale_fraction:.2f} -> new_risk={risk_amount:.2f}")

            # 3. Prioritize explicit percentage from the strategy for regular trades
            elif risk_amount <= 0 and decision.risk_per_trade_pct:
                risk_amount = sizing_capital * float(decision.risk_per_trade_pct)

            # 4. Fallback to global profile settings
            if risk_amount <= 0:
                risk_amount = self.profile.risk_per_trade_dollars
                if risk_amount <= 0:
                    risk_amount = sizing_capital * self.profile.risk_per_trade_pct

            # ── CURRENCY CONVERSION: Target Risk to Quote Currency ──
            # The stop_dist is represented in the Quote currency (e.g., JPY, CAD, USD)
            # We must convert the standard USD risk amount into Quote currency first!
            sym_upper = decision.symbol.upper().replace("_", "")
            is_usd_base = sym_upper.startswith("USD")
            is_jpy_quote = sym_upper.endswith("JPY")
            is_cad_quote = sym_upper.endswith("CAD")
            is_chf_quote = sym_upper.endswith("CHF")
            is_usd_quote = sym_upper.endswith("USD")
            
            usd_to_quote_rate = 1.0
            if is_usd_quote:
                usd_to_quote_rate = 1.0
            elif is_usd_base:
                # e.g., USDJPY, USDCAD: The exchange rate is simply the current price of this pair
                usd_to_quote_rate = price
            else:
                # Cross pairs (e.g., EURJPY, AUDCAD) require an external USD exchange rate
                try:
                    from tradebot_sci.market import oanda_provider
                    if is_jpy_quote:
                        usd_to_quote_rate = getattr(oanda_provider, '_last_usdjpy', 150.0) or 150.0
                    elif is_cad_quote:
                        usd_to_quote_rate = getattr(oanda_provider, '_last_usdcad', 1.35) or 1.35
                    elif is_chf_quote:
                        usd_to_quote_rate = getattr(oanda_provider, '_last_usdchf', 0.90) or 0.90
                except Exception:
                    usd_to_quote_rate = 150.0 if is_jpy_quote else (1.35 if is_cad_quote else 1.0)
            
            risk_amount_in_quote = risk_amount * usd_to_quote_rate
            
            # units = risk_in_quote / effective_stop_dist (spread-adjusted)
            units = risk_amount_in_quote / effective_stop_dist
            
            # Leverage-based sizing Cap (Multi-Position Aware)
            # Prevent TOTAL notional across all open positions from exceeding
            # account_equity * target_leverage. This shares the leverage cap
            # across all positions instead of allowing each to use the full 50x.
            target_leverage = getattr(self.profile, "target_leverage", 50.0)
            if target_leverage > 0:
                max_notional = self._liquid_capital * target_leverage
                sym_upper = decision.symbol.upper().replace("_", "")
                is_usd_base = sym_upper.startswith("USD")
                is_jpy_quote = sym_upper.endswith("JPY") and not is_usd_base
                if is_usd_base:
                    notional_per_unit = 1.0
                elif is_jpy_quote:
                    usdjpy_rate = 157.0
                    try:
                        from tradebot_sci.market import oanda_provider
                        usdjpy_rate = getattr(oanda_provider, '_last_usdjpy', 157.0) or 157.0
                    except Exception:
                        pass
                    notional_per_unit = price / usdjpy_rate if usdjpy_rate > 0 else price
                else:
                    notional_per_unit = price if price > 0 else 1.0

                # ── MULTI-POSITION LEVERAGE HEADROOM ──
                # Sum notional value of all existing open positions, then subtract
                # from the total leverage cap to avoid over-exposing the account.
                existing_notional = 0.0
                try:
                    for sym, pos_info in self._tracked_positions.items():
                        pos_size = abs(float(pos_info.get("size", 0)))
                        pos_price = float(pos_info.get("avg_price", 0)) or 1.0
                        pos_sym = sym.upper().replace("_", "")
                        if pos_sym.startswith("USD"):
                            existing_notional += pos_size * 1.0
                        elif pos_sym.endswith("JPY"):
                            existing_notional += pos_size * (pos_price / usdjpy_rate) if usdjpy_rate > 0 else pos_size
                        else:
                            existing_notional += pos_size * pos_price
                except Exception as e:
                    logger.debug(f"[OANDA] Could not calculate existing notional: {e}")

                remaining_notional = max(max_notional - existing_notional, 0)
                max_units = remaining_notional / notional_per_unit if notional_per_unit > 0 else 0

                logger.info(
                    f"[OANDA] Leverage Headroom: existing=${existing_notional:,.0f} / "
                    f"cap=${max_notional:,.0f} ({target_leverage}x), "
                    f"remaining=${remaining_notional:,.0f}, max_units={max_units:.0f}"
                )

                if abs(units) > max_units and max_units > 0:
                    logger.warning(
                        f"[OANDA] Sizing Cap: Calculated units {abs(units):.2f} exceeds "
                        f"leverage cap {max_units:.2f} (Leverage={target_leverage}x, "
                        f"notional_per_unit={'$1' if is_usd_base else f'${notional_per_unit:.4f}'})"
                    )
                    units = max_units if units > 0 else -max_units
                elif max_units <= 0 and remaining_notional <= 0:
                    logger.warning(
                        f"[OANDA] [BLOCKED] No leverage headroom for {decision.symbol}: "
                        f"existing=${existing_notional:,.0f} >= cap=${max_notional:,.0f}"
                    )
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "leverage headroom exhausted"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"leverage headroom exhausted")
                    )

            logger.info(
                f"[OANDA] [SIZING] {decision.symbol}: capital=${self._liquid_capital:.2f} "
                f"risk_pct={self.profile.risk_per_trade_pct} risk=${risk_amount:.2f} "
                f"stop_dist={stop_dist:.5f} eff_stop={effective_stop_dist:.8f} "
                f"raw_units={risk_amount/effective_stop_dist:.0f} "
                f"lev_cap={target_leverage}x final_units={int(abs(units))}"
            )

            if is_short:
                units = -units
            
            # Crypto might require more than 0 decimals, Forex usually whole units
            is_crypto = any(c in decision.symbol.upper() for c in ["BTC", "ETH", "SOL", "ADA", "LTC"])
            
            # Allow fractional units for crypto, integer for forex
            if is_crypto:
                units = round(units, 4)
                min_size = 0.0001
            else:
                units = int(units)
                min_size = 1
                
            if abs(units) < min_size:
                logger.warning(f"[OANDA] Calculated units too small: {units} for {decision.symbol} (min={min_size}). This is likely a pyramid scale-in that was too small.")
                return ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "units too small"), ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "units too small")

            # Prepare Order — use LIMIT FOK to reduce slippage, fallback to MARKET IOC
            fmt = ".5f" if not is_crypto else ".2f"
            if "JPY" in decision.symbol: fmt = ".3f"  # JPY pairs use 3 decimals

            order_data = None
            if self.USE_LIMIT_ORDERS:
                # Fetch live bid/ask for LIMIT pricing
                try:
                    _oanda_sym = self._normalize_symbol(decision.symbol)
                    params = {"instruments": _oanda_sym}
                    r_pricing = pricing.PricingInfo(self.account_id, params=params)
                    resp_pricing = self.client.request(r_pricing)
                    prices = resp_pricing.get("prices", [])
                    if prices:
                        p = prices[0]
                        bids = p.get("bids", [])
                        asks = p.get("asks", [])
                        if bids and asks:
                            bid = float(bids[0].get("price", 0))
                            ask = float(asks[0].get("price", 0))
                            mid = (bid + ask) / 2.0
                            pip_val = self.PIP_VALUE_JPY if "JPY" in decision.symbol.upper() else self.PIP_VALUE_STANDARD
                            buffer = self.LIMIT_ORDER_BUFFER_PIPS * pip_val
                            # For buys: limit slightly above ask; for sells: slightly below bid
                            if units > 0:  # buy
                                limit_price = ask + buffer
                            else:  # sell
                                limit_price = bid - buffer
                            order_data = {
                                "order": {
                                    "units": str(units),
                                    "instrument": oanda_sym,
                                    "timeInForce": "FOK",
                                    "type": "LIMIT",
                                    "price": f"{limit_price:{fmt}}",
                                    "positionFill": "DEFAULT"
                                }
                            }
                            logger.info(
                                f"[OANDA] Using LIMIT order @ {limit_price:{fmt}} "
                                f"(bid={bid:{fmt}} ask={ask:{fmt}} mid={mid:{fmt}} buffer={buffer:.5f})"
                            )
                except Exception as e:
                    logger.warning(f"[OANDA] LIMIT pricing failed, falling back to MARKET: {e}")

            # Fallback to MARKET IOC if LIMIT pricing unavailable or disabled
            if order_data is None:
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
                order_data["order"]["stopLossOnFill"] = {"price": f"{stop_price:{fmt}}"}
            if take_profit:
                order_data["order"]["takeProfitOnFill"] = {"price": f"{take_profit:{fmt}}"}

            # Refresh account summary to get latest margin info
            self.refresh_account_summary()
            
            # Additional Margin Logging + Margin Sufficiency Gate
            try:
                r_summary = accounts.AccountSummary(self.account_id)
                self.client.request(r_summary)
                summ = r_summary.response.get("account", {})
                margin_used = summ.get("marginUsed", "0")
                margin_avail = float(summ.get("marginAvailable", "0"))
                margin_rate = summ.get("marginRate", "0")
                nav = float(summ.get("NAV", "0"))
                logger.info(f"[OANDA] Pre-order Margin Check: Used=${margin_used}, Available=${margin_avail:.4f}, Leverage={1/float(margin_rate) if float(margin_rate) > 0 else 'N/A'}:1")

                # ── MARGIN GATE: Abort if available margin < 1% of NAV or $5 (whichever is greater) ──
                # Exempt pyramids (scale_in / add_to_position) — let OANDA reject server-side if needed.
                min_margin = max(nav * 0.01, 5.0)
                if action not in {"scale_in", "add_to_position"} and margin_avail < min_margin:
                    logger.warning(
                        f"[OANDA] [BLOCKED] Insufficient margin for {decision.symbol}: "
                        f"Available=${margin_avail:.2f} < min ${min_margin:.2f} (Max of 1% NAV=${nav:.2f} or $5)"
                    )
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "insufficient margin"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, f"margin ${margin_avail:.2f} < ${min_margin:.2f}")
                    )
            except Exception as e:
                logger.warning(f"[OANDA] Could not fetch detailed margin info: {e}")

            logger.info(f"[OANDA] Placing {decision.action} order for {decision.symbol}: {units} units")
            # Log specific tags for GUI parsing (Arrows & Tables)
            logger.info(f"[ENTRY] {decision.symbol} side={'buy' if units > 0 else 'sell'} amount={abs(units)} price={decision.entry_price or 0}")
            r = orders.OrderCreate(self.account_id, data=order_data)
            self.client.request(r)

            
            res = r.response
            if "orderFillTransaction" in res:
                fill = res["orderFillTransaction"]
                avg_fill = float(fill.get("price") or 0.0)
                if avg_fill > 0:
                    logger.info(f"[FILL] {decision.symbol} @ {avg_fill} (ID: {fill['id']})")
                logger.info(f"[OANDA] Order filled: {fill['id']} at {fill['price']}")

                # Live Bot Pyramiding Math Fix
                # On initial entry, persist the original entry price and initial risk
                if action not in {"scale_in", "add_to_position"} and hasattr(self, "position_hold_store") and self.position_hold_store:
                    stop_loss_val = getattr(decision, "stop_loss", None)
                    initial_risk_val = abs(avg_fill - stop_loss_val) if stop_loss_val else None
                    self.position_hold_store.upsert(
                        symbol=decision.symbol,
                        opened_at=datetime.now(timezone.utc),
                        stop_loss=stop_loss_val,
                        entry_price=avg_fill,
                        take_profit=getattr(decision, "take_profit", None),
                        size=units,
                        strategy=getattr(decision, "strategy_name", None) or "unknown",
                        original_entry_price=avg_fill,
                        initial_risk=initial_risk_val
                    )

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
        """
        Detect OANDA positions that disappeared (SL/TP filled server-side)
        and log [EXIT] for the GUI/ledger to pick up.
        """
        results = []
        try:
            # Snapshot current open positions from OANDA
            current_symbols = set(self.list_open_position_symbols())

            # Get current balance for PnL calc
            try:
                r = accounts.AccountSummary(self.account_id)
                self.client.request(r)
                current_balance = float(r.response.get("account", {}).get("balance", 0))
            except Exception:
                current_balance = None

            # ── Detect vanished positions (SL/TP filled externally) ──
            for sym, prev in list(self._tracked_positions.items()):
                if sym not in current_symbols:
                    # Position is gone — OANDA closed it (SL/TP or manual)
                    # Query OANDA API for the actual realized PnL
                    pnl = 0.0
                    pnl_pct = 0.0
                    side = "short" if prev.get("size", 0) < 0 else "long"

                    try:
                        r_closed = trades.TradesList(
                            self.account_id,
                            params={"state": "CLOSED", "instrument": self._normalize_symbol(sym), "count": 5}
                        )
                        closed_resp = self.client.request(r_closed)
                        closed_trades = closed_resp.get("trades", [])
                        if closed_trades:
                            latest = closed_trades[0]
                            gross_pl = float(latest.get("realizedPL", 0))
                            financing = float(latest.get("financing", 0))
                            dividend = float(latest.get("dividendAdjustment", 0))
                            pnl = gross_pl + financing + dividend
                            initial_units = float(latest.get("initialUnits", 0))
                            price = float(latest.get("price", 0))
                            if initial_units != 0 and price > 0:
                                pnl_pct = (pnl / (abs(initial_units) * price)) * 100
                            side = "short" if initial_units < 0 else "long"
                            logger.info(f"[OANDA] Closed trade found via API: {sym} PnL=${pnl:.4f}")
                        else:
                            logger.warning(f"[OANDA] No closed trades found for {sym}, skipping exit log")
                            del self._tracked_positions[sym]
                            continue
                    except Exception as e:
                        logger.warning(f"[OANDA] Could not query closed trades for {sym}: {e}")
                        # Fall back to balance delta if API fails
                        if current_balance is not None and self._prev_balance is not None:
                            pnl = current_balance - self._prev_balance
                            entry_price = prev.get("avg_price") or prev.get("entry_price", 0)
                            units = abs(prev.get("size", 0))
                            if entry_price > 0 and units > 0:
                                pnl_pct = (pnl / (entry_price * units)) * 100
                        else:
                            # Cannot determine PnL at all — skip this exit
                            logger.warning(f"[OANDA] Cannot determine PnL for {sym}, skipping exit log")
                            del self._tracked_positions[sym]
                            continue

                    # Estimate spread cost for logging
                    pip_value = self.PIP_VALUE_JPY if "JPY" in sym.upper() else self.PIP_VALUE_STANDARD
                    units = abs(prev.get("size", 0))
                    est_spread = units * self.get_live_spread(sym) * pip_value * 2
                    if "JPY" in sym.upper():
                        _ep = prev.get("avg_price", 0) or prev.get("entry_price", 0)
                        if _ep > 0:
                            est_spread /= _ep  # Convert JPY spread to USD

                    entry_time_str = prev.get("entry_time")
                    duration_str, duration_secs = self._compute_duration(entry_time_str)

                    pnl_sign = '+' if pnl >= 0 else '-'
                    pnl_str = f"{pnl_sign}${abs(pnl):.2f}"
                    logger.info(
                        f"[EXIT] OANDA SL/TP: {sym} {pnl_str} "
                        f"(Pct={pnl_pct:.2f}%) position={side.upper()} | "
                        f"Duration={duration_str} | "
                        f"Est. Spread Cost: ${est_spread:.4f}"
                    )
                    # Record exit for re-entry cooldown (losses only — wins can re-enter immediately)
                    if pnl <= 0:
                        self._exit_cooldowns[sym] = time.time()
                    # Register with SafetyGuard for Streak Breaker & Exit Cooldown
                    try:
                        from tradebot_sci.strategy.safety_guard import SafetyGuard
                        is_win = pnl > 0
                        SafetyGuard.register_trade_completion(sym, is_win)
                        logger.info(f"[STREAK] Registered {'WIN' if is_win else 'LOSS'} for {sym} (streak count: {SafetyGuard._state.symbol_loss_streaks.get(sym, 0)})")
                    except Exception as e:
                        logger.error(f"[STREAK] Failed to register trade completion for {sym}: {e}")

                    # Read strategy from hold store before removing
                    _exit_strategy = None
                    if self.position_hold_store:
                        _hold_rec = self.position_hold_store.get(sym)
                        _exit_strategy = _hold_rec.strategy if _hold_rec else None
                        self.position_hold_store.record_exit_with_result(sym, is_win=pnl > 0, strategy=_exit_strategy)
                        self.position_hold_store.remove(sym)  # clean up record

                    # Record in TradeResultStore for pnl_stats
                    if self.trade_results:
                        from datetime import datetime as _dt, timezone as _tz
                        self.trade_results.add_result(TradeResult(
                            symbol=sym,
                            closed_at=_dt.now(_tz.utc).isoformat(),
                            pnl_pct=pnl_pct,
                            pnl_usd=pnl,
                            is_win=pnl > 0,
                            tier="100%",
                            capital_at_close=current_balance or self._liquid_capital,
                            opened_at=entry_time_str,
                            duration_seconds=duration_secs,
                            strategy=_exit_strategy or "unknown",
                            exit_reason="sl_tp_hit",
                            side=side.lower() if side else None,
                            spread_cost=est_spread,
                        ))

                    del self._tracked_positions[sym]
                    results.append(ExecutionResult(
                        ExecutionStatus.EXIT_SIGNAL, sym,
                        f"OANDA SL/TP exit PnL={pnl:.2f}"
                    ))

            # ── Track new/existing positions ──
            for sym in current_symbols:
                snap = self.get_open_position_snapshot(sym)
                if snap and abs(snap.get("size", 0)) > 1e-8:
                    # Enrich with strategy from hold store
                    if self.position_hold_store and sym in self.position_hold_store:
                        hold_rec = self.position_hold_store[sym]
                        if hasattr(hold_rec, 'strategy') and hold_rec.strategy:
                            snap["strategy"] = hold_rec.strategy
                    self._tracked_positions[sym] = snap

            # Update previous balance for next cycle
            if current_balance is not None:
                self._prev_balance = current_balance

            # Persist tracked positions to disk
            self._save_tracked_positions()

        except Exception as e:
            logger.error(f"[OANDA] evaluate_synthetic_stops error: {e}")
        finally:
            # Always persist tracked positions, even if the scan errored mid-way
            try:
                self._save_tracked_positions()
            except Exception:
                pass
        return results

    def summarize_pnl(self) -> None:
        pass

    def _fetch_symbol_state(self, symbol: str) -> dict:
        pos = self.get_open_position_snapshot(symbol)
        return {"position": pos} if pos else {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        pos = self.get_open_position_snapshot(symbol)
        return pos is not None
