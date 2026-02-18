from __future__ import annotations


import json
import logging
import math
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
from typing import Any, ClassVar, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from tradebot_sci.broker.execution import (
    ExecutionOutcome,
    ExecutionOutcomeType,
    ExecutionResult,
    ExecutionStatus,
)
from tradebot_sci.config.broker import BrokerSettings, load_ibkr_broker_options
from tradebot_sci.config.models import RuntimeSettings, TradingProfileSettings
from tradebot_sci.market.contracts import ContractResolutionError, build_contract
from tradebot_sci.market.symbols import AssetClass, SymbolMetadata, SYMBOL_METADATA
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.broker.synthetic_stop_store import (
    SyntheticStopRecord,
    SyntheticStopStore,
)
from tradebot_sci.broker.position_hold_store import PositionHoldStore
from tradebot_sci.broker.ibkr.bracket_manager import BracketManager
from tradebot_sci.broker.ibkr.pdt_guard import PDTGuard
from tradebot_sci.broker.ibkr.synthetic_stops import SyntheticStop, SyntheticStopManager


# SyntheticStop moved to synthetic_stops.py


@dataclass
class EntryPreparation:
    candidate: float
    ai_dir: str
    campaign: object
    state: dict
    per_share_risk: float
    open_risk: float
    max_risk_dollars: float
    shares_cap: float

logger = logging.getLogger(__name__)

WORKING_ORDER_STATUSES = {"PendingSubmit", "PreSubmitted", "Submitted"}

DEFAULT_CRYPTO_QTY_STEPS: dict[str, float] = {
    "BTCUSD": 0.0001,
    "ETHUSD": 0.001,
    "SOLUSD": 0.01,
}


class StopOrderUnsupportedError(Exception):
    """Raised when the venue rejects stop orders and local stops are disabled."""

    def __init__(self, symbol: str, exchange: str) -> None:
        self.symbol = symbol.upper()
        self.exchange = exchange
        super().__init__(
            f"{self.symbol} venue {self.exchange} does not support stop orders; enable local stop protection"
        )


# 
class IbkrExecutor:
    """Translates AITradeDecision into IBKR orders so you can sip coffee instead of click buttons."""

    def __init__(
        self,
        settings: Optional[BrokerSettings] = None,
        runtime_settings: Optional[RuntimeSettings] = None,
        profile_settings: Optional[TradingProfileSettings] = None,
        ib_client=None,
        allowed_symbols: Iterable[str] | None = None,
        position_hold_store_path: str | None = None,
    ) -> None:
        """Loads broker settings and primes a (possibly pretend) IBKR connection."""
        self.settings = settings or load_ibkr_broker_options()
        self.runtime = runtime_settings or RuntimeSettings()
        self.ib = ib_client or self._lazy_ib_client()
        self.profile_settings = profile_settings
        self.placed_orders = []
        overrides = getattr(self.runtime, "local_stop_symbols", []) or []
        self._local_stop_symbols = {symbol.upper() for symbol in overrides}
        
        # Initialize modular components
        self.bracket_manager = BracketManager(self.ib, self.runtime, self.profile_settings)
        self.pdt_guard = PDTGuard(self.profile_settings)
        self.stop_manager = SyntheticStopManager()
        
        # Legacy attributes for test compatibility
        self._local_stop_info: dict[str, dict] = {}
        self._native_stop_supported: dict[str, bool] = {}
        self._synthetic_stops = self.stop_manager.stops
        self._pdt_guard_enabled = bool(getattr(profile_settings, "pdt_guard_enabled", False))
        self._pdt_roundtrip_limit = int(getattr(profile_settings, "pdt_roundtrip_limit", 3))
        
        self._last_bracket_orders: list[Any] = []
        store_path = os.getenv("SYNTH_STOP_STORE_PATH") or (
            profile_settings.synthetic_stop_store_path if profile_settings else "state/synthetic_stops.json"
        )
        self._stop_store = (
            SyntheticStopStore(store_path)
            if profile_settings and profile_settings.synthetic_stop_persistence_enabled
            else None
        )
        self._paused_symbols: set[str] = set()
        self._integrity_counter = 0
        self._zero_hash_symbols = self._discover_zero_hash_symbols()
        self._scale_in_counts: dict[str, int] = {}
        self._position_metadata: dict[str, dict] = {}  # Stores htf_neutral_bars, pyramid_count, etc.
        self._zero_hash_symbols_set = {s.upper() for s in self._zero_hash_symbols}
        self._allowed_symbols = (
            {symbol.upper() for symbol in allowed_symbols} if allowed_symbols else None
        )
        self._account_segments: dict[str, float] = {}
        store_path = (
            position_hold_store_path
            or os.getenv("POSITION_HOLD_STORE_PATH")
            or self.runtime.position_hold_store_path
        )
        self._position_hold_store = PositionHoldStore(store_path)
        self._sync_position_holds_with_ib()
        if self.ib and hasattr(self.ib, "execDetailsEvent"):
            self.ib.execDetailsEvent += self._on_exec_details
        self._contract_symbol_map = self._build_contract_symbol_map()
        self._account_summary: dict[str, float] = {}
        self._last_account_summary: datetime | None = None
        self._contract_cache: dict[str, Any] = {}
        self._daily_risk_state: dict[str, Any] = {
            "date": None,
            "start_net_liq": None,
            "last_net_liq": None,
            "consecutive_losses": 0,
        }

    @property
    def position_hold_store(self) -> PositionHoldStore:
        return self._position_hold_store

    @property
    def profile(self):
        """Alias for profile_settings to maintain interface compatibility with loop.py."""
        return self.profile_settings

    @property
    def _pdt_roundtrips_today(self) -> int:
        return self.pdt_guard.roundtrips_today
    
    @_pdt_roundtrips_today.setter
    def _pdt_roundtrips_today(self, value: int):
        self.pdt_guard.roundtrips_today = value
        
    @property
    def _pdt_current_date(self):
        return self.pdt_guard.current_date

    @_pdt_current_date.setter
    def _pdt_current_date(self, value):
        self.pdt_guard.current_date = value
        
    @property
    def _pdt_entry_dates(self) -> dict:
        return self.pdt_guard.entry_dates

    def _get_min_tick(self, contract: object, symbol: str) -> float | None:
        return self.bracket_manager.get_min_tick(contract, symbol)

    @staticmethod
    def _round_price_to_tick(price: float, tick: float) -> float:
        return BracketManager.round_price_to_tick(price, tick)

    @staticmethod
    def _align_bracket_prices(
        direction: str,
        entry: float,
        take_profit: float,
        stop_loss: float,
        tick: float,
    ) -> tuple[float, float, float]:
        return BracketManager.align_prices(direction, entry, take_profit, stop_loss, tick)

    @staticmethod
    def _effective_tif(asset_class: AssetClass | None, exchange: str | None, default: str) -> str:
        return BracketManager.effective_tif(asset_class, exchange, default)

    @staticmethod
    def _apply_zerohash_minutes_tif(order: Any) -> None:
        return BracketManager.apply_zerohash_minutes_tif(order)

    @staticmethod
    def _set_order_ref(order: Any, symbol: str, tag: str) -> None:
        return BracketManager.set_order_ref(order, symbol, tag)

    def _make_outcome(
        self,
        symbol: str,
        outcome_type: ExecutionOutcomeType,
        reason: str,
        detail: str | None = None,
        order_ids: list[int] | None = None,
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            status=outcome_type,
            symbol=symbol,
            reason=reason,
            detail=detail,
            order_ids=order_ids,
        )

    def _respond(
        self,
        result: ExecutionResult,
        outcome_type: ExecutionOutcomeType,
        reason: str,
        detail: str | None = None,
        order_ids: list[int] | None = None,
    ) -> tuple[ExecutionResult, ExecutionOutcome]:
        return (
            result,
            self._make_outcome(
                result.symbol,
                outcome_type,
                reason,
                detail=detail,
                order_ids=order_ids,
            ),
        )

    def _lazy_ib_client(self):
        """Creates an IB client or a polite stub if ib_insync isn't around."""
        try:
            from ib_insync import IB  # type: ignore

            ib = IB()
            ib.connect(
                self.settings.host,
                int(self.settings.port),
                clientId=int(self.settings.client_id),
                readonly=self.settings.read_only,
            )
            return ib
        except ImportError:
            logger.warning("ib_insync not installed; running in dry-run mode.")
            return None
        except Exception as exc:  # pragma: no cover - connection failures
            raise RuntimeError(f"Failed to connect to IBKR: {exc}") from exc

    def _build_contract_symbol_map(self) -> dict[tuple[str, str], str]:
        mapping: dict[tuple[str, str], str] = {}
        for symbol, metadata in SYMBOL_METADATA.items():
            key = (metadata.contract_symbol.upper(), metadata.currency.upper())
            mapping[key] = symbol
        return mapping

    def _canonical_symbol_for_contract(self, contract) -> str | None:
        if not contract:
            return None
        contract_symbol = getattr(contract, "symbol", None)
        if not contract_symbol:
            return None
        currency = getattr(contract, "currency", None) or "USD"
        key = (contract_symbol.upper(), currency.upper())
        if contract_symbol.upper() in {"BIP", "BITCOIN", "BTC"}:
            return "BTCUSD"
        if contract_symbol.upper() in {"ETP", "ETHER", "ETH"}:
            return "ETHUSD"

        if key in self._contract_symbol_map:
            return self._contract_symbol_map[key]
        fallback = f"{contract_symbol.upper()}{currency.upper()}"
        if fallback in SYMBOL_METADATA:
            return fallback
        if contract_symbol.upper() in SYMBOL_METADATA:
            return contract_symbol.upper()
        return None

    def _contract_matches_symbol(self, symbol: str, contract: Any) -> bool:
        """True if the IB contract maps to the given canonical symbol.

        IBKR crypto positions use `contract.symbol` like `SOL` while the bot uses `SOLUSD`.
        """
        sym = (symbol or "").upper()
        if not sym or not contract:
            return False
        contract_symbol = (getattr(contract, "symbol", "") or "").upper()
        if contract_symbol == sym:
            return True
        canonical = self._canonical_symbol_for_contract(contract)
        if canonical and canonical.upper() == sym:
            return True
        return False

    def _is_symbol_allowed(self, symbol: str) -> bool:
        if not self._allowed_symbols:
            return True
        return symbol.upper() in self._allowed_symbols

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        """Places or simulates orders based on AITradeDecision, while double-checking sanity."""
        if self.settings.read_only or self.settings.execution_mode == "simulate":
            logger.info("Read-only or simulate mode: would execute %s", decision.summary())
            return (
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "simulation mode"),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SKIPPED,
                    "simulation mode",
                ),
            )

        if decision.action in {"stand_aside", "hold"}:
            logger.info("Standing aside / holding: %s", decision.summary())
            return (
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "AI requested stand aside"),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SKIPPED,
                    "AI stand aside",
                ),
            )

        if not self.ib:
            logger.warning("IBKR connection unavailable; cannot execute %s", decision.summary())
            return self._respond(
                ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "IB connection unavailable"),
                ExecutionOutcomeType.ERROR,
                "IB connection unavailable",
            )

        symbol = decision.symbol.upper()
        self._symbol = symbol
        if not self._is_symbol_allowed(symbol):
            allowed_list = ", ".join(sorted(self._allowed_symbols)) if self._allowed_symbols else "none"
            logger.warning(
                "[BLOCKED] %s not in allowed trading universe; allowed=%s",
                symbol,
                allowed_list,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.RISK_SUPPRESSED,
                    decision.symbol,
                    "symbol not permitted",
                ),
                ExecutionOutcomeType.BLOCKED_SYMBOL_NOT_ALLOWED,
                "symbol not permitted",
                f"allowed={allowed_list}",
            )
        metadata = SYMBOL_METADATA.get(symbol)
        if not metadata:
            logger.info("[UNSUPPORTED_SYMBOL] %s has no known metadata", symbol)
            return (
                ExecutionResult(
                    ExecutionStatus.UNSUPPORTED_SYMBOL,
                    decision.symbol,
                    "symbol unsupported",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.ERROR,
                    "symbol unsupported",
                ),
            )
        if metadata.asset_class == AssetClass.FUTURE:
            logger.info("[UNSUPPORTED_SYMBOL_CONFIG] %s futures trading disabled for now", symbol)
            return (
                ExecutionResult(
                    ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG,
                    decision.symbol,
                    "futures not yet supported",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.ERROR,
                    "future symbol not supported",
                ),
            )

        self._ensure_emergency_stop()
        if decision.action in {"enter_long", "enter_short", "scale_in", "add_to_position"}:
            # Note: add_to_position is handled like scale_in (pyramiding into existing position)
            return self._enter_position_for_symbol(decision)
        if decision.action in {"scale_out", "close_position"}:
            return self._scale_or_close_stock(decision)
        if decision.action in {"flip_to_long", "flip_to_short"}:
            return self._flip_position_for_symbol(decision)
        logger.info("No execution for action %s", decision.action)
        return (
            ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no execution path"),
            self._make_outcome(
                decision.symbol,
                ExecutionOutcomeType.SKIPPED,
                "no execution path",
            ),
        )

    def _flip_position_for_symbol(
        self, decision: AITradeDecision
    ) -> tuple[ExecutionResult, ExecutionOutcome]:
        symbol = self._symbol
        if self._pdt_guard_enabled and self._flip_cooldown_seconds > 0:
            last_ts = self._flip_last_ts.get(symbol.upper())
            if last_ts is not None and (time.time() - last_ts) < self._flip_cooldown_seconds:
                remaining = self._flip_cooldown_seconds - (time.time() - last_ts)
                return self._respond(
                    ExecutionResult(
                        ExecutionStatus.STAND_ASIDE,
                        decision.symbol,
                        "flip cooldown active",
                    ),
                    ExecutionOutcomeType.BLOCKED_GUARD,
                    f"flip_cooldown_remaining={remaining:.1f}s",
                )
        target_dir = "long" if decision.action == "flip_to_long" else "short"
        caps = self.get_execution_capabilities(symbol)
        if target_dir == "short" and (caps.get("long_only") is True or caps.get("supports_short") is False):
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "flip blocked: long-only venue",
                ),
                ExecutionOutcomeType.BLOCKED_GUARD,
                "flip long-only venue",
            )
        state = self._fetch_symbol_state(symbol)
        pos_size = float(state.get("position_shares", 0) or 0.0)
        if pos_size == 0:
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "no open position to flip",
                ),
                ExecutionOutcomeType.SKIPPED,
                "no open position to flip",
            )
        current_dir = "long" if pos_size > 0 else "short"
        if current_dir == target_dir:
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "already on target side",
                ),
                ExecutionOutcomeType.SKIPPED,
                "already on target side",
            )

        self.cancel_all_orders_for_symbol(symbol)
        close_decision = decision.model_copy(update={"action": "close_position"})
        close_result, close_outcome = self._scale_or_close_stock(
            close_decision,
            bypass_hold_guard=True,
            bypass_pdt_exit=True,
        )
        if close_outcome.status != ExecutionOutcomeType.SUCCESS_SUBMITTED:
            return close_result, close_outcome
        if not self._wait_for_flat_position(symbol):
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "position not flat after flip close",
                ),
                ExecutionOutcomeType.BLOCKED_EXISTING,
                "position not flat after flip close",
            )

        entry_action = "enter_long" if target_dir == "long" else "enter_short"
        entry_decision = decision.model_copy(update={"action": entry_action})
        entry_result, entry_outcome = self._enter_position_for_symbol(
            entry_decision,
            allow_opposite_entry=True,
        )
        if entry_outcome.status == ExecutionOutcomeType.SUCCESS_SUBMITTED:
            self._flip_last_ts[symbol.upper()] = time.time()
        return entry_result, entry_outcome

    def _wait_for_flat_position(self, symbol: str, timeout_seconds: int = 8) -> bool:
        deadline = time.time() + max(1, timeout_seconds)
        while time.time() < deadline:
            state = self._fetch_symbol_state(symbol)
            if abs(state.get("position_shares", 0) or 0.0) == 0:
                return True
            try:
                self.ib.sleep(1)
            except Exception:
                time.sleep(1)
        return False
    def _validate_entry_guards(
        self,
        decision: AITradeDecision,
        allow_opposite_entry: bool = False,
    ) -> tuple[ExecutionResult, ExecutionOutcome] | None:
        """Run all pre-entry guard checks.

        Returns ``None`` when all guards pass, otherwise returns the
        rejection ``(ExecutionResult, ExecutionOutcome)`` tuple.  The
        caller can use the decision as-is (with possible TP suppression
        applied via model_copy) if this returns ``None``.
        """
        if decision.entry_price is None or decision.stop_loss is None:
            logger.warning("Missing entry or stop; refusing to place %s bracket.", self._symbol)
            return self._respond(
                ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "missing entry or stop"),
                ExecutionOutcomeType.ERROR,
                "missing entry or stop",
            )

        symbol = self._symbol
        metadata = SYMBOL_METADATA.get(symbol)
        if not metadata:
            logger.info("[UNSUPPORTED_SYMBOL] %s has no metadata; skipping", symbol)
            return self._respond(
                ExecutionResult(ExecutionStatus.UNSUPPORTED_SYMBOL, decision.symbol, "metadata missing"),
                ExecutionOutcomeType.ERROR,
                "metadata missing",
            )

        # TP hold guard (mutates decision but not a rejection)
        if decision.take_profit and not self._can_place_take_profit(symbol):
            age = self._position_hold_age_seconds(symbol) or 0.0
            logger.info("[HOLD_GUARD] Suppressing TP for %s (held=%.1f sec)", symbol, age)
            # note: model_copy is local to this scope; the caller re-derives via passed decision

        if not self._check_pdt_guard(symbol, metadata):
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "pdt guard triggered"),
                ExecutionOutcomeType.BLOCKED_PDT,
                "pdt guard triggered",
            )

        campaign = self._campaign_state(symbol)
        if campaign.position_size > 0 and decision.action == "enter_short" and not allow_opposite_entry:
            logger.info(
                "[GUARD] Suppressed opposite-side entry for %s; existing long position of %.2f shares",
                symbol, campaign.position_size,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "opposite side exists"),
                ExecutionOutcomeType.BLOCKED_EXISTING,
                "existing opposite position",
            )
        if campaign.position_size < 0 and decision.action == "enter_long" and not allow_opposite_entry:
            logger.info(
                "[GUARD] Suppressed opposite-side entry for %s; existing short position of %.2f shares",
                symbol, campaign.position_size,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "opposite side exists"),
                ExecutionOutcomeType.BLOCKED_EXISTING,
                "existing opposite position",
            )

        ai_dir = "long" if decision.action in {"enter_long"} else "short"
        if decision.action == "scale_in":
            if campaign.has_position:
                ai_dir = "long" if campaign.position_size > 0 else "short"
            else:
                logger.info("[GUARD] Suppressing scale_in: no open position for %s", symbol)
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no open position"),
                    ExecutionOutcomeType.SKIPPED,
                    "scale_in no open position",
                )
            if campaign.side and ai_dir != campaign.side:
                logger.info(
                    "[GUARD] Suppressing scale_in: direction mismatch (side=%s requested=%s)",
                    campaign.side, ai_dir,
                )
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "direction mismatch"),
                    ExecutionOutcomeType.SKIPPED,
                    "scale_in direction mismatch",
                )

        if metadata.asset_class == AssetClass.CRYPTO and ai_dir == "short":
            try:
                contract = self._contract_for_symbol(symbol)
                contract_exchange = (getattr(contract, "exchange", "") or "").upper()
            except Exception:
                contract_exchange = ""
            if contract_exchange == "ZEROHASH":
                logger.info(
                    "[GUARD] Suppressing short on %s: ZEROHASH crypto spot does not allow short sales",
                    symbol,
                )
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "short not supported on ZEROHASH"),
                    ExecutionOutcomeType.BLOCKED_GUARD,
                    "short not supported on ZEROHASH",
                )

        if campaign.has_bracket and campaign.side == ai_dir:
            logger.info(
                "[GUARD] Ignoring new %s entry: active %s campaign already exists (parent=%s)",
                decision.action, ai_dir, campaign.parent_order_id,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "active campaign"),
                ExecutionOutcomeType.BLOCKED_EXISTING,
                "active campaign",
            )

        per_share_risk = abs(decision.entry_price - decision.stop_loss)
        if per_share_risk <= 0:
            logger.warning("Invalid per-share risk; refusing to place %s bracket.", symbol)
            return self._respond(
                ExecutionResult(ExecutionStatus.ERROR, decision.symbol, "invalid per-share risk"),
                ExecutionOutcomeType.ERROR,
                "invalid per-share risk",
            )

        return None  # All guards passed

    def _validate_state_guards(
        self,
        decision: AITradeDecision,
        symbol: str,
        metadata: SymbolMetadata,
        ai_dir: str,
        state: dict,
        campaign: object,
    ) -> tuple[ExecutionResult, ExecutionOutcome] | None:
        """State-dependent guards that run after ``_fetch_symbol_state()``.

        Returns ``None`` when all guards pass, otherwise returns the
        rejection ``(ExecutionResult, ExecutionOutcome)`` tuple.
        """
        if decision.action == "scale_in":
            max_adds = int(getattr(self.runtime, "max_scale_ins_per_leg", 2))
            if max_adds <= 0:
                logger.info("[GUARD] Suppressing scale_in: disabled by max_scale_ins_per_leg=%s", max_adds)
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "scale_in disabled"),
                    ExecutionOutcomeType.BLOCKED_GUARD,
                    "scale_in disabled",
                )
            current_adds = int(self._scale_in_counts.get(symbol.upper(), 0))
            if current_adds >= max_adds:
                logger.info(
                    "[GUARD] Suppressing scale_in: max adds reached (%s/%s) for %s",
                    current_adds, max_adds, symbol,
                )
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "max scale_in reached"),
                    ExecutionOutcomeType.BLOCKED_GUARD,
                    "max scale_in reached",
                )
            opposite_dir = "short" if ai_dir == "long" else "long"
            if state["open_parent_shares"].get(opposite_dir):
                logger.info(
                    "[GUARD] Suppressing scale_in: open orders exist in opposite direction (side=%s, open_%s=%s)",
                    ai_dir, opposite_dir, state["open_parent_shares"].get(opposite_dir),
                )
                return self._respond(
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "open opposite orders"),
                    ExecutionOutcomeType.BLOCKED_EXISTING,
                    "open opposite orders",
                )

        if campaign.has_position and not campaign.has_bracket:
            if decision.stop_loss is not None and decision.take_profit is not None:
                self._rebuild_bracket_for_existing(campaign, decision)
                return self._respond(
                    ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "rebuild protection"),
                    ExecutionOutcomeType.SUCCESS_SUBMITTED,
                    "rebuild protection",
                )
            else:
                self._ensure_emergency_stop()

        if self._has_active_orders_or_position(symbol, state) and decision.action != "scale_in":
            detail_parts: list[str] = []
            if abs(state.get("position_shares", 0)) > 0:
                detail_parts.append(f"position_size={state['position_shares']}")
            working_count = state.get("working_orders", 0)
            if working_count:
                statuses = "/".join(state.get("working_order_statuses", []))
                detail_parts.append(
                    f"workingOrders={working_count} statuses={statuses or 'unknown'}"
                )
            if state.get("synthetic_stop_armed"):
                detail_parts.append("synthetic_stop=armed")
            detail = "; ".join(detail_parts) if detail_parts else "existing orders/position"
            logger.info(
                "[BLOCKED] Existing position or working orders for %s; skipping new entry (%s).",
                symbol, detail,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "existing orders/position"),
                ExecutionOutcomeType.BLOCKED_EXISTING,
                detail,
            )

        margin_blocked, margin_reason = self._check_margin_guard(symbol, metadata, decision)
        if margin_blocked:
            reason = margin_reason or "insufficient equity for margin-sensitive entry"
            return self._respond(
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "margin guard triggered"),
                ExecutionOutcomeType.BLOCKED_INSUFFICIENT_EQUITY,
                reason,
            )

        return None  # All state guards passed

    def _submit_bracket_order(
        self,
        decision: AITradeDecision,
        symbol: str,
        metadata: SymbolMetadata,
        ai_dir: str,
        per_share_risk: float,
        preparation: EntryPreparation,
        campaign: object,
    ) -> tuple[ExecutionResult, ExecutionOutcome]:
        """Place bracket order and handle post-trade bookkeeping."""
        tif = "GTC"
        self._last_bracket_orders = []
        try:
            if campaign.has_position and not campaign.has_bracket and campaign.side == ai_dir:
                qty = abs(campaign.position_size)
                self._place_protection_orders(
                    symbol=symbol,
                    direction=ai_dir,
                    quantity=qty,
                    take_profit=decision.take_profit,
                    stop_loss=decision.stop_loss,
                    tif=tif,
                )
                logger.info(
                    "[STATE] %s protection: side=%s sl=%.4f tp=%.4f emergency=%s size=%.2f",
                    symbol, "SELL" if ai_dir == "long" else "BUY",
                    decision.stop_loss, decision.take_profit,
                    "active" if self.runtime.emergency_stop_pct > 0 else "none",
                    qty,
                )
                return ExecutionResult(
                    ExecutionStatus.EXECUTED, decision.symbol, "reprotected existing",
                )

            orders_sent = self._place_entry_bracket(
                symbol=symbol,
                direction=ai_dir,
                quantity=preparation.candidate,
                entry_price=decision.entry_price,
                take_profit=decision.take_profit,
                stop_loss=decision.stop_loss,
                metadata=metadata,
                tif=tif,
            )
            logger.info(
                "IBKR %s bracket sent: %s | shares=%s | per-share-risk=%.4f | open-risk=%.2f | max-risk=$%.2f",
                symbol, decision.summary(), preparation.candidate,
                per_share_risk, preparation.open_risk, preparation.max_risk_dollars,
            )
            logger.info(
                "[STATE] %s protection: side=%s sl=%.4f tp=%.4f emergency=%s size=%.2f",
                symbol, "SELL" if ai_dir == "long" else "BUY",
                decision.stop_loss, decision.take_profit,
                "active" if self.runtime.emergency_stop_pct > 0 else "none",
                preparation.candidate,
            )
            self._record_equity_entry(symbol)
        except StopOrderUnsupportedError as exc:  # pragma: no cover
            logger.warning(
                "[GUARD] %s; config allows local stops? runtime.allow_local_stops=%s local_stop_symbols=%s",
                exc, self.runtime.allow_local_stops, self.runtime.local_stop_symbols,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG, decision.symbol, str(exc)),
                ExecutionOutcomeType.BLOCKED_GUARD,
                str(exc),
            )
        except Exception as exc:  # pragma: no cover
            logger.error(
                "Failed to place %s bracket (qty=%.4f entry=%.4f tp=%.4f sl=%.4f): %s",
                symbol, preparation.candidate, decision.entry_price,
                decision.take_profit, decision.stop_loss, exc,
            )
            return self._respond(
                ExecutionResult(ExecutionStatus.ERROR, decision.symbol, f"execution failed: {exc}"),
                ExecutionOutcomeType.ERROR, "execution failed", detail=str(exc),
            )

        response = self._respond(
            ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "bracket placed"),
            ExecutionOutcomeType.SUCCESS_SUBMITTED, "bracket placed",
            order_ids=[o.orderId for o in getattr(self, "_last_bracket_orders", []) if getattr(o, "orderId", None)],
        )
        # Increment counters for pyramiding/scaling in
        if decision.action in {"scale_in", "add_to_position"}:
            symbol_key = symbol.upper()
            self._scale_in_counts[symbol_key] = int(self._scale_in_counts.get(symbol_key, 0)) + 1
            if symbol_key not in self._position_metadata:
                self._position_metadata[symbol_key] = {"htf_neutral_bars": 0, "pyramid_count": 1}
            self._position_metadata[symbol_key]["pyramid_count"] = (
                self._position_metadata[symbol_key].get("pyramid_count", 1) + 1
            )
        return response

    def _enter_position_for_symbol(
        self,
        decision: AITradeDecision,
        *,
        allow_opposite_entry: bool = False,
    ) -> tuple[ExecutionResult, ExecutionOutcome]:
        """Fires a bracket order sized to ~$3 risk and max 5 shares for the configured symbol."""
        # ── Pre-entry validation ──
        rejection = self._validate_entry_guards(decision, allow_opposite_entry)
        if rejection is not None:
            return rejection

        symbol = self._symbol
        metadata = SYMBOL_METADATA.get(symbol)
        campaign = self._campaign_state(symbol)
        ai_dir = "long" if decision.action in {"enter_long"} else "short"
        if decision.action == "scale_in" and campaign.has_position:
            ai_dir = "long" if campaign.position_size > 0 else "short"
        per_share_risk = abs(decision.entry_price - decision.stop_loss)

        state = self._fetch_symbol_state(symbol)
        # ── State-dependent guards (scale-in, bracket rebuild, margin) ──
        rejection = self._validate_state_guards(
            decision=decision, symbol=symbol, metadata=metadata,
            ai_dir=ai_dir, state=state, campaign=campaign,
        )
        if rejection is not None:
            return rejection

        preparation, guard_result = self._prepare_entry(
            symbol=symbol,
            metadata=metadata,
            decision=decision,
            ai_dir=ai_dir,
            state=state,
            per_share_risk=per_share_risk,
            campaign=campaign,
        )
        if guard_result:
            return self._respond(
                guard_result,
                ExecutionOutcomeType.BLOCKED_GUARD,
                guard_result.reason or "risk guard",
            )

        # ── Submit order ──
        return self._submit_bracket_order(
            decision=decision, symbol=symbol, metadata=metadata,
            ai_dir=ai_dir, per_share_risk=per_share_risk,
            preparation=preparation, campaign=campaign,
        )

    def _portfolio_open_bracket_risk(self) -> float:
        """Best-effort estimate of total open bracket risk across all symbols with open trades/positions."""
        if not self.ib:
            return 0.0
        symbols: set[str] = set()
        try:
            symbols.update(self.list_open_position_symbols())
        except Exception as e:
            logger.error(f"Failed to list open position symbols: {e}")
            pass
        try:
            for trade in self.ib.openTrades():
                contract = getattr(trade, "contract", None)
                canonical = self._canonical_symbol_for_contract(contract)
                if canonical:
                    symbols.add(str(canonical).upper())
                    continue
                sym = getattr(contract, "symbol", None)
                if sym:
                    symbols.add(str(sym).upper())
        except Exception as e:
            logger.error(f"Failed to get symbols from open trades: {e}")
            pass
        if self._allowed_symbols:
            symbols = {s for s in symbols if s in self._allowed_symbols}
        total = 0.0
        for sym in sorted(symbols):
            try:
                st = self._fetch_symbol_state(sym)
                total += float(st.get("open_bracket_risk", 0.0) or 0.0)
            except Exception as e:
                logger.error(f"Failed to fetch symbol state for {sym}: {e}")
                continue
        return float(total)

    def _prepare_entry(
        self,
        symbol: str,
        metadata: SymbolMetadata,
        decision: AITradeDecision,
        ai_dir: str,
        state: dict,
        per_share_risk: float,
        campaign: object,
    ) -> tuple[EntryPreparation | None, ExecutionResult | None]:
        aggressive_mode = bool(self.profile_settings and self.profile_settings.icc_aggressive_mode)
        max_risk_dollars = float(getattr(self.settings, "max_dollar_risk_per_symbol", 3.0))
        fixed_risk = float(
            getattr(self.profile_settings, "risk_per_trade_dollars", 0.0) or 0.0
        )
        risk_pct = 0.0
        if aggressive_mode:
            net_liq = self.get_net_liquidation()
            if net_liq is None or net_liq <= 0:
                logger.info("[GUARD] Aggressive mode blocked: net liquidation unavailable.")
                return None, ExecutionResult(
                    ExecutionStatus.RISK_SUPPRESSED,
                    decision.symbol,
                    "net liquidation unavailable",
                )
            risk_pct = decision.risk_per_trade_pct
            if risk_pct is None:
                risk_pct = float(getattr(self.profile_settings, "aggressive_risk_per_trade_pct", 0.0) or 0.0)
            risk_pct = max(0.0, min(float(risk_pct), 1.0))
            
            # Per-Slice Risk Redesign:
            # max_risk_dollars is the TOTAL symbol cap (e.g. 6% * 5 = 30%)
            max_pyramid = int(getattr(self.profile_settings, "max_pyramid_entries", 1) or 1)
            base_slice_risk = fixed_risk if fixed_risk > 0 else net_liq * risk_pct
            max_risk_dollars = base_slice_risk * max_pyramid
        elif fixed_risk > 0:
            max_risk_dollars = fixed_risk
            
            start_net = self._daily_risk_state.get("start_net_liq") or net_liq
            max_daily_loss_pct = float(getattr(self.profile_settings, "max_daily_loss_pct", 0.0) or 0.0)
            if max_daily_loss_pct > 0 and net_liq < start_net * (1 - max_daily_loss_pct):
                logger.info(
                    "[GUARD] Aggressive mode blocked: daily loss cap hit (start=%.2f net_liq=%.2f cap=%.2f%%)",
                    start_net,
                    net_liq,
                    max_daily_loss_pct * 100,
                )
                return None, ExecutionResult(
                    ExecutionStatus.RISK_SUPPRESSED,
                    decision.symbol,
                    "daily loss cap hit",
                )
            max_losses = int(getattr(self.profile_settings, "max_consecutive_losses", 0) or 0)
            losses = int(self._daily_risk_state.get("consecutive_losses", 0) or 0)
            if max_losses > 0 and losses >= max_losses:
                logger.info(
                    "[GUARD] Aggressive mode blocked: consecutive loss cap hit (losses=%s cap=%s)",
                    losses,
                    max_losses,
                )
                return None, ExecutionResult(
                    ExecutionStatus.RISK_SUPPRESSED,
                    decision.symbol,
                    "consecutive loss cap hit",
                )
        max_shares_cap = float(getattr(self.settings, "max_shares_per_symbol", 5))
        open_risk = state["open_bracket_risk"]
        remaining_risk = max_risk_dollars - open_risk
        if remaining_risk <= 0:
            logger.info(
                "[GUARD] Skipped new %s entry: symbol risk cap reached (open risk=%.2f, max=%.2f)",
                symbol,
                open_risk,
                max_risk_dollars,
            )
            return None, ExecutionResult(
                ExecutionStatus.RISK_SUPPRESSED,
                decision.symbol,
                "risk cap reached",
            )

        max_account = getattr(self.settings, "max_dollar_risk_per_account", None)
        if aggressive_mode:
            net_liq = self.get_net_liquidation()
            exposure_pct = float(getattr(self.profile_settings, "max_exposure_pct", 0.0) or 0.0)
            if net_liq and exposure_pct > 0:
                max_account = net_liq * exposure_pct
        if max_account is not None:
            try:
                max_account_f = float(max_account)
            except Exception:
                max_account_f = 0.0
            if max_account_f > 0:
                account_open_risk = self._portfolio_open_bracket_risk()
                remaining_account = max_account_f - account_open_risk
                if remaining_account <= 0:
                    logger.info(
                        "[GUARD] Skipped new %s entry: account risk cap reached (open risk=%.2f, max=%.2f)",
                        symbol,
                        account_open_risk,
                        max_account_f,
                    )
                    return None, ExecutionResult(
                        ExecutionStatus.RISK_SUPPRESSED,
                        decision.symbol,
                        "account risk cap reached",
                    )
                remaining_risk = min(remaining_risk, remaining_account)

        same_dir_pos = state["position_shares"] if state["direction"] == ai_dir else 0
        open_same_dir = state["open_parent_shares"].get(ai_dir, 0)
        shares_cap = max(max_shares_cap - (same_dir_pos + open_same_dir), 0.0)
        
        # Each entry (slice) is capped at fixed or pct-based risk.
        # But we can't exceed the remaining_risk cap (TOTAL symbol cap).
        if aggressive_mode:
            if fixed_risk > 0:
                slice_risk = min(remaining_risk, fixed_risk)
            else:
                slice_risk = min(remaining_risk, net_liq * risk_pct) if risk_pct > 0 else remaining_risk
        else:
            slice_risk = remaining_risk
        
        # JPY/CAD/CHF Sizing Fix
        # For USD-base pairs (USDJPY), per_share_risk is in Quote Ccy (JPY).
        # We must convert it to Account Ccy (USD) to compare with slice_risk (USD).
        risk_norm = per_share_risk
        if metadata.asset_class == AssetClass.FOREX and symbol.startswith("USD") and decision.entry_price:
             risk_norm = per_share_risk / decision.entry_price
        
        units_by_risk = slice_risk / risk_norm
        allows_fractional = self._allows_fractional_for_asset_class(metadata.asset_class)
        if allows_fractional:
            candidate = max(0.0, min(units_by_risk, shares_cap))
        else:
            candidate = max(0, min(int(units_by_risk), int(shares_cap)))
        if self._requires_integer_qty(symbol, metadata):
            candidate = self._round_quantity_to_int(candidate)
        if candidate <= 0 or (not allows_fractional and candidate < 1):
            logger.info(
                "[GUARD] Suppressed %s entry: candidate_shares=%s (remaining_risk=%.2f, per_share_risk=%.4f, cap=%s)",
                symbol,
                candidate,
                remaining_risk,
                per_share_risk,
                shares_cap,
            )
            return None, ExecutionResult(
                ExecutionStatus.RISK_SUPPRESSED,
                decision.symbol,
                "candidate shares zero",
            )
        fractional_reason: str | None = None
        if self._should_apply_crypto_fractional(metadata) and decision.entry_price:
            candidate, fractional_reason = self._apply_crypto_fractional_symbol(
                symbol,
                candidate,
                decision.entry_price,
            )
            if fractional_reason:
                return None, ExecutionResult(
                    ExecutionStatus.RISK_SUPPRESSED,
                    decision.symbol,
                    fractional_reason,
                )

        margin_guard = self._guard_buying_power(
            symbol,
            candidate,
            decision.entry_price,
            risk_budget=remaining_risk,
            per_share_risk=per_share_risk,
        )
        if margin_guard:
            return None, margin_guard

        return (
            EntryPreparation(
                candidate=candidate,
                ai_dir=ai_dir,
                campaign=campaign,
                state=state,
                per_share_risk=per_share_risk,
                open_risk=open_risk,
                max_risk_dollars=max_risk_dollars,
                shares_cap=shares_cap,
            ),
            None,
        )

    def _allows_fractional_for_asset_class(self, asset_class: AssetClass) -> bool:
        """Determines if the asset class allows fractional quantities."""
        return asset_class in {AssetClass.CRYPTO, AssetClass.FOREX}

    def _allows_fractional(self, symbol: str) -> bool:
        """Indicates whether the given symbol supports fractional quantity sizing."""
        metadata = SYMBOL_METADATA.get(symbol.upper())
        if not metadata:
            return False
        return self._allows_fractional_for_asset_class(metadata.asset_class)

    def _should_apply_crypto_fractional(self, metadata: SymbolMetadata) -> bool:
        if not self.profile_settings or metadata.asset_class != AssetClass.CRYPTO:
            return False
        return bool(self.profile_settings.crypto_fractional_enabled)

    def _crypto_qty_step_for_symbol(self, symbol: str) -> float:
        if self.profile_settings and self.profile_settings.crypto_qty_steps:
            step = self.profile_settings.crypto_qty_steps.get(symbol.upper())
            if step:
                return step
        return DEFAULT_CRYPTO_QTY_STEPS.get(symbol.upper(), 0.0)

    @staticmethod
    def _round_quantity_to_int(qty: float) -> float:
        return float(max(1, int(qty)))

    @staticmethod
    def _requires_integer_qty(symbol: str, metadata: SymbolMetadata | None) -> bool:
        if not metadata:
            return False
        sym = symbol.upper()
        return metadata.asset_class == AssetClass.FOREX and sym.startswith(("XAU", "XAG", "XPT", "XPD"))

    def _apply_crypto_fractional_symbol(
        self, symbol: str, qty: float, entry_price: float
    ) -> tuple[float, str | None]:
        step = self._crypto_qty_step_for_symbol(symbol)
        if step <= 0:
            return qty, None
        max_notional = self.profile_settings.crypto_max_notional_usd if self.profile_settings else None
        min_notional = self.profile_settings.crypto_min_notional_usd if self.profile_settings else 0.0
        raw_notional = qty * entry_price
        if max_notional and raw_notional > max_notional:
            raw_notional = max_notional
            qty = raw_notional / entry_price
        qty_raw = qty
        qty_rounded = math.floor(qty_raw / step) * step
        if qty_rounded <= 0:
            reason = "crypto_qty_step_constraint"
            logger.info(
                "[CRYPTO][GUARD] blocked symbol=%s reason=%s step=%s qty_raw=%s",
                symbol,
                reason,
                step,
                qty_raw,
            )
            return 0.0, reason
        final_notional = qty_rounded * entry_price
        if final_notional < min_notional:
            reason = "crypto_min_notional_unmet"
            logger.info(
                "[CRYPTO][GUARD] blocked symbol=%s reason=%s min=%.2f actual=%.2f",
                symbol,
                reason,
                min_notional,
                final_notional,
            )
            return 0.0, reason
        logger.info(
            "[CRYPTO] fractional sizing symbol=%s price=%.4f notional_target=%.2f qty_raw=%.6f qty_rounded=%.6f step=%.6f",
            symbol,
            entry_price,
            raw_notional,
            qty_raw,
            qty_rounded,
            step,
        )
        return round(qty_rounded, 8), None

    def _register_synthetic_stop(
        self,
        symbol: str,
        direction: str,
        stop_price: float,
        tp_price: float | None,
        size: float,
        entry_order: Any | None,
        tp_order: Any | None,
    ) -> None:
        symbol_key = symbol.upper()
        stop = SyntheticStop(
            symbol=symbol_key,
            direction=direction,
            stop_price=stop_price,
            tp_price=tp_price,
            size=size,
            entry_order=entry_order,
            tp_order=tp_order,
            state="armed",
            created_at=datetime.now(ZoneInfo("UTC")),
        )
        self._synthetic_stops[symbol_key] = stop
        logger.info(
            "[CRYPTO] Synthetic stop armed for %s: side=%s size=%.2f stop=%.4f tp=%s parent=%s",
            symbol_key,
            direction,
            size,
            stop_price,
            f"{tp_price:.4f}" if tp_price is not None else "n/a",
            getattr(entry_order, "orderId", "unknown") if entry_order is not None else "none",
        )
        self._persist_stop_record(symbol_key, stop, "ARMED")

    def _persist_stop_record(self, symbol: str, stop: SyntheticStop, status: str) -> None:
        if not self._stop_store:
            return
        record = SyntheticStopRecord(
            symbol=symbol,
            side=stop.direction,
            size=abs(stop.size),
            stop_price=stop.stop_price,
            tp_price=stop.tp_price,
            parent_order_id=getattr(stop.entry_order, "orderId", None),
            tp_order_ids=[getattr(stop.tp_order, "orderId", None)]
            if stop.tp_order
            else None,
            status=status,
            timestamp=datetime.now(ZoneInfo("UTC")).isoformat(),
        )
        self._stop_store.upsert(record)
        logger.info(
            "[CRYPTO][PERSIST] wrote stop store path=%s count=%s",
            self._stop_store.path,
            len(self._stop_store.records),
        )

    def _clear_stop_record(self, symbol: str) -> None:
        if not self._stop_store:
            return
        self._stop_store.remove(symbol)
        logger.info("[CRYPTO][PERSIST] removed stop record for %s", symbol)

    def _mark_stop_stale(self, symbol: str) -> None:
        stop = self._synthetic_stops.get(symbol)
        if stop:
            stop.state = "stale"
        if self._stop_store and symbol in self._stop_store.records:
            record = self._stop_store.records[symbol]
            record.status = "STALE"
            record.timestamp = datetime.now(ZoneInfo("UTC")).isoformat()
            self._stop_store.upsert(record)
            logger.info(
                "[CRYPTO][PERSIST] marked stale stop for %s path=%s",
                symbol,
                self._stop_store.path,
            )

    def _rearm_stop_from_record(self, symbol: str, record: SyntheticStopRecord, pos) -> None:
        size = abs(pos.position)
        direction = record.side
        stop = SyntheticStop(
            symbol=symbol,
            direction=direction,
            stop_price=record.stop_price,
            tp_price=record.tp_price,
            size=size,
            entry_order=None,
            tp_order=None,
            state="armed",
            created_at=datetime.now(ZoneInfo("UTC")),
        )
        self._synthetic_stops[symbol] = stop
        if abs(record.size - size) > 1e-6:
            record.size = size
            record.timestamp = datetime.now(ZoneInfo("UTC")).isoformat()
        self._persist_stop_record(symbol, stop, "ARMED")
        logger.info(
            "[CRYPTO][STARTUP] re-armed synthetic stop for %s size=%.2f stop=%.4f tp=%s",
            symbol,
            size,
            record.stop_price,
            record.tp_price,
        )

    def _fetch_last_price(self, symbol: str, provider, timeframe: str) -> float | None:
        if not provider:
            return None
        try:
            snapshot = provider.get_latest_snapshot(symbol, timeframe)
        except Exception as e:
            logger.error(f"Failed to fetch last price for {symbol}: {e}")
            return None
        candles = getattr(snapshot, "candles", None)
        if candles:
            return candles[-1].close
        return getattr(snapshot, "close", None) or getattr(snapshot, "last", None)

    def _rearm_missing_stop(
        self, symbol: str, position: float, provider, timeframe: str
    ) -> None:
        if not self.profile_settings:
            return
        price = self._fetch_last_price(symbol, provider, timeframe)
        if price is None:
            logger.warning(
                "[CRYPTO][SAFETY] cannot re-arm %s; no price snapshot", symbol
            )
            return
        direction = "long" if position > 0 else "short"
        pct = self.profile_settings.rearm_stop_distance_pct
        stop_price = price * (1 - pct) if direction == "long" else price * (1 + pct)
        stop = SyntheticStop(
            symbol=symbol,
            direction=direction,
            stop_price=stop_price,
            tp_price=None,
            size=abs(position),
            entry_order=None,
            tp_order=None,
            state="armed",
            created_at=datetime.now(ZoneInfo("UTC")),
        )
        self._synthetic_stops[symbol] = stop
        self._persist_stop_record(symbol, stop, "ARMED")
        logger.info(
            "[CRYPTO][STARTUP] re-armed synthetic stop for %s (policy=REARM stop=%.4f)",
            symbol,
            stop_price,
        )

    def _force_flatten(self, symbol: str, side: str, policy: str) -> None:
        if self.ib:
            self.cancel_all_orders_for_symbol(symbol)
            self._flatten_symbol(symbol)
        self._clear_synthetic_stop(symbol)
        logger.info(
            "[CRYPTO][SAFETY] naked ZEROHASH %s (%s) flattened (policy=%s)",
            symbol,
            side,
            policy,
        )

    def _handle_naked_position(
        self,
        symbol: str,
        position: float,
        provider,
        timeframe: str,
        policy: str,
    ) -> None:
        side = "long" if position > 0 else "short"
        policy = policy.upper()
        if policy == "FLATTEN":
            self._force_flatten(symbol, side, policy)
        elif policy == "PAUSE":
            self._paused_symbols.add(symbol)
            logger.info(
                "[CRYPTO][SAFETY] naked ZEROHASH %s (%s) paused (policy=PAUSE)",
                symbol,
                side,
            )
        elif policy == "REARM":
            self._rearm_missing_stop(symbol, position, provider, timeframe)
        else:
            logger.info(
                "[CRYPTO][SAFETY] naked ZEROHASH %s (%s) ignored (policy=%s)",
                symbol,
                side,
                policy,
            )

    def _effective_startup_crypto_unprotected_policy(self) -> str:
        """
        Profile-level default can be overridden at runtime via env var.

        This is intentionally separate from profile YAML to keep the safety policy explicit in LIVE runs.
        """
        override = (os.getenv("STARTUP_CRYPTO_UNPROTECTED_POLICY") or "").strip()
        if override:
            return override.upper()
        if not self.profile_settings:
            return "FLATTEN"
        return str(self.profile_settings.startup_crypto_unprotected_policy).upper()

    def reconcile_synthetic_stops(self, provider, timeframe: str) -> None:
        if (
            not self.profile_settings
            or not self.profile_settings.synthetic_stop_persistence_enabled
            or not self._stop_store
            or not self.ib
        ):
            return
        positions: dict[str, Any] = {}
        for pos in self.ib.positions():
            canonical = self._canonical_symbol_for_contract(pos.contract)
            if not canonical or not self._is_zero_hash_symbol(canonical) or abs(pos.position) <= 0:
                continue
            positions[canonical] = pos
        orders = self.ib.openOrders()
        order_map: dict[str, list[Any]] = defaultdict(list)
        for order in orders:
            canonical = self._canonical_symbol_for_contract(order.contract)
            if not canonical or not self._is_zero_hash_symbol(canonical):
                continue
            order_map[canonical].append(order)
        stats = {
            "loaded": len(self._stop_store.records),
            "rearmed": 0,
            "cleared": 0,
            "flattened": 0,
            "paused": 0,
            "ignored": 0,
        }
        for symbol in self._zero_hash_symbols:
            record = self._stop_store.records.get(symbol)
            pos = positions.get(symbol)
            if record and pos:
                self._rearm_stop_from_record(symbol, record, pos)
                stats["rearmed"] += 1
            elif record and not pos:
                self._mark_stop_stale(symbol)
                self._clear_synthetic_stop(symbol)
                stats["cleared"] += 1
                logger.info(
                    "[CRYPTO][STARTUP] cleared stale synthetic stop for %s (no live position)",
                    symbol,
                )
            elif pos and not record:
                policy = self._effective_startup_crypto_unprotected_policy()
                self._handle_naked_position(symbol, pos.position, provider, timeframe, policy)
                if policy == "FLATTEN":
                    stats["flattened"] += 1
                elif policy == "PAUSE":
                    stats["paused"] += 1
                elif policy == "REARM":
                    stats["rearmed"] += 1
                else:
                    stats["ignored"] += 1
        logger.info(
            "[CRYPTO][STARTUP] synthetic-stop reconciliation summary "
            "loaded=%s rearmed=%s cleared=%s flattened=%s paused=%s ignored=%s",
            stats["loaded"],
            stats["rearmed"],
            stats["cleared"],
            stats["flattened"],
            stats["paused"],
            stats["ignored"],
        )

    def _clear_synthetic_stop(self, symbol: str) -> None:
        symbol = symbol.upper()
        self._synthetic_stops.pop(symbol, None)
        self._paused_symbols.discard(symbol)
        self._clear_stop_record(symbol)

    def evaluate_synthetic_stops(self, provider, timeframe: str) -> list[ExecutionResult]:
        """Monitors last sale price against armed stops; triggers market exits on breach."""
        if not self.ib or not provider:
            return []
        return self.stop_manager.evaluate_all(
            provider,
            get_last_price_fn=lambda s: self.get_last_price(s),
            trigger_cb=self._on_synthetic_trigger
        )

    def _on_synthetic_trigger(self, stop: SyntheticStop, price: float, trigger_type: str) -> Optional[ExecutionResult]:
        if trigger_type == "TP":
            return self._trigger_synthetic_take_profit(stop, price)
        return self._trigger_synthetic_stop(stop, price)

    def _trigger_synthetic_take_profit(self, stop: SyntheticStop, last_price: float) -> ExecutionResult | None:
        symbol = stop.symbol
        try:
            from ib_insync import MarketOrder
            self.cancel_all_orders_for_symbol(symbol)
            action = "SELL" if stop.direction == "long" else "BUY"
            order = MarketOrder(action=action, totalQuantity=stop.size)
            self._set_order_ref(order, symbol, "SYN_TP")
            self.ib.placeOrder(self._contract_for_symbol(symbol), order)
            logger.info("[CRYPTO] Synthetic TP TRIGGERED for %s at %.4f", symbol, last_price)
            self._record_equity_exit(symbol)
            return ExecutionResult(ExecutionStatus.EXECUTED, symbol, "synthetic take-profit triggered")
        except Exception as exc:
            logger.error("[CRYPTO] Synthetic TP failed for %s: %s", symbol, exc)
            return ExecutionResult(ExecutionStatus.ERROR, symbol, f"synthetic take-profit failed: {exc}")

    def _trigger_synthetic_stop(self, stop: SyntheticStop, last_price: float) -> ExecutionResult | None:
        symbol = stop.symbol
        try:
            from ib_insync import MarketOrder
            self.cancel_all_orders_for_symbol(symbol)
            action = "SELL" if stop.direction == "long" else "BUY"
            order = MarketOrder(action=action, totalQuantity=stop.size)
            self._set_order_ref(order, symbol, "SYN_SL")
            self.ib.placeOrder(self._contract_for_symbol(symbol), order)
            logger.warning("[CRYPTO] Synthetic stop TRIGGERED for %s at %.4f", symbol, last_price)
            self._record_equity_exit(symbol)
            return ExecutionResult(ExecutionStatus.EXECUTED, symbol, "synthetic stop triggered")
        except Exception as exc:
            logger.error("[CRYPTO] Synthetic stop failed for %s: %s", symbol, exc)
            return ExecutionResult(ExecutionStatus.ERROR, symbol, f"synthetic stop failed: {exc}")

    def _cancel_order(self, order: Any | None) -> None:
        if not order or not self.ib:
            return
        try:
            self.ib.cancelOrder(order)
        except Exception as exc:
            logger.debug("Failed to cancel order %s: %s", getattr(order, "orderId", order), exc)

    def _check_pdt_guard(self, symbol: str, metadata: SymbolMetadata) -> bool:
        return self.pdt_guard.check_pdt_guard(symbol, metadata)

    def _record_equity_entry(self, symbol: str) -> None:
        self.pdt_guard.record_equity_entry(symbol)

    def _record_equity_exit(self, symbol: str) -> None:
        self.pdt_guard.record_equity_exit(symbol)

    def _sync_position_holds_with_ib(self) -> None:
        if not self.ib:
            return
        now = datetime.now(timezone.utc)
        infer = bool(getattr(self.runtime, "infer_position_hold_from_executions", False))
        lookback_days = int(getattr(self.runtime, "infer_position_hold_lookback_days", 7) or 7)
        inferred_open_times: dict[str, datetime] = {}
        if infer:
            inferred_open_times = self._infer_position_open_times_from_executions(lookback_days, now)
        try:
            for pos in self.ib.positions():
                symbol = self._canonical_symbol_for_contract(getattr(pos, "contract", None)) or getattr(
                    getattr(pos, "contract", None), "symbol", None
                )
                if not symbol:
                    continue
                symbol = str(symbol).upper()
                if abs(pos.position) > 0 and not self._position_hold_store.get(symbol):
                    opened_at = inferred_open_times.get(symbol) or now
                    reason = "exec_history" if symbol in inferred_open_times else "no_exec_timestamp"
                    logger.info(
                        "[HOLD_GUARD][FALLBACK] symbol=%s opened_at=%s reason=%s",
                        symbol,
                        opened_at.isoformat(),
                        reason,
                    )
                    self._position_hold_store.upsert(symbol, opened_at)
        except Exception:
            logger.debug("Failed to sync position hold timestamps with IB positions")

    def _infer_position_open_times_from_executions(
        self,
        lookback_days: int,
        now: datetime,
    ) -> dict[str, datetime]:
        """Best-effort inference of position open timestamps using recent executions.

        IBKR positions do not include an "opened_at" timestamp. This method uses recent executions
        to estimate the most recent time a symbol transitioned from flat to non-flat.
        """
        if not self.ib:
            return {}
        try:
            from ib_insync import ExecutionFilter  # type: ignore
        except Exception as e:
            logger.error(f"Failed to import ExecutionFilter: {e}")
            return {}
        lookback_days = max(1, int(lookback_days or 1))
        since = (now - timedelta(days=lookback_days)).strftime("%Y%m%d %H:%M:%S")
        try:
            exec_filter = ExecutionFilter(time=since)
            fills = self.ib.reqExecutions(exec_filter)
        except Exception as e:
            logger.error(f"Failed to request executions: {e}")
            return {}
        if not fills:
            return {}

        # Current signed positions by canonical symbol.
        current_positions: dict[str, float] = {}
        for pos in self.ib.positions():
            symbol = self._canonical_symbol_for_contract(getattr(pos, "contract", None)) or getattr(
                getattr(pos, "contract", None), "symbol", None
            )
            if not symbol:
                continue
            symbol = str(symbol).upper()
            signed = float(getattr(pos, "position", 0) or 0)
            if abs(signed) < 1e-8:
                continue
            current_positions[symbol] = signed
        if not current_positions:
            return {}

        per_symbol: dict[str, list[tuple[datetime, float]]] = {}
        for fill in fills:
            contract = getattr(fill, "contract", None)
            symbol = self._canonical_symbol_for_contract(contract) or getattr(contract, "symbol", None)
            if not symbol:
                continue
            symbol = str(symbol).upper()
            if symbol not in current_positions:
                continue
            execution = getattr(fill, "execution", None) or getattr(fill, "execDetails", None)
            if not execution:
                continue
            exec_time = self._parse_execution_time(getattr(execution, "time", None))
            if not exec_time:
                continue
            side = (getattr(execution, "side", None) or getattr(execution, "action", None) or "").upper()
            qty = float(getattr(execution, "shares", None) or getattr(execution, "qty", None) or 0.0)
            if qty <= 0:
                continue
            signed_qty = qty if side == "BUY" else -qty if side == "SELL" else 0.0
            if signed_qty == 0.0:
                continue
            per_symbol.setdefault(symbol, []).append((exec_time, signed_qty))

        inferred: dict[str, datetime] = {}
        for symbol, signed_position in current_positions.items():
            records = per_symbol.get(symbol, [])
            if not records:
                continue
            records.sort(key=lambda item: item[0])
            net = 0.0
            last_open: datetime | None = None
            for t, q in records:
                prev = net
                net += q
                if abs(prev) < 1e-8 and abs(net) >= 1e-8:
                    last_open = t
            if last_open is None:
                continue
            # Only accept if the inferred direction matches current position direction.
            if signed_position > 0 and net <= 0:
                continue
            if signed_position < 0 and net >= 0:
                continue
            inferred[symbol] = last_open
        return inferred

    def _record_position_open(self, symbol: str, opened_at: datetime) -> None:
        self._position_hold_store.upsert(symbol, opened_at)

    def _on_exec_details(self, trade, fill) -> None:
        if not fill:
            return
        contract = getattr(fill, "contract", None)
        symbol = self._canonical_symbol_for_contract(contract)
        if not symbol:
            return
        if self._position_hold_store.get(symbol):
            return
        state = self._fetch_symbol_state(symbol)
        if abs(state.get("position_shares", 0)) == 0:
            return
        execution = getattr(fill, "execution", None)
        if not execution:
            execution = getattr(fill, "execDetails", None)
        exec_time = self._parse_execution_time(getattr(execution, "time", None))
        if not exec_time:
            return
        self._record_position_open(symbol, exec_time)
        logger.info(
            "[HOLD_GUARD] symbol=%s opened_at_utc=%s source=execDetails",
            symbol,
            exec_time.isoformat(),
        )

    def _parse_execution_time(self, raw_time: str | None) -> datetime | None:
        if not raw_time:
            return None
        formats = ("%Y%m%d  %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d-%H:%M:%S")
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw_time, fmt)
            except ValueError:
                continue
            return parsed.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(raw_time)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _clear_position_hold(self, symbol: str) -> None:
        self._position_hold_store.remove(symbol)

    def _position_hold_age_seconds(self, symbol: str) -> float | None:
        record = self._position_hold_store.get(symbol)
        if not record:
            return None
        try:
            opened = datetime.fromisoformat(record.opened_at)
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - opened).total_seconds()

    def _hold_guard_allows_exit(self, symbol: str, emergency: bool = False) -> tuple[bool, float | None]:
        metadata = SYMBOL_METADATA.get(symbol.upper())
        if metadata and metadata.asset_class == AssetClass.CRYPTO:
            return True, None
        if self.runtime.allow_day_trades:
            return True, None
        age = self._position_hold_age_seconds(symbol)
        if age is None:
            return True, None
        if age >= self.runtime.min_hold_seconds:
            return True, age
        return False, age

    def _can_place_take_profit(self, symbol: str) -> bool:
        allow, _ = self._hold_guard_allows_exit(symbol)
        return allow

    def refresh_account_summary(self) -> None:
        if not self.ib:
            return
        try:
            rows = self.ib.accountSummary()
        except Exception as exc:
            logger.warning("[ACCOUNT] Failed to refresh account summary: %s", exc)
            return
        summary: dict[str, float] = {}
        segments: dict[str, float] = {}
        for row in rows:
            tag = getattr(row, "tag", None)
            value = getattr(row, "value", None)
            if not tag or value is None:
                continue
            try:
                val_float = float(value)
                summary[tag] = val_float
                if "-" in tag:
                    segments[tag] = val_float
            except ValueError:
                continue
        self._account_summary = summary
        self._account_segments = segments
        self._last_account_summary = datetime.now(timezone.utc)
        net_liq = summary.get("NetLiquidation")
        if isinstance(net_liq, (int, float)):
            self._update_daily_risk_state(float(net_liq))

    def _update_daily_risk_state(self, net_liq: float) -> None:
        today = datetime.now(timezone.utc).date()
        state_date = self._daily_risk_state.get("date")
        if state_date != today:
            self._daily_risk_state.update(
                {
                    "date": today,
                    "start_net_liq": net_liq,
                    "last_net_liq": net_liq,
                    "consecutive_losses": 0,
                }
            )
            return
        last = self._daily_risk_state.get("last_net_liq")
        if isinstance(last, (int, float)):
            if net_liq < last:
                self._daily_risk_state["consecutive_losses"] = int(
                    self._daily_risk_state.get("consecutive_losses", 0)
                ) + 1
            elif net_liq > last:
                self._daily_risk_state["consecutive_losses"] = 0
        self._daily_risk_state["last_net_liq"] = net_liq

    def get_net_liquidation(self) -> float | None:
        return self._account_summary.get("NetLiquidation")

    def account_summary_age_seconds(self) -> float | None:
        if not self._last_account_summary:
            return None
        return (datetime.now(timezone.utc) - self._last_account_summary).total_seconds()

    def get_liquid_capital(self) -> float:
        """Alias for get_net_liquidation to satisfy runtime interface."""
        val = self.get_net_liquidation()
        return val if val is not None else 0.0

    def _check_margin_guard(
        self, symbol: str, metadata: SymbolMetadata, decision: AITradeDecision
    ) -> tuple[bool, str | None]:
        threshold = self.runtime.min_equity_for_margin
        if threshold <= 0:
            return False, None
        
        # Use segment-specific net liquidation if available
        # NetLiquidation-S: Securities (Equities, Forex)
        # NetLiquidation-C: Commodities (Futures)
        seg_tag = "NetLiquidation-C" if metadata.asset_class == AssetClass.FUTURE else "NetLiquidation-S"
        net_liq = self._account_segments.get(seg_tag, self.get_net_liquidation())
        
        if net_liq is None or net_liq >= threshold:
            return False, None
        
        reason = f"segment={seg_tag} liquid={net_liq:.2f} threshold={threshold:.2f}"
        fragile_asset = metadata.asset_class
        
        # Margin Guard now checks the specific segment.
        # If the user has sufficient Forex capital ($400) but low Futures ($0),
        # only Futures trades will be blocked.
        
        block_short = fragile_asset == AssetClass.EQUITY and decision.action == "enter_short"
        block_futures = fragile_asset == AssetClass.FUTURE
        block_forex = fragile_asset == AssetClass.FOREX # User says "no need to exempt if separated"
        
        if block_short or block_futures or block_forex:
            logger.warning(
                "[MARGIN_GUARD] %s; blocking trade for %s",
                reason,
                symbol,
            )
            return True, reason
            
        return False, None

    def should_block_for_hold(
        self,
        symbol: str,
        decision: AITradeDecision,
        open_position: dict | None,
    ) -> tuple[bool, str | None, float | None]:
        action = decision.action
        if action not in {"scale_out", "close_position"}:
            return False, None, None
        if not open_position or abs(open_position.get("size", 0)) == 0:
            return False, None, None
        allowed, age = self._hold_guard_allows_exit(symbol, decision.emergency_exit)
        if allowed:
            if decision.emergency_exit:
                logger.info(
                    "[HOLD_GUARD][EMERGENCY_EXIT] symbol=%s action=%s held_for=%.1f seconds",
                    symbol,
                    action,
                    age or 0.0,
                )
            return False, None, age
        remaining = self.runtime.min_hold_seconds - (age or 0.0)
        detail = f"held_for={age or 0.0:.1f} remaining={remaining:.1f}"
        logger.info(
            "[HOLD_GUARD] symbol=%s held_for=%.1f remaining=%.1f action=%s blocked",
            symbol,
            age or 0.0,
            remaining,
            action,
        )
        return True, detail, age

    def _has_active_orders_or_position(self, symbol: str, state: dict) -> bool:
        """True if we have a position OR open orders for this specific symbol.
        
        Note: If max_concurrent_positions > 1, we only return True if THIS symbol
        is already active. We rely on the loops to handle the total portfolio cap.
        """
        max_pos = int(self.profile_settings.max_concurrent_positions if self.profile_settings else 1)
        
        # If we are limited to 1 position, then ANY active position/order elsewhere blocks us.
        if max_pos <= 1:
            total_active = len(self.list_open_position_symbols())
            if total_active > 0:
                # But wait, if the one active position IS this symbol, we shouldn't block scale-ins
                # This is handled by the caller checking if action == "scale_in"
                # For a fresh entry, we block if total_active > 0.
                return True

        # If we have multi-slot capability, we only care if THIS symbol is busy.
        if abs(state.get("position_shares", 0)) > 1e-8:
            return True
        if state.get("working_orders", 0) > 0:
            return True
        if state.get("synthetic_stop_armed"):
            return True
        open_parents = state.get("open_parent_shares", {})
        return any(value > 0 for value in open_parents.values())

    def _supports_native_stop(self, symbol: str) -> bool:
        return self._native_stop_supported.get(symbol.upper(), True)

    def _allows_local_stop(self, symbol: str) -> bool:
        symbol_key = symbol.upper()
        if self.runtime.allow_local_stops:
            return True
        return symbol_key in self._local_stop_symbols

    def _record_local_stop(
        self,
        symbol: str,
        metadata: SymbolMetadata,
        stop_level: float,
        direction: str,
        entry_price: float | None,
    ) -> None:
        symbol_key = symbol.upper()
        if stop_level is None:
            return
        if not self._allows_local_stop(symbol_key):
            raise StopOrderUnsupportedError(symbol_key, metadata.exchange)
        self._native_stop_supported[symbol_key] = False
        self._local_stop_info[symbol_key] = {
            "stop_level": stop_level,
            "direction": direction,
            "entry_price": entry_price or 0.0,
            "exchange": metadata.exchange,
        }
        logger.info(
            "[STATE] %s using local_stop protection (%s does not support stop orders).",
            symbol_key,
            metadata.exchange,
        )

    def _clear_local_stop(self, symbol: str) -> None:
        self._local_stop_info.pop(symbol.upper(), None)

    def _is_stop_unsupported_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "unsupported order type" in text or "error 387" in text

    def _maybe_place_stop_order(
        self,
        symbol: str,
        metadata: SymbolMetadata,
        contract,
        stop_order,
        direction: str,
        stop_level: float | None,
        entry_price: float | None,
    ) -> bool:
        if stop_level is None:
            return False
        symbol_key = symbol.upper()
        if not self._supports_native_stop(symbol_key):
            self._record_local_stop(symbol_key, metadata, stop_level, direction, entry_price)
            return False
        try:
            self.ib.placeOrder(contract, stop_order)
            return True
        except Exception as exc:
            if self._is_stop_unsupported_error(exc):
                self._record_local_stop(symbol_key, metadata, stop_level, direction, entry_price)
                return False
            raise
        return True

    def enforce_local_stops(self, provider, timeframe: str) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        if not self.ib or not self._local_stop_info:
            return results
        for symbol, info in list(self._local_stop_info.items()):
            try:
                snapshot = provider.get_latest_snapshot(symbol, timeframe)
            except Exception as e:
                logger.error(f"Failed to get snapshot for {symbol} during local stop monitoring: {e}")
                continue
            if not snapshot.candles:
                continue
            last_price = snapshot.candles[-1].close
            if self._should_trigger_local_stop(info, last_price):
                result = self._execute_local_stop(symbol, info, last_price)
                if result:
                    results.append(result)
        return results

    def _should_trigger_local_stop(self, info: dict[str, Any], last_price: float) -> bool:
        direction = info.get("direction")
        stop_level = info.get("stop_level")
        if stop_level is None or direction not in {"long", "short"}:
            return False
        if direction == "long":
            return last_price <= stop_level
        return last_price >= stop_level

    def _execute_local_stop(self, symbol: str, info: dict[str, Any], last_price: float) -> ExecutionResult | None:
        if not self.ib:
            return None
        state = self._fetch_symbol_state(symbol)
        pos_size = state["position_shares"]
        if pos_size == 0:
            self._clear_local_stop(symbol)
            return None
        action = "SELL" if info.get("direction") == "long" else "BUY"
        try:
            from ib_insync import MarketOrder  # type: ignore
        except Exception as exc:  # pragma: no cover
            logger.error("ib_insync MarketOrder unavailable: %s", exc)
            return ExecutionResult(
                ExecutionStatus.ERROR,
                symbol,
                f"local stop market order unavailable: {exc}",
            )
        self.cancel_all_orders_for_symbol(symbol)
        contract = self._contract_for_symbol(symbol)
        metadata = SYMBOL_METADATA.get(symbol.upper())
        order = MarketOrder(action=action, totalQuantity=abs(pos_size))
        order.tif = self._effective_tif(
            metadata.asset_class if metadata else None,
            getattr(contract, "exchange", None),
            "GTC",
        )
        try:
            self.ib.placeOrder(contract, order)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to execute local stop for %s: %s", symbol, exc)
            return ExecutionResult(
                ExecutionStatus.ERROR,
                symbol,
                f"local stop failed: {exc}",
            )
        logger.info(
            "[EMERGENCY_FLATTEN] %s %s closed via local stop at %.4f (stop=%.4f size=%.2f)",
            symbol,
            "long" if info.get("direction") == "long" else "short",
            last_price,
            info.get("stop_level"),
            pos_size,
        )
        self._clear_local_stop(symbol)
        self._record_equity_exit(symbol)
        return ExecutionResult(
            ExecutionStatus.EXECUTED,
            symbol,
            "local stop triggered",
        )

    def _guard_buying_power(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        *,
        risk_budget: float | None = None,
        per_share_risk: float | None = None,
    ) -> ExecutionResult | None:
        """Verifies IB buying power for the requested symbol before sending brackets."""
        if not self.ib:
            return None
        acct = self.settings.account_id or ""
        try:
            summary = self.ib.accountSummary(acct)
        except Exception as exc:
            logger.warning(
                "[GUARD] Cannot read account summary for %s; aborting entry (%s)",
                symbol,
                exc,
            )
            return ExecutionResult(
                ExecutionStatus.ERROR,
                symbol,
                f"account summary failed: {exc}",
            )

        buying_power = None
        for entry in summary:
            tag = getattr(entry, "tag", None)
            value = getattr(entry, "value", None)
            if tag in {"BuyingPower", "AvailableFunds"} and value not in (None, ""):
                try:
                    buying_power = float(value)
                except (TypeError, ValueError):
                    continue
                break

        if buying_power is None:
            logger.warning(
                "[GUARD] Buying power unavailable for %s; cannot size entry",
                symbol,
            )
            return ExecutionResult(
                ExecutionStatus.ERROR,
                symbol,
                "buying power unavailable",
            )

        needed = quantity * entry_price
        if needed > buying_power:
            logger.info(
                "[GUARD] Risk suppressed %s entry: risk_budget=%.2f qty=%.4f per_share_risk=%.4f needs≈%.2f buying_power=%.2f",
                symbol,
                risk_budget or 0.0,
                quantity,
                per_share_risk or 0.0,
                needed,
                buying_power,
            )
            return ExecutionResult(
                ExecutionStatus.RISK_SUPPRESSED,
                symbol,
                "insufficient buying power",
            )
        return None
    def _scale_or_close_stock(
        self,
        decision: AITradeDecision,
        *,
        bypass_hold_guard: bool = False,
        bypass_pdt_exit: bool = False,
    ) -> tuple[ExecutionResult, ExecutionOutcome]:
        """Handles scale_out/close_position with real orders, not imaginary helpers."""
        if not self.ib:
            logger.info("Dry-run: would scale/close positions")
            return (
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "dry-run scale/close",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SKIPPED,
                    "dry-run scale/close",
                ),
            )
        try:
            from ib_insync import MarketOrder  # type: ignore
        except Exception as exc:  # pragma: no cover
            logger.error("ib_insync MarketOrder unavailable: %s", exc)
            return (
                ExecutionResult(
                    ExecutionStatus.ERROR,
                    decision.symbol,
                    f"market order unavailable: {exc}",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.ERROR,
                    "market order unavailable",
                    detail=str(exc),
                ),
            )

        pos_state = self._fetch_symbol_state(self._symbol)
        pos_size = pos_state["position_shares"]
        metadata = SYMBOL_METADATA.get(self._symbol.upper())
        is_equity = bool(metadata and metadata.asset_class == AssetClass.EQUITY)
        entry_day = self._pdt_entry_dates.get(self._symbol.upper())
        today = date.today()
        entry_open_today = entry_day == today
        guard_blocks_scale = self._pdt_guard_enabled and is_equity
        guard_blocks_close = guard_blocks_scale and entry_open_today
        emergency_exit = decision.emergency_exit

        if pos_size == 0:
            if decision.action == "scale_out":
                logger.info("[GUARD] Ignoring scale_out: no open position for %s", self._symbol)
            else:
                logger.info("[GUARD] No position to close for %s; skipping", self._symbol)
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "no open position",
                ),
                ExecutionOutcomeType.SKIPPED,
                "no open position",
            )

        if not bypass_hold_guard:
            hold_blocked, detail, age = self.should_block_for_hold(
                self._symbol,
                decision,
                {"size": pos_size},
            )
            if hold_blocked:
                return self._respond(
                    ExecutionResult(
                        ExecutionStatus.STAND_ASIDE,
                        decision.symbol,
                        "min-hold guard blocks exit",
                    ),
                    ExecutionOutcomeType.BLOCKED_MIN_HOLD,
                    detail or "min_hold_active",
                )

        if decision.action == "close_position":
            if guard_blocks_close and not bypass_pdt_exit:
                logger.info(
                    "[PDT][BLOCK] close_position blocked for %s (non-emergency)", self._symbol
                )
                return self._respond(
                    ExecutionResult(
                        ExecutionStatus.STAND_ASIDE,
                        decision.symbol,
                        "pdt guard blocks close_position",
                    ),
                    ExecutionOutcomeType.BLOCKED_PDT_EXIT,
                    "pdt_guard_close_block",
            )
            self._flatten_symbol(self._symbol)
            return (
                ExecutionResult(
                    ExecutionStatus.EXECUTED,
                    decision.symbol,
                    "flattened position",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SUCCESS_SUBMITTED,
                    "flattened position",
                ),
            )

        if decision.action != "scale_out":  # pragma: no cover - defensive
            logger.info("No execution for action %s", decision.action)
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "no execution path",
                ),
                ExecutionOutcomeType.SKIPPED,
                "no execution path",
            )

        fraction = float(getattr(self.runtime, "scale_out_fraction", 0.5))
        min_scale = float(getattr(self.runtime, "min_position_size_to_scale", 1.0))
        if guard_blocks_scale and not emergency_exit:
            logger.info(
                "[PDT][BLOCK] scale_out blocked for %s (pdt guard enabled)", self._symbol
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "pdt guard blocks scale_out",
                ),
                ExecutionOutcomeType.BLOCKED_PDT_EXIT,
                "pdt_guard_scale_out",
            )
        if abs(pos_size) <= min_scale:
            if is_equity:
                logger.info(
                    "[PDT][BLOCK] scale_out skipped — size too small (%s, size=%.2f)",
                    self._symbol,
                    pos_size,
                )
                return self._respond(
                    ExecutionResult(
                        ExecutionStatus.STAND_ASIDE,
                        decision.symbol,
                        "scale_out size too small for equity",
                    ),
                    ExecutionOutcomeType.BLOCKED_PDT_EXIT,
                    "scale_out_size_too_small",
                )
            logger.info(
                "[GUARD] scale_out with tiny size; flattening remainder instead (%s, size=%.2f)",
                self._symbol,
                pos_size,
            )
            self._flatten_symbol(self._symbol)
            return (
                ExecutionResult(
                    ExecutionStatus.EXECUTED,
                    decision.symbol,
                    "flattened tiny position",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SUCCESS_SUBMITTED,
                    "flattened tiny position",
                ),
            )

        if guard_blocks_scale and not emergency_exit:
            logger.info(
                "[PDT][BLOCK] scale_out blocked for %s (pdt guard enabled)", self._symbol
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "pdt guard blocks scale_out",
                ),
                ExecutionOutcomeType.BLOCKED_PDT_EXIT,
                "pdt_guard_scale_out",
            )

        if fraction <= 0:
            logger.info(
                "[GUARD] Suppressing scale_out with non-positive fraction (%.4f) for %s",
                fraction,
                self._symbol,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "invalid scale_out fraction",
                ),
                ExecutionOutcomeType.SKIPPED,
                "invalid scale_out fraction",
            )

        if pos_size < 0:
            target_size = math.ceil(abs(pos_size) * (1 - fraction))
            order_qty = abs(pos_size) - target_size
            action = "BUY"
        else:
            target_size = math.floor(pos_size * (1 - fraction))
            order_qty = pos_size - target_size
            action = "SELL"

        if self._allows_fractional(self._symbol):
            max_qty = abs(pos_size)
            order_qty = max(0.0, min(abs(order_qty), max_qty))
            metadata = SYMBOL_METADATA.get(self._symbol.upper())
            if metadata and metadata.asset_class == AssetClass.CRYPTO:
                # Force crypto 8-decimal rounding even on scale-out
                order_qty = round(order_qty, 8)
                # Re-clamp after rounding just in case
                if order_qty > max_qty:
                    order_qty = max_qty
        else:
            max_qty = abs(int(pos_size))
            order_qty = max(0, min(abs(int(order_qty)), max_qty))
        new_size = pos_size + order_qty if pos_size < 0 else pos_size - order_qty
        target_signed = new_size

        if pos_size < 0 and action != "BUY":
            logger.info(
                "[GUARD] Suppressing scale_out that would increase risk (%s, side=short, requested %s)",
                self._symbol,
                action,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "would increase short risk",
                ),
                ExecutionOutcomeType.SKIPPED,
                "would increase short risk",
            )
        if pos_size > 0 and action != "SELL":
            logger.info(
                "[GUARD] Suppressing scale_out that would increase risk (%s, side=long, requested %s)",
                self._symbol,
                action,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "would increase long risk",
                ),
                ExecutionOutcomeType.SKIPPED,
                "would increase long risk",
            )
        if order_qty <= 0:
            logger.info(
                "[GUARD] scale_out produced zero quantity (pos=%.2f target=%.2f fraction=%.2f)",
                pos_size,
                target_signed,
                fraction,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "zero quantity scale_out",
                ),
                ExecutionOutcomeType.SKIPPED,
                "zero quantity scale_out",
            )
        if (pos_size < 0 and new_size > 0) or (pos_size > 0 and new_size < 0):
            logger.info(
                "[GUARD] Suppressing scale_out that would flip the book (pos=%.2f qty=%s -> new=%.2f)",
                pos_size,
                order_qty,
                new_size,
            )
            return self._respond(
                ExecutionResult(
                    ExecutionStatus.STAND_ASIDE,
                    decision.symbol,
                    "would flip book",
                ),
                ExecutionOutcomeType.SKIPPED,
                "would flip book",
            )

        contract = self._contract_for_symbol(self._symbol)
        order = MarketOrder(action=action, totalQuantity=order_qty)
        metadata = SYMBOL_METADATA.get(self._symbol.upper())
        order.tif = self._effective_tif(
            metadata.asset_class if metadata else None,
            getattr(contract, "exchange", None),
            "GTC",
        )
        try:
            self.ib.placeOrder(contract, order)
            logger.info(
                "Sent scale_out order to %s %s shares of %s (pos=%.2f -> target=%.2f, fraction=%.2f)",
                action,
                order_qty,
                self._symbol,
                pos_size,
                target_signed,
                fraction,
            )
            return (
                ExecutionResult(
                    ExecutionStatus.EXECUTED,
                    decision.symbol,
                    "scale_out order sent",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.SUCCESS_SUBMITTED,
                    "scale_out executed",
                ),
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to place scale_out order for %s: %s", self._symbol, exc)
            return (
                ExecutionResult(
                    ExecutionStatus.ERROR,
                    decision.symbol,
                    f"scale_out failed: {exc}",
                ),
                self._make_outcome(
                    decision.symbol,
                    ExecutionOutcomeType.ERROR,
                    "scale_out failed",
                    detail=str(exc),
                ),
            )

    def _ensure_emergency_stop(self) -> None:
        """If a position exists without a stop, place a protective emergency stop."""
        if not self.ib:
            return
        pct = float(getattr(self.runtime, "emergency_stop_pct", 0.0))
        if pct <= 0:
            return
        state = self._fetch_symbol_state(self._symbol)
        if state["position_shares"] == 0 or state.get("stop_loss") is not None:
            return
        avg = state.get("avg_price")
        if not avg or avg <= 0:
            logger.info("[GUARD] emergency stop skipped: avg_price missing")
            return
        from ib_insync import StopOrder  # type: ignore

        direction = state["direction"]
        qty = abs(state["position_shares"])
        if qty <= 0:
            return
        if direction == "long":
            stop_px = avg * (1 - pct)
            action = "SELL"
        else:
            stop_px = avg * (1 + pct)
            action = "BUY"
        stop_px = round(stop_px, 2)
        contract = self._contract_for_symbol(self._symbol)
        metadata = SYMBOL_METADATA.get(self._symbol.upper())
        if (
            metadata
            and metadata.asset_class == AssetClass.CRYPTO
            and getattr(contract, "exchange", "").upper() == "ZEROHASH"
        ):
            logger.info("[GUARD] emergency stop skipped for ZEROHASH crypto; synthetic stops handle protection")
            return
        try:
            order = StopOrder(action=action, totalQuantity=qty, stopPrice=stop_px, tif="GTC")
            self.ib.placeOrder(contract, order)
            logger.info(
                "[GUARD] Placed emergency stop for %s %s shares at %.4f (avg=%.4f pct=%.4f)",
                direction,
                qty,
                stop_px,
                avg,
                pct,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to place emergency stop: %s", exc)

    def summarize_pnl(self):
        """Pulls positions and PnL so you can brag (or cry) later."""
        if not self.ib:
            logger.info("No IBKR connection for PnL summary.")
            return
        try:
            positions = self.ib.positions()
            acct = self.settings.account_id or ""
            summary = self.ib.accountSummary()
            logger.info("Positions: %s", positions)
            logger.info("Account summary: %s", summary)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to summarize PnL: %s", exc)

    def _fetch_symbol_state(self, symbol: str) -> dict:
        """Reads current positions and open bracket risk for the symbol."""
        symbol = symbol.upper()
        state = {
            "position_shares": 0,
            "direction": None,
            "open_bracket_risk": 0.0,
            "open_parent_shares": {"long": 0, "short": 0},
            "stop_loss": None,
            "take_profit": None,
            "avg_price": None,
            "working_orders": 0,
            "working_order_statuses": [],
            "synthetic_stop_armed": False,
        }
        try:
            positions = self.ib.positions()
            for pos in positions:
                contract = getattr(pos, "contract", None)
                if self._contract_matches_symbol(symbol, contract):
                    logger.debug(f"[IBKR] Match: symbol={symbol} contract={getattr(contract, 'symbol', 'N/A')} qty={pos.position}")
                    state["position_shares"] += pos.position
                    state["avg_price"] = float(pos.avgCost)
            if state["position_shares"] > 0:
                state["direction"] = "long"
            elif state["position_shares"] < 0:
                state["direction"] = "short"
        except Exception as e:
            logger.debug(f"Failed to set position direction for {symbol}: {e}")
            pass

        try:
            orders = self.ib.openTrades()
            # Map parentId to parent price/action
            parents = {}
            for o in orders:
                if o.order.parentId == 0 and self._contract_matches_symbol(symbol, getattr(o, "contract", None)):
                    parents[o.order.orderId] = o.order
                    dir_key = "long" if o.order.action == "BUY" else "short"
                    state["open_parent_shares"][dir_key] += o.order.totalQuantity
            for o in orders:
                od = o.order
                if not self._contract_matches_symbol(symbol, getattr(o, "contract", None)):
                    continue
                if od.orderType == "STP" and od.parentId in parents:
                    parent = parents[od.parentId]
                    if parent.lmtPrice and od.auxPrice:
                        per = abs(parent.lmtPrice - od.auxPrice)
                        qty = od.totalQuantity
                        state["open_bracket_risk"] += per * qty
                        state["stop_loss"] = od.auxPrice
                if od.orderType in {"LMT", "MIT"} and od.parentId in parents:
                    if getattr(od, "lmtPrice", None):
                        state["take_profit"] = od.lmtPrice
                status_name = getattr(getattr(o, "orderStatus", None), "status", None)
                if status_name in WORKING_ORDER_STATUSES:
                    state["working_orders"] += 1
                    if status_name not in state["working_order_statuses"]:
                        state["working_order_statuses"].append(status_name)
        except Exception as e:
            logger.error(f"Failed to process open orders for {symbol}: {e}")
            pass
        if state["position_shares"] == 0 and state["working_orders"] > 0:
            try:
                open_orders = self.ib.openOrders()
                has_active = False
                for o in open_orders:
                    contract = getattr(o, "contract", None)
                    if not self._contract_matches_symbol(symbol, contract):
                        continue
                    status_name = getattr(getattr(o, "orderStatus", None), "status", None)
                    if status_name in WORKING_ORDER_STATUSES:
                        has_active = True
                        break
                if not has_active:
                    state["working_orders"] = 0
                    state["working_order_statuses"] = []
            except Exception as e:
                logger.debug(f"Failed to verify openOrders for {symbol}: {e}")

        if symbol.upper() == "BTCUSD":
            symbol = "BIP"
        elif symbol.upper() == "ETHUSD":
            symbol = "ETP"

        local = self._local_stop_info.get(symbol)
        if local:
            state["stop_loss"] = local["stop_level"]
        active_stop = self._synthetic_stops.get(symbol)
        if active_stop and active_stop.state == "armed":
            state["synthetic_stop_armed"] = True
        return state

    def list_open_position_symbols(self) -> list[str]:
        """Returns canonical symbols (e.g. BTCUSD, SPY) with non-zero broker positions."""
        if not self.ib:
            return []
        symbols: set[str] = set()
        try:
            for pos in self.ib.positions():
                if abs(getattr(pos, "position", 0) or 0) < 1e-8:
                    continue
                canonical = self._canonical_symbol_for_contract(getattr(pos, "contract", None))
                if canonical:
                    symbols.add(str(canonical).upper())
                    continue
                contract_symbol = getattr(getattr(pos, "contract", None), "symbol", None)
                if contract_symbol:
                    symbols.add(str(contract_symbol).upper())
        except Exception as e:
            logger.error(f"Failed to list open position symbols: {e}")
            return []
        return sorted(symbols)

    def _campaign_state(self, symbol: str):
        """Builds a lightweight per-symbol campaign snapshot."""
        state = self._fetch_symbol_state(symbol)
        from dataclasses import dataclass
        from typing import Literal

        @dataclass
        class CampaignState:
            side: Optional[str]
            has_position: bool
            position_size: float
            avg_price: Optional[float]
            has_bracket: bool
            parent_order_id: Optional[int]
            tp_order_id: Optional[int]
            sl_order_id: Optional[int]
            protection_mode: str
            local_stop_level: Optional[float]

        side = state["direction"]
        pos_size = state["position_shares"]
        has_pos = pos_size != 0
        # Bracket presence inferred from open_parent_shares > 0
        has_bracket = any(state["open_parent_shares"].values())
        parent_id = None
        tp_id = None
        sl_id = None
        try:
            orders = self.ib.openOrders()
            for o in orders:
                if not self._contract_matches_symbol(symbol, getattr(o, "contract", None)):
                    continue
                if o.order.parentId == 0 and parent_id is None:
                    parent_id = o.order.orderId
                if o.order.orderType == "LMT" and o.order.parentId:
                    tp_id = o.order.orderId
                if o.order.orderType == "STP" and o.order.parentId:
                    sl_id = o.order.orderId
        except Exception:
            pass

        local = self._local_stop_info.get(symbol.upper())
        mode = "local_stop" if local else "native_bracket"
        return CampaignState(
            side=side,
            has_position=has_pos,
            position_size=pos_size,
            avg_price=state.get("avg_price"),
            has_bracket=has_bracket,
            parent_order_id=parent_id,
            tp_order_id=tp_id,
            sl_order_id=sl_id,
            protection_mode=mode,
            local_stop_level=local["stop_level"] if local else None,
        )

    def _rebuild_bracket_for_existing(self, campaign, decision: AITradeDecision) -> None:
        """Places TP/SL around an existing position if none are active."""
        if not self.ib:
            logger.info("Dry-run: would rebuild bracket")
            return
        if decision.take_profit is None or decision.stop_loss is None:
            logger.info("[GUARD] Cannot rebuild bracket without TP/SL values.")
            return
        from ib_insync import LimitOrder, StopOrder  # type: ignore

        symbol = self._symbol
        # Clear any stale working orders before rebuilding protection
        self.cancel_all_orders_for_symbol(symbol)
        qty = abs(campaign.position_size)
        protect_action = "SELL" if campaign.side == "long" else "BUY"
        contract = self._contract_for_symbol(symbol)
        metadata = SYMBOL_METADATA.get(symbol.upper())
        if (
            metadata
            and metadata.asset_class == AssetClass.CRYPTO
            and getattr(contract, "exchange", "").upper() == "ZEROHASH"
        ):
            logger.info(
                "[CRYPTO] ZEROHASH synthetic protection preferred; rebuilding synthetic protection for %s",
                symbol,
            )
            self._register_synthetic_stop(
                symbol,
                campaign.side,
                decision.stop_loss,
                decision.take_profit,
                qty,
                None,
                None,
            )
            return
        base_id = self.ib.client.getReqId()
        parent_id = base_id
        tp_order = LimitOrder(
            action=protect_action,
            totalQuantity=qty,
            lmtPrice=decision.take_profit,
            tif="GTC",
            parentId=parent_id,
            orderId=base_id + 1,
            transmit=False,
        )
        sl_order = StopOrder(
            action=protect_action,
            totalQuantity=qty,
            stopPrice=decision.stop_loss,
            tif="GTC",
            parentId=parent_id,
            orderId=base_id + 2,
            transmit=True,
        )
        parent = LimitOrder(
            action="BUY" if campaign.side == "short" else "SELL",
            totalQuantity=0,
            lmtPrice=decision.entry_price or decision.take_profit,
            tif="GTC",
            orderId=parent_id,
            transmit=False,
        )
        self.ib.placeOrder(contract, parent)
        self.ib.placeOrder(contract, tp_order)
        if metadata:
            self._maybe_place_stop_order(
                symbol,
                metadata,
                contract,
                sl_order,
                direction,
                stop_loss,
                None,
            )
        else:
            self.ib.placeOrder(contract, sl_order)
        logger.info(
            "[STATE] %s protection: side=%s sl=%.4f tp=%.4f emergency=%s size=%.2f",
            symbol,
            protect_action,
            decision.stop_loss,
            decision.take_profit,
            "active" if self.runtime.emergency_stop_pct > 0 else "none",
            qty,
        )

    def get_open_position_snapshot(self, symbol: str) -> Optional[dict]:
        """Returns structured open position info for prompt context."""
        symbol_key = symbol.upper()
        try:
            positions = self.ib.positions()
            for pos in positions:
                if self._contract_matches_symbol(symbol, getattr(pos, "contract", None)):
                    side = "long" if pos.position > 0 else "short"
                    state = self._fetch_symbol_state(symbol)
                    age = self._position_hold_age_seconds(symbol) or 0.0
                    allow_day_trades = bool(getattr(self.runtime, "allow_day_trades", False))
                    hold_remaining = None
                    if not allow_day_trades:
                        hold_remaining = max(0.0, float(getattr(self.runtime, "min_hold_seconds", 0) or 0) - age)

                    # Get metadata (htf_neutral_bars, pyramid_count, etc.)
                    metadata = self._position_metadata.get(symbol_key, {})

                    return {
                        "side": side,
                        "direction": side,  # Add for compatibility with strategy engine
                        "size": float(pos.position),
                        "avg_price": float(pos.avgCost),
                        "entry_price": float(pos.avgCost),  # Add for compatibility
                        "stop_loss": state.get("stop_loss"),
                        "take_profit": state.get("take_profit"),
                        "working_orders": state.get("working_orders", 0),
                        "working_order_statuses": state.get("working_order_statuses", []),
                        "open_bracket_risk": float(state.get("open_bracket_risk", 0.0) or 0.0),
                        "synthetic_stop_armed": state.get("synthetic_stop_armed", False),
                        "scale_ins_taken": int(self._scale_in_counts.get(symbol_key, 0)),
                        "max_scale_ins_per_leg": int(getattr(self.runtime, "max_scale_ins_per_leg", 2)),
                        "hold_age_seconds": float(age),
                        "hold_remaining_seconds": float(hold_remaining) if hold_remaining is not None else None,
                        "htf_neutral_bars": int(metadata.get("htf_neutral_bars", 0)),
                        "pyramid_count": int(metadata.get("pyramid_count", 1)),
                    }
        except Exception as e:
            logger.error(f"Failed to build campaign state for {symbol}: {e}")
            return None
        self._scale_in_counts[symbol_key] = 0
        self._position_metadata.pop(symbol_key, None)  # Clear metadata when no position
        return None

    def update_position_metadata(self, symbol: str, snapshot) -> None:
        """Update position metadata like htf_neutral_bars counter.

        This should be called from the runtime loop after fetching the latest snapshot
        to track how long HTF has been neutral (for timeout exits).
        """
        symbol_key = symbol.upper()
        if symbol_key not in self._position_metadata:
            self._position_metadata[symbol_key] = {"htf_neutral_bars": 0, "pyramid_count": 1}

        metadata = self._position_metadata[symbol_key]

        # Update HTF neutral bar counter
        if snapshot and hasattr(snapshot, "trend_htf") and snapshot.trend_htf:
            from tradebot_sci.market.trend_enums import TrendDirection
            if snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
                metadata["htf_neutral_bars"] = metadata.get("htf_neutral_bars", 0) + 1
            else:
                # Reset counter when HTF becomes trending again
                metadata["htf_neutral_bars"] = 0

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        """Cancels all open orders for a symbol to clear stale brackets."""
        if not self.ib:
            return
        symbol = symbol.upper()
        try:
            for trade in self.ib.openTrades():
                if self._contract_matches_symbol(symbol, getattr(trade, "contract", None)):
                    self.ib.cancelOrder(trade.order)
            logger.info("Cancelled all open orders for %s", symbol)
        except Exception as exc:
            logger.error("Failed to cancel orders for %s: %s", symbol, exc)

    def _flatten_symbol(self, symbol: str) -> None:
        """Flattens positions for a symbol and verifies the book is truly flat."""
        if not self.ib:
            return
        symbol = symbol.upper()
        try:
            from ib_insync import MarketOrder  # type: ignore
        except Exception as exc:  # pragma: no cover
            logger.error("ib_insync MarketOrder unavailable: %s", exc)
            return

        self.cancel_all_orders_for_symbol(symbol)
        positions = [
            p
            for p in self.ib.positions()
            if self._contract_matches_symbol(symbol, getattr(p, "contract", None)) and p.position != 0
        ]
        had_positions = bool(positions)
        if not positions:
            logger.info("[STATE] %s open_position: none", symbol)
            self._clear_local_stop(symbol)
            return

        for pos in positions:
            action = "SELL" if pos.position > 0 else "BUY"
            qty = abs(pos.position)
            close_order = MarketOrder(action=action, totalQuantity=qty)
            contract = self._contract_for_symbol(symbol)
            metadata = SYMBOL_METADATA.get(symbol.upper())
            close_order.tif = self._effective_tif(
                metadata.asset_class if metadata else None,
                getattr(contract, "exchange", None),
                "GTC",
            )
            self._set_order_ref(close_order, symbol, "FLATTEN")
            self._apply_zerohash_minutes_tif(close_order)
            self.ib.placeOrder(contract, close_order)
            logger.info("Flattening %s: sent %s %s shares", symbol, action, qty)

        for _ in range(5):
            try:
                self.ib.sleep(1)
            except Exception:
                time.sleep(1)
            remaining = [
                p
                for p in self.ib.positions()
                if self._contract_matches_symbol(symbol, getattr(p, "contract", None)) and p.position != 0
            ]
            if not remaining:
                logger.info("[STATE] %s open_position: none", symbol)
                return

        remaining = [
            p
            for p in self.ib.positions()
            if self._contract_matches_symbol(symbol, getattr(p, "contract", None)) and p.position != 0
        ]
        if remaining:
            logger.info(
                "[GUARD] flatten_symbol: residual position remains (%s, pos=%.2f); manual attention required",
                symbol,
                remaining[0].position,
            )
        self._clear_local_stop(symbol)
        if had_positions:
            self._record_equity_exit(symbol)

    def flatten_symbol(self, symbol: str) -> None:
        """Public wrapper to flatten positions for a symbol."""
        self._flatten_symbol(symbol)

    def _contract_for_symbol(self, symbol: str):
        """Routes to the right IBKR contract builder and caches the result."""
        key = symbol.upper()
        if key in self._contract_cache:
            return self._contract_cache[key]
        try:
            contract = build_contract(key)
        except ContractResolutionError as exc:
            raise RuntimeError(f"Unable to build contract for {key}: {exc}") from exc
        self._contract_cache[key] = contract
        return contract

    def _discover_zero_hash_symbols(self) -> list[str]:
        # Skip Zerohash management if IBKR is not the primary crypto broker
        broker_mode = (os.getenv("BROKER_MODE") or "").strip().lower()
        if broker_mode in {"hybrid", "alternative"}:
            logger.info("[CRYPTO][IBKR] Skipping Zerohash discovery (managed by alternative broker)")
            return []

        symbols: list[str] = []
        for sym, metadata in SYMBOL_METADATA.items():
            if metadata.asset_class != AssetClass.CRYPTO:
                continue
            try:
                contract = self._contract_for_symbol(sym)
            except Exception as e:
                logger.debug(f"Failed to get contract for {sym}: {e}")
                continue
            if getattr(contract, "exchange", "").upper() == "ZEROHASH":
                symbols.append(sym)
        return symbols

    def _is_zero_hash_symbol(self, symbol: str) -> bool:
        return symbol.upper() in self._zero_hash_symbols_set

    def is_symbol_paused(self, symbol: str) -> bool:
        return symbol in self._paused_symbols

    def get_execution_capabilities(self, symbol: str) -> dict:
        """Returns venue capabilities used to steer the AI and normalize decisions."""
        sym = symbol.upper()
        metadata = SYMBOL_METADATA.get(sym)
        asset_class = metadata.asset_class.value if metadata else "unknown"
        exchange = None
        long_only = False
        supports_short = True
        supports_bracket_children = True
        supports_native_brackets = True
        supports_native_stops = True
        requires_synthetic_stops = False
        if metadata and metadata.asset_class == AssetClass.CRYPTO:
            try:
                contract = self._contract_for_symbol(sym)
                exchange = (getattr(contract, "exchange", "") or "").upper() or None
            except Exception:
                exchange = (metadata.exchange or "").upper() or None
            if exchange == "ZEROHASH":
                long_only = False
                supports_short = True
                supports_bracket_children = False
                supports_native_brackets = False
                supports_native_stops = False
                requires_synthetic_stops = True
        return {
            "venue": "IBKR",
            "venue_name": "IBKR",
            "asset_class": asset_class,
            "exchange": exchange,
            "long_only": long_only,
            "supports_short": supports_short,
            "supports_bracket_children": supports_bracket_children,
            "supports_native_brackets": supports_native_brackets,
            "supports_native_stops": supports_native_stops,
            "requires_synthetic_stops": requires_synthetic_stops,
        }

    def _place_entry_bracket(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        take_profit: float | None,
        stop_loss: float,
        metadata: SymbolMetadata,
        tif: str = "GTC",
    ) -> None:
        """Places a parent limit with TP/SL children using explicit orderIds and correct exit sides."""
        from ib_insync import LimitOrder, StopOrder  # type: ignore

        exit_side = "SELL" if direction == "long" else "BUY"
        action = "BUY" if direction == "long" else "SELL"
        base_id = self.ib.client.getReqId()
        parent_id = base_id
        contract = self._contract_for_symbol(symbol)
        contract_exchange = getattr(contract, "exchange", "") or ""
        zerohash_crypto = (
            metadata.asset_class == AssetClass.CRYPTO and contract_exchange.upper() == "ZEROHASH"
        )
        tif = self._effective_tif(metadata.asset_class, contract_exchange, tif)
        min_tick = self._get_min_tick(contract, symbol) or 0.0
        if min_tick > 0:
            entry_price = self._round_price_to_tick(entry_price, min_tick)
            stop_loss = self._round_price_to_tick(stop_loss, min_tick)
            if take_profit is not None:
                take_profit = self._round_price_to_tick(take_profit, min_tick)
                entry_price, take_profit, stop_loss = self._align_bracket_prices(
                    direction, entry_price, take_profit, stop_loss, min_tick
                )

        if zerohash_crypto:
            logger.info(
                "[CRYPTO] ZEROHASH synthetic protection preferred; using entry-only + synthetic stop for %s",
                symbol,
            )
            order_type = "LIMIT"
            if self.profile_settings and getattr(self.profile_settings, "crypto_order_type", "LIMIT") == "MARKET":
                order_type = "MARKET"

            if order_type == "MARKET":
                from ib_insync import MarketOrder # type: ignore
                parent = MarketOrder(
                    action=action,
                    totalQuantity=quantity,
                    ordersRef="", # Will be set by _set_order_ref
                    transmit=True,
                )
            else:
                parent = LimitOrder(
                    action=action,
                    totalQuantity=quantity,
                    lmtPrice=entry_price,
                    tif=tif,
                    orderId=parent_id,
                    transmit=True,
                )
            
            # _effective_tif already handles overrides; Market orders on Zerohash usually accept IOC/Minutes too
            # but standard MarketOrder in ib_insync doesn't always set tif. We ensure it matches.
            parent.orderId = parent_id
            if order_type == "LIMIT":
                self._apply_zerohash_minutes_tif(parent)
            
            self._set_order_ref(parent, symbol, "ENTRY")
            
            # Additional logging for Market orders
            if order_type == "MARKET":
                 logger.info(
                    "[CRYPTO] Placing MARKET order for %s (qty=%s) due to crypto_order_type=MARKET",
                    symbol,
                    quantity,
                )
            
            self.ib.placeOrder(contract, parent)
            orders_sent = [parent]
            self._register_synthetic_stop(
                symbol,
                direction,
                stop_loss,
                take_profit,
                quantity,
                parent,
                None,
            )
        else:
            if take_profit is None:
                raise ValueError("take_profit is required for non-ZEROHASH bracket orders")
            parent = LimitOrder(
                action=action,
                totalQuantity=quantity,
                lmtPrice=entry_price,
                tif=tif,
                orderId=parent_id,
                transmit=False,
            )
            tp_order = LimitOrder(
                action=exit_side,
                totalQuantity=quantity,
                lmtPrice=take_profit,
                tif=tif,
                orderId=base_id + 1,
                parentId=parent_id,
                transmit=False,
            )
            self._set_order_ref(parent, symbol, "ENTRY")
            self._set_order_ref(tp_order, symbol, "TP")
            self.ib.placeOrder(contract, parent)
            self.ib.placeOrder(contract, tp_order)
            orders_sent = [parent, tp_order]
            sl_order = StopOrder(
                action=exit_side,
                totalQuantity=quantity,
                stopPrice=stop_loss,
                tif=tif,
                orderId=base_id + 2,
                parentId=parent_id,
                transmit=True,
            )
            self._set_order_ref(sl_order, symbol, "SL")
            stop_sent = self._maybe_place_stop_order(
                symbol,
                metadata,
                contract,
                sl_order,
                direction,
                stop_loss,
                entry_price,
            )
            if stop_sent:
                orders_sent.append(sl_order)
            else:
                tp_order.transmit = True
                # When stop placement fails, flip TP to transmit and modify the order so IBKR actually transmits
                # the parent+TP bracket (otherwise both legs remain transmit=False and can be discarded).
                try:
                    self.ib.placeOrder(contract, tp_order)
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "[CRYPTO] Failed to transmit updated TP order for %s (orderId=%s): %s",
                        symbol,
                        getattr(tp_order, "orderId", "n/a"),
                        exc,
                    )
        self.placed_orders.extend(orders_sent)
        self._last_bracket_orders = list(orders_sent)
        return orders_sent

    def _place_protection_orders(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        take_profit: float,
        stop_loss: float,
        tif: str = "GTC",
    ) -> None:
        """Places standalone TP/SL for an existing position with the correct exit side."""
        from ib_insync import LimitOrder, StopOrder  # type: ignore

        exit_side = "SELL" if direction == "long" else "BUY"
        contract = self._contract_for_symbol(symbol)
        metadata = SYMBOL_METADATA.get(symbol.upper())
        if (
            metadata
            and metadata.asset_class == AssetClass.CRYPTO
            and getattr(contract, "exchange", "").upper() == "ZEROHASH"
        ):
            logger.info(
                "[CRYPTO] ZEROHASH synthetic protection preferred; using synthetic protection for %s",
                symbol,
            )
            self._register_synthetic_stop(
                symbol,
                direction,
                stop_loss,
                take_profit,
                quantity,
                None,
                None,
            )
            return
        min_tick = self._get_min_tick(contract, symbol) or 0.0
        if min_tick > 0:
            take_profit = self._round_price_to_tick(take_profit, min_tick)
            stop_loss = self._round_price_to_tick(stop_loss, min_tick)

        tp_order = LimitOrder(
            action=exit_side,
            totalQuantity=quantity,
            lmtPrice=take_profit,
            tif=tif,
            transmit=False,
        )
        sl_order = StopOrder(
            action=exit_side,
            totalQuantity=quantity,
            stopPrice=stop_loss,
            tif=tif,
            transmit=True,
        )

        self._set_order_ref(tp_order, symbol, "TP")
        self._set_order_ref(sl_order, symbol, "SL")
        self.ib.placeOrder(contract, tp_order)
        self.ib.placeOrder(contract, sl_order)
        self.placed_orders.extend([tp_order, sl_order])
