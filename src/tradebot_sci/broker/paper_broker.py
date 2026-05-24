import logging
import json
import time
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Iterable

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult, ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.broker.trade_result_store import TradeResult
from tradebot_sci import paths as _paths
from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass, convert_quote_to_usd
from tradebot_sci.strategy.safety_guard import SafetyGuard

logger = logging.getLogger(__name__)

PAPER_STATE_FILE = str(_paths.DATA_DIR / "paper_state.json")

class PaperBroker:
    """A simulated broker for local-only paper trading during Sabbath."""

    # Per-leg trading friction for realistic paper results.
    # Crypto: Kraken ActiveTrader tier taker fee 0.25%, half-spread ~0.05%, slippage ~0.02%
    # Forex:  OANDA zero commission, friction is spread-only (~0.005% covers residual)
    TAKER_FEE_PCT_CRYPTO = float(os.getenv("PAPER_TAKER_FEE_PCT", "0.0025"))  # 0.25%
    TAKER_FEE_PCT_FOREX  = float(os.getenv("PAPER_FOREX_FEE_PCT", "0.00005")) # 0.005% (spread-only)
    HALF_SPREAD_PCT = float(os.getenv("PAPER_HALF_SPREAD_PCT", "0.0005"))  # 0.05%
    SLIPPAGE_PCT = float(os.getenv("PAPER_SLIPPAGE_PCT", "0.0002"))        # 0.02%


    def _get_taker_fee(self, symbol: str) -> float:
        """Return half of the round-trip fee for parity with backtester."""
        from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
        return get_fee_for_symbol(symbol) / 2.0

    def _get_paper_friction(self, tier_slip_bps: float = 0.0) -> tuple[float, float, float, float, bool]:
        """Parse configuration to extract fee, spread, and slippage percentages.
        Returns: (fee_pct, spread_pct, slip_pct, friction_rate, is_parity)
        """
        import json
        from tradebot_sci import paths as _paths
        try:
            with open(_paths.CONFIG_FILE, "r") as f:
                _full_conf = json.load(f)
                _p_conf = _full_conf.get("paper", {})
                _g_conf = _full_conf.get("global", {})
        except Exception:
            _p_conf = {}
            _g_conf = {}

        spread_buffer = float(_g_conf.get("spread_buffer", _p_conf.get("spread_bps", 0.0)))
        commission_rate = float(_g_conf.get("commission_rate", _p_conf.get("fee_bps", 0.0)))
        
        fee_bps = commission_rate
        spread_bps = spread_buffer
        slip_bps = float(_p_conf.get("slippage_bps", 0.0)) + tier_slip_bps

        if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
            return 0.0, 0.0, 0.0, 0.0, True
        else:
            fee_pct = fee_bps / 10000.0
            spread_pct = spread_bps / 10000.0
            slip_pct = slip_bps / 10000.0
            friction = (spread_pct / 2.0) + slip_pct
            return fee_pct, spread_pct, slip_pct, friction, False

    # Hard leverage cap for paper trading.
    # Profile target_leverage (e.g. 50x) is for OANDA forex — way too high for
    # crypto paper trading.  Cap at 3x to prevent catastrophic position sizing.
    PAPER_MAX_LEVERAGE = float(os.getenv("PAPER_MAX_LEVERAGE", "50.0"))
    
    def __init__(self, profile_settings, market_provider=None, trade_results=None, initial_balance=10000.0, controller=None):
        self.profile = profile_settings
        self.market_provider = market_provider
        self.trade_results = trade_results
        self.controller = controller
        self.positions = {} # symbol -> position_dict
        self.history = []
        self._exit_cooldowns = {}  # symbol -> timestamp of last exit
        self._emergency_stop_timers = {}  # [NEW] symbol -> epoch_time
        self.REENTRY_COOLDOWN = float(os.getenv("PAPER_REENTRY_COOLDOWN", "300"))  # 5 min default

        # Load persisted state or fall back to initial balance
        default_balance = float(os.getenv("PAPER_BALANCE", initial_balance))
        saved = self._load_state()
        if saved:
            self.balance = saved.get("balance", default_balance)
            self.positions = saved.get("positions", {})
            logger.info(f"Restored Paper Broker: ${self.balance:.2f} balance, {len(self.positions)} open positions.")
            # Anchor should be the saved balance to prevent sizing mismatch
            self._initial_balance = self.balance
        else:
            self.balance = default_balance
            logger.info(f"Initialized Paper Broker with ${self.balance:.2f} balance (no saved state).")
            self._initial_balance = default_balance
        
        # Immediate reporting on startup for UI visibility
        self.summarize_pnl()
        self.refresh_account_summary()
        self.last_status: str = "healthy"
        self.last_error: str = ""
        self._update_status("healthy", "")

    def _update_status(self, status: str, error: str = "") -> None:
        self.last_status = status
        self.last_error = error
        if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'health_monitor'):
            self.controller.health_monitor.record_paper_broker_status(status, error)

    def _load_state(self) -> dict | None:
        """Load persisted paper state from disk."""
        try:
            if os.path.exists(PAPER_STATE_FILE):
                with open(PAPER_STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[PAPER] Failed to load saved state: {e}")
        return None

    def _save_state(self):
        """Persist current balance and positions to disk."""
        try:
            os.makedirs(os.path.dirname(PAPER_STATE_FILE), exist_ok=True)
            state = {
                "balance": self.balance,
                "positions": self.positions,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp = PAPER_STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, PAPER_STATE_FILE)
        except Exception as e:
            logger.warning(f"[PAPER] Failed to save state: {e}")

    def _get_current_price(self, symbol: str) -> float:
        if self.market_provider:
            try:
                ticker = self.market_provider.get_ticker(symbol)
                if ticker and ticker.last:
                    return float(ticker.last)
            except Exception as e:
                logger.warning(f"[PAPER] Could not fetch price for {symbol}: {e}")
        return 100.0 # Fallback

    def _now(self) -> datetime:
        """Return the current time for internal strategy calculations.

        In replay mode, returns sim_time (candle timestamp) so that
        entry_time is in the same time domain as the engine's Hold Guard
        age calculation (which uses snapshot.candles[-1].timestamp).
        In live mode, returns wall-clock UTC time.
        """
        # Check if market_provider has sim_time (replay mode)
        if hasattr(self, 'market_provider') and self.market_provider is not None:
            sim_time = getattr(self.market_provider, 'sim_time', None)
            if isinstance(sim_time, datetime):
                return sim_time
        return datetime.now(timezone.utc)

    def _wall_clock(self) -> datetime:
        """Return real wall-clock UTC time for display timestamps.

        Used for opened_at/closed_at in trade results so the Trade History
        shows when trades actually happened, not the replay candle time
        (which races ahead of real time in turbo mode).
        """
        return datetime.now(timezone.utc)

    def _compute_duration(self, pos: dict) -> tuple[float, str]:
        """Compute duration of a paper position in seconds and human-readable string.
        
        Enforces sim_time domain first. If the resulting duration is less than 1 second
        (common in accelerated replay where entry and exit occur within the same heartbeat cycle/candle),
        falls back to high-resolution wall-clock duration to achieve sub-second/millisecond precision
        and avoid the "0m 0s" reporting bug.
        """
        duration_secs = 0.0
        try:
            entry_time_str = pos.get("entry_time")
            opened_at_str = pos.get("opened_at")
            
            # Start with sim_time domain
            if entry_time_str:
                entry_dt = datetime.fromisoformat(entry_time_str)
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                closed_sim = self._now()
                if closed_sim.tzinfo is None:
                    closed_sim = closed_sim.replace(tzinfo=timezone.utc)
                duration_secs = (closed_sim - entry_dt).total_seconds()
                if duration_secs < 0:
                    duration_secs = abs(duration_secs)
            
            # Fall back to wall-clock if sub-second
            if duration_secs < 1.0 and opened_at_str:
                opened_at_dt = datetime.fromisoformat(opened_at_str)
                if opened_at_dt.tzinfo is None:
                    opened_at_dt = opened_at_dt.replace(tzinfo=timezone.utc)
                now_wall = self._wall_clock()
                if now_wall.tzinfo is None:
                    now_wall = now_wall.replace(tzinfo=timezone.utc)
                wall_diff = (now_wall - opened_at_dt).total_seconds()
                if wall_diff > 0:
                    duration_secs = wall_diff
                else:
                    duration_secs = 0.001  # Fallback to 1ms minimum
        except Exception:
            pass

        if not isinstance(duration_secs, (int, float)):
            duration_secs = 0.0

        # Format string
        if duration_secs < 1.0:
            ms = int(duration_secs * 1000)
            if ms <= 0:
                ms = 1
            duration_str = f"{ms}ms"
        else:
            mins = int(duration_secs // 60)
            secs = int(duration_secs % 60)
            
            if mins >= 60:
                hrs = mins // 60
                mins = mins % 60
                duration_str = f"{hrs}h {mins}m {secs}s"
            elif mins > 0:
                duration_str = f"{mins}m {secs}s"
            else:
                duration_str = f"{secs}s"

        return duration_secs, duration_str

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        """Return sizing capital (initial balance) to prevent compounding snowball.

        External callers (strategy engine, safety guards) use this for position
        sizing.  We return the *initial* balance so that a $10K account doesn't
        suddenly size like a $113M account after a few lucky wins.
        The full running balance is still available via get_total_balance_value().
        """
        return self._initial_balance

    def get_display_cash(self) -> float:
        """Return actual tracked cash balance for GUI display purposes.

        Unlike get_liquid_capital() which returns a fixed sizing base,
        this returns the real running balance so the GUI shows accurate
        liquid cash to the user.
        """
        return self.balance

    def get_total_balance_value(self) -> float:
        """Sum of cash + unrealized pnl of all paper positions."""
        total = self.balance
        for sym, pos in self.positions.items():
            total += pos.get("unrealized_pnl", 0.0)
        return total

    def get_total_equity(self) -> float:
        """Return total account equity for safety guards."""
        return self.get_total_balance_value()

    def refresh_account_summary(self) -> None:
        # Prefixed with [PAPER] so ledger daemon skips these lines
        logger.info(f"[PAPER] [TOTAL] Liquidity available: ${self.balance:.2f}")
        logger.info(f"[PAPER] [CASH] Buying Power: ${self.balance:.2f}")

    def _apply_high_net_worth_restrictions(self, symbol: str, action: str, price: float, sizing_capital: float, qty: float, decision: Any, existing_notional: float = 0.0) -> tuple[float, float, bool, str]:
        """
        Applies professional broker restrictions for high-net-worth / large balance accounts.
        Returns: (adjusted_qty, slippage_penalty_bps, is_blocked, block_reason)
        """
        # Determine account tier based on total equity
        if sizing_capital < 50000.0:
            tier_name = "Standard (<$50k)"
            max_leverage = self.PAPER_MAX_LEVERAGE
            slippage_bps = 0.0
            max_symbol_notional = sizing_capital * max_leverage
            min_stop_pct = 0.0010  # 0.10%
            reject_prob = 0.0
        elif sizing_capital < 250000.0:
            tier_name = "High-Balance Tier 1 ($50k-$250k)"
            max_leverage = min(20.0, self.PAPER_MAX_LEVERAGE)
            slippage_bps = 1.0
            max_symbol_notional = min(sizing_capital * max_leverage, 1000000.0)
            min_stop_pct = 0.0015  # 0.15%
            reject_prob = 0.0
        elif sizing_capital < 1000000.0:
            tier_name = "High-Balance Tier 2 ($250k-$1M)"
            max_leverage = min(10.0, self.PAPER_MAX_LEVERAGE)
            slippage_bps = 2.5
            max_symbol_notional = min(sizing_capital * max_leverage, 2000000.0)
            min_stop_pct = 0.0020  # 0.20%
            reject_prob = 0.0
        else:
            tier_name = "Whale / Institutional (>$1M)"
            max_leverage = min(5.0, self.PAPER_MAX_LEVERAGE)
            slippage_bps = 5.0
            max_symbol_notional = min(sizing_capital * max_leverage, 3000000.0)
            min_stop_pct = 0.0025  # 0.25%
            reject_prob = 0.05  # 5% chance of manual desk review rejection

        # 1. Simulated Institutional Desk Review Rejection
        if reject_prob > 0:
            import random
            if random.random() < reject_prob:
                logger.warning(f"[PAPER] [DESK REVIEW REJECT] {symbol}: Order rejected by institutional desk review ({reject_prob*100:.1f}% chance for {tier_name})")
                if hasattr(self, 'controller') and self.controller:
                    self.controller.broadcast_restriction({
                        "symbol": symbol,
                        "restriction_type": "desk_review",
                        "tier": tier_name,
                        "message": f"Order rejected by institutional desk review ({reject_prob*100:.1f}% chance for {tier_name}).",
                        "suggested_action": "Click AI Optimize to adjust sizing or enable Seasoned Trader Autopilot.",
                        "manual_location": "Settings Tab -> Strategy Parameters -> Risk Per Trade / Max Leverage"
                    })
                return qty, slippage_bps, True, f"Institutional desk review rejection ({tier_name})"

        # 2. Mandatory Minimum Stop Distance Widen
        if decision and getattr(decision, "stop_loss", None) and abs(price - decision.stop_loss) > 1e-6:
            risk_per_unit = abs(price - decision.stop_loss)
            min_stop_distance = price * min_stop_pct
            if risk_per_unit < min_stop_distance:
                target_r_cfg = float(getattr(self.profile, 'target_r', 2.5))
                logger.warning(
                    f"[PAPER] [STOP-WIDEN TIERING] {symbol}: Stop too tight for {tier_name} "
                    f"(${risk_per_unit:.5f} < ${min_stop_distance:.5f} / {min_stop_pct*100:.2f}%), "
                    f"widening to tier minimum (rescaling TP to {target_r_cfg}R)"
                )
                risk_per_unit = min_stop_distance
                if action in ("enter_long", "scale_in_long", "buy"):
                    decision.stop_loss = price - min_stop_distance
                    decision.take_profit = price + (min_stop_distance * target_r_cfg)
                else:
                    decision.stop_loss = price + min_stop_distance
                    decision.take_profit = price - (min_stop_distance * target_r_cfg)
                
                # If we widened the stop, recompute qty to maintain risk_usd if possible
                risk_usd = getattr(decision, "risk_per_trade_dollars", 0.0)
                if not risk_usd:
                    risk_pct = getattr(decision, "risk_per_trade_pct", None) or getattr(self.profile, "risk_per_trade_pct", 0.01)
                    risk_usd = sizing_capital * float(risk_pct)
                qty = risk_usd / risk_per_unit

        # 3. Leverage & Concentration Sizing Cap
        profile_leverage = getattr(self.profile, "target_leverage", 1.0) or 1.0
        effective_leverage = min(profile_leverage, max_leverage)
        
        # Adjust max_symbol_notional to respect effective_leverage and actual balance
        effective_max_notional = min(max_symbol_notional, sizing_capital * effective_leverage, self.balance * effective_leverage)
        
        # Calculate maximum additional notional allowed
        remaining_notional = max(0.0, effective_max_notional - existing_notional)
        max_add_qty = remaining_notional / price if price > 0 else 0.0

        if qty > max_add_qty:
            if max_add_qty <= 0:
                logger.warning(
                    f"[PAPER] [CONCENTRATION BLOCKED] {symbol}: existing notional "
                    f"${existing_notional:,.0f} already at {tier_name} cap ${max_symbol_notional:,.0f} "
                    f"(max leverage {effective_leverage}x)"
                )
                if hasattr(self, 'controller') and self.controller:
                    self.controller.broadcast_restriction({
                        "symbol": symbol,
                        "restriction_type": "concentration_blocked",
                        "tier": tier_name,
                        "message": f"Existing notional ${existing_notional:,.0f} already at {tier_name} cap ${max_symbol_notional:,.0f}.",
                        "suggested_action": "Click AI Optimize to balance portfolio allocation or enable AI Autopilot.",
                        "manual_location": "Settings Tab -> Strategy Parameters -> Max Position Concentration"
                    })
                return qty, slippage_bps, True, f"Concentration limit reached for {tier_name} (${max_symbol_notional:,.0f} cap)"
            
            logger.warning(
                f"[PAPER] [TIERED SIZING CAP] {symbol}: qty {qty:.4f} -> {max_add_qty:.4f} "
                f"(notional ${qty * price:,.0f} + existing ${existing_notional:,.0f} exceeds {tier_name} cap ${max_symbol_notional:,.0f} at {effective_leverage}x leverage)",
                extra={"broker": "paper", "symbol": symbol, "event": "tiered_sizing_cap", "original_qty": qty, "capped_qty": max_add_qty, "tier": tier_name}
            )
            qty = max_add_qty

        return qty, slippage_bps, False, ""

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        action = decision.action
        symbol = decision.symbol
        price = self._get_current_price(symbol)
        
        if action in {"enter_long", "enter_short"}:
            # [NEW] Weekend filter: Mimic Forex hours (Friday 5PM EST to Sunday 5PM EST)
            mp_class = getattr(self.market_provider, "__class__", None).__name__ if hasattr(self, "market_provider") else ""
            is_replay = os.getenv("IS_REPLAY_MODE", "0") == "1" or mp_class == "ReplayMarketProvider"
            is_synthetic = os.getenv("SYNTHETIC_FIRE", "0") == "1" or mp_class == "SyntheticMarketProvider"
            if not is_replay and not is_synthetic:
                try:
                    import zoneinfo
                    est_tz = zoneinfo.ZoneInfo("America/New_York")
                    now_est = self._now().astimezone(est_tz)
                    is_weekend_block = False
                    if now_est.weekday() == 4 and now_est.hour >= 17:
                        is_weekend_block = True
                    elif now_est.weekday() == 5:
                        is_weekend_block = True
                    elif now_est.weekday() == 6 and now_est.hour < 17:
                        is_weekend_block = True
                        
                    if is_weekend_block:
                        logger.info(f"[PAPER] [WEEKEND BLOCK] Rejecting trade for {symbol}. Forex market is closed (5PM Friday - 5PM Sunday EST).")
                        self._update_status("warning", "Forex market is closed (weekend)")
                        return (
                            ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: Forex market closed"),
                            ExecutionOutcome(ExecutionOutcomeType.REJECTED, symbol, "Paper: Forex market closed", price=0.0)
                        )
                except Exception as e:
                    pass

            # [NEW] Bankruptcy Check — block entries if equity is zero or negative
            current_equity = self.get_total_equity()
            if current_equity <= 0:
                logger.error(
                    f"[PAPER] [BANKRUPT] {symbol}: blocked {action}, "
                    f"account equity is negative (${current_equity:.2f})"
                )
                self._update_status("critical", "Account equity is negative (Bankrupt)")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: account bankrupt"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_INSUFFICIENT_EQUITY, symbol, "Paper: account bankrupt")
                )

            # Skip if we already have a position in this symbol
            if symbol in self.positions:
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, f"Paper: already holding {symbol}"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, f"Paper: duplicate entry blocked")
                )

            # Re-entry cooldown — prevent churning after SL/TP exits
            if symbol in self._exit_cooldowns:
                now_ts = self._now().timestamp()
                elapsed = now_ts - self._exit_cooldowns[symbol]
                remaining = self.REENTRY_COOLDOWN - elapsed
                if remaining > 0:
                    logger.info(
                        f"[PAPER] [COOLDOWN] {symbol}: blocked re-entry, "
                        f"{remaining:.0f}s remaining of {self.REENTRY_COOLDOWN:.0f}s cooldown",
                        extra={"broker": "paper", "symbol": symbol, "event": "cooldown", "remaining_s": remaining}
                    )
                    return (
                        ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, f"Paper: cooldown {remaining:.0f}s"),
                        ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, f"Paper: re-entry cooldown active")
                    )
                else:
                    del self._exit_cooldowns[symbol]

            side = "buy" if action == "enter_long" else "sell"
            
            # Dynamic Paper Sizing
            sizing_capital = self.get_total_equity()
                
            risk_pct = getattr(decision, "risk_per_trade_pct", None) or getattr(self.profile, "risk_per_trade_pct", 0.01)
            
            # Dollar override always wins
            risk_dollars = float(getattr(decision, "risk_per_trade_dollars", 0.0) or getattr(self.profile, "risk_per_trade_dollars", 0.0))
            if risk_dollars > 0:
                risk_usd = risk_dollars
            else:
                risk_usd = sizing_capital * float(risk_pct)
            
            # ── Minimum Stop Distance (parity with backtester) ──────────
            # The backtester enforces a 0.15% minimum stop so that strategy
            # entries with absurdly tight stops (3-7 pips on EURUSD when
            # ATR-minimum should be ~18 pips) are widened to realistic
            # distances.  Without this, 5m candle noise hits the stop in
            # 1-2 bars (10 minutes), producing a 86% "Hard Stop Loss Hit"
            # ratio.  This is the #1 parity gap between backtester and
            # paper trading.
            if decision.stop_loss and abs(price - decision.stop_loss) > 1e-6:
                risk_per_unit = abs(price - decision.stop_loss)
                min_stop_distance = price * 0.0010  # 0.10% of entry (~10 pips, harmonized with strategy)
                if risk_per_unit < min_stop_distance:
                    target_r_cfg = float(getattr(self.profile, 'target_r', 2.5))
                    logger.warning(
                        f"[PAPER] [STOP-WIDEN] {symbol}: Stop too tight "
                        f"(${risk_per_unit:.5f} < ${min_stop_distance:.5f}), "
                        f"widening to minimum (rescaling TP to {target_r_cfg}R)"
                    )
                    risk_per_unit = min_stop_distance
                    if action == "enter_long":
                        decision.stop_loss = price - min_stop_distance
                        decision.take_profit = price + (min_stop_distance * target_r_cfg)
                    else:
                        decision.stop_loss = price + min_stop_distance
                        decision.take_profit = price - (min_stop_distance * target_r_cfg)
                qty = risk_usd / risk_per_unit
            else:
                # Fallback: Treat risk_usd as the actual notional size (very conservative for paper)
                qty = risk_usd / price if price > 0 else 0

            # [PHASE 2.2] Apply High-Net-Worth / Large Balance Tiered Restrictions
            qty, tier_slip_bps, is_blocked, block_reason = self._apply_high_net_worth_restrictions(
                symbol, action, price, sizing_capital, qty, decision, existing_notional=0.0
            )
            if is_blocked:
                self._update_status("warning", f"Restriction: {block_reason}")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, f"Paper: {block_reason}"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, f"Paper: {block_reason}")
                )

            # ── FLOOR SIZING PROTECTION ──
            is_crypto = False
            try:
                from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
                is_crypto = classify_symbol(symbol) == AssetClass.CRYPTO
            except Exception:
                is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "ADA", "LTC"])

            min_unit = 0.0001 if is_crypto else 1.0
            matched = False

            min_units_dict = getattr(self.profile, "min_units", None) or getattr(self.profile, "min_unit", None)
            if min_units_dict and isinstance(min_units_dict, dict):
                sym_clean = symbol.upper().replace("_", "").replace("/", "")
                for k, v in min_units_dict.items():
                    k_clean = k.upper().replace("_", "").replace("/", "")
                    if k_clean == sym_clean:
                        min_unit = float(v)
                        matched = True
                        break
                if not matched:
                    g_def = min_units_dict.get("DEFAULT", min_units_dict.get("default"))
                    if g_def is not None:
                        g_def_val = float(g_def)
                        if not is_crypto or g_def_val < 1.0:
                            min_unit = g_def_val
            else:
                # Fallback to check global config
                try:
                    import json
                    from tradebot_sci import paths
                    with open(paths.CONFIG_FILE, "r") as f:
                        cf = json.load(f)
                        g_min = cf.get("global", {}).get("min_units") or cf.get("global", {}).get("min_unit")
                        if g_min and isinstance(g_min, dict):
                            sym_clean = symbol.upper().replace("_", "").replace("/", "")
                            for k, v in g_min.items():
                                k_clean = k.upper().replace("_", "").replace("/", "")
                                if k_clean == sym_clean:
                                    min_unit = float(v)
                                    matched = True
                                    break
                            if not matched:
                                g_def = g_min.get("DEFAULT", g_min.get("default"))
                                if g_def is not None:
                                    g_def_val = float(g_def)
                                    if not is_crypto or g_def_val < 1.0:
                                        min_unit = g_def_val
                except Exception:
                    pass

            below_action = getattr(self.profile, "below_min_unit_action", None)
            if not below_action:
                try:
                    import json
                    from tradebot_sci import paths
                    with open(paths.CONFIG_FILE, "r") as f:
                        below_action = json.load(f).get("global", {}).get("below_min_unit_action", "reject")
                except Exception:
                    below_action = "reject"
            below_action = below_action.lower()

            if qty < min_unit:
                if below_action == "round_up":
                    logger.warning(
                        f"[PAPER] [FLOOR SIZING] Qty {qty:.4f} is below min_unit {min_unit:.4f} for {symbol}. "
                        f"Rounding up to minimum lot size."
                    )
                    qty = min_unit
                else:
                    logger.warning(
                        f"[PAPER] [FLOOR SIZING] Qty {qty:.4f} is below min_unit {min_unit:.4f} for {symbol}. "
                        f"Rejecting entry as below min_unit floor."
                    )
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, f"below min_unit floor: {qty:.4f} < {min_unit}"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, f"below min_unit floor")
                    )

            # [DEBUG] Trace sizing pipeline
            logger.info(
                f"[PAPER] [SIZING DEBUG] {symbol}: sizing_capital=${sizing_capital:.2f}, "
                f"risk_pct={risk_pct}, risk_usd=${risk_usd:.2f}, price={price:.5f}, "
                f"SL={decision.stop_loss}, qty_before_cap={qty:.4f}, "
                f"notional_before_cap=${qty * price:,.0f}"
            )

            # [PHASE 2.3] Simulated Order Rejection (1% chance)
            import random
            if random.random() < 0.01:
                logger.warning(f"[PAPER] [REJECTED] {symbol}: simulated broker rejection (1% chance)")
                self._update_status("warning", "Simulated broker rejection")
                return (
                    ExecutionResult(ExecutionStatus.ERROR, symbol, "Simulated broker rejection"),
                    ExecutionOutcome(ExecutionOutcomeType.FAILED_OTHER, symbol, "Simulated broker rejection")
                )

            # Affordability guard: cap qty if notional exceeds leveraged REAL balance
            notional = qty * price
            profile_leverage = getattr(self.profile, "target_leverage", 1.0) or 1.0
            target_leverage = min(profile_leverage, self.PAPER_MAX_LEVERAGE)
            max_affordable_notional = self.balance * max(target_leverage, 1.0)
            if notional > max_affordable_notional * 1.01:
                max_affordable_qty = max_affordable_notional / price if price > 0 else 0.0
                logger.warning(
                    f"[PAPER] [AFFORDABILITY CAPPED] {symbol}: notional ${notional:,.0f} exceeds "
                    f"available leveraged balance ${max_affordable_notional:,.0f}, capping qty from {qty:.4f} to {max_affordable_qty:.4f}",
                    extra={"broker": "paper", "symbol": symbol, "event": "affordability_capped", "original_notional": notional, "capped_notional": max_affordable_notional, "balance": self.balance}
                )
                qty = max_affordable_qty
                notional = qty * price

            if qty <= 0:
                self._update_status("warning", "Paper position size too small")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper position size too small"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, "Paper size zero")
                )

            fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction(tier_slip_bps)
            if is_parity:
                # Parity Mode: use backtester equivalent fees and NO artificial spread
                fill_price = price
                fee_usd = abs(qty * fill_price) * self._get_taker_fee(symbol)
            else:
                # Custom UI Override Mode + Tiered Slippage Penalty
                fill_price = price * (1 + friction) if side == "buy" else price * (1 - friction)
                fee_usd = abs(qty * fill_price) * (fee_pct / 2.0)  # Half on entry

            fee_usd = convert_quote_to_usd(fee_usd, symbol, fill_price, self.market_provider)
            self.balance -= fee_usd  # Deduct taker fee immediately

            stop_loss_val = getattr(decision, "stop_loss", None)
            take_profit_val = getattr(decision, "take_profit", None)

            # [PHASE 2.1] Atomic Bracket Order Validation
            if not stop_loss_val or not take_profit_val:
                logger.error(f"[PAPER] [REJECTED] {symbol}: Missing SL({stop_loss_val}) or TP({take_profit_val}) for atomic order")
                self._update_status("error", "Missing SL/TP for atomic order")
                return (
                    ExecutionResult(ExecutionStatus.ERROR, symbol, "Missing bracket parameters"),
                    ExecutionOutcome(ExecutionOutcomeType.FAILED_OTHER, symbol, "Missing SL/TP")
                )

            initial_risk_val = abs(fill_price - stop_loss_val)

            self.positions[symbol] = {
                "symbol": symbol,
                "side": "long" if side == "buy" else "short",
                "size": qty if side == "buy" else -qty,
                "qty": qty, # Explicit qty for easier math
                "entry_price": fill_price,
                "avg_price": fill_price,
                "original_entry_price": fill_price,
                "initial_risk": initial_risk_val,
                "current_price": price,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
                "opened_at": self._wall_clock().isoformat(),
                "entry_time": self._now().isoformat(),
                "stop_loss": stop_loss_val,
                "take_profit": getattr(decision, "take_profit", None),
                "entry_fee": fee_usd,
                "strategy": getattr(decision, "strategy_name", None) or "unknown",
                "risk_usd": risk_usd,
                "mfe_usd": 0.0,
                "mae_usd": 0.0,
            }
            logger.info(
                f"[PAPER] [FILL] {symbol} {qty:.4f} @ {fill_price:.5f} "
                f"(mid={price:.5f}, spread+slip={friction*100:.2f}%, fee=${fee_usd:.4f}, Risk=${risk_usd:.2f})",
                extra={"broker": "paper", "symbol": symbol, "event": "order_filled",
                       "side": side, "qty": qty, "fill_price": fill_price,
                        "fee_usd": fee_usd, "risk_usd": risk_usd}
            )

            # [PHASE 1.1] Start emergency timeout timer on new position
            self._emergency_stop_timers[symbol] = self._now().timestamp()

            self._save_state()
            self._update_status("healthy", "")
            return (
                ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Paper {action} executed"),
                ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Paper {action}")
            )

        if action in {"close_position", "flatten"}:
            if symbol in self.positions:
                pos = self.positions.pop(symbol)
                entry_p = pos["entry_price"]
                opened_at_str = pos.get("opened_at", "")
                pos_side = pos.get("side", "long")

                fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction()
                if is_parity:
                    exit_p = price
                    fee_usd = abs(pos["qty"] * exit_p) * self._get_taker_fee(symbol)
                else:
                    exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                    fee_usd = abs(pos["qty"] * exit_p) * (fee_pct / 2.0)

                if pos_side == "long":
                    pnl_gross_raw = (exit_p - entry_p) * pos["size"]
                else:
                    pnl_gross_raw = (entry_p - exit_p) * pos["size"]

                pnl_gross = convert_quote_to_usd(pnl_gross_raw, symbol, exit_p, self.market_provider)
                fee_usd = convert_quote_to_usd(fee_usd, symbol, exit_p, self.market_provider)

                pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), pnl_gross)
                pos["mae_usd"] = min(pos.get("mae_usd", 0.0), pnl_gross)
                
                pnl_usd = pnl_gross - fee_usd
                self.balance += pnl_usd

                duration_secs, duration_str = self._compute_duration(pos)
                pnl_sign = "+" if pnl_usd >= 0 else "-"
                pnl_str = f"{pnl_sign}${abs(pnl_usd):.2f}"
                pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if pos["size"] else 0.0
                spread_cost = pos.get("entry_fee", 0.0) + fee_usd
                exit_reason = decision.notes or "paper_close"

                logger.info(
                    f"[PAPER] [EXIT] Paper {exit_reason}: {symbol} {pnl_str} "
                    f"(Pct={pnl_pct:.2f}%) position={pos_side.upper()} | "
                    f"Entry={entry_p:.5f} Exit={exit_p:.5f} | "
                    f"Duration={duration_str} | "
                    f"Est. Spread Cost: ${spread_cost:.2f} | "
                    f"MFE=${pos.get('mfe_usd', 0.0):.2f} MAE=${pos.get('mae_usd', 0.0):.2f}",
                    extra={"broker": "paper", "symbol": symbol, "event": "order_closed",
                           "exit_price": exit_p, "pnl_usd": pnl_usd, "fee_usd": fee_usd}
                )

                # Record in trade results store
                if self.trade_results:
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=self._wall_clock().isoformat(),
                        pnl_pct=(pnl_usd / (entry_p * abs(pos["size"]))) * 100 if pos["size"] else 0,
                        pnl_usd=pnl_usd,
                        is_win=pnl_usd > 0,
                        tier="100%",
                        capital_at_close=self.balance,
                        opened_at=opened_at_str,
                        duration_seconds=duration_secs,
                        strategy=pos.get("strategy", "unknown"),
                        exit_reason=decision.notes or "paper_close",
                        side=pos_side,
                        spread_cost=pos.get("entry_fee", 0.0) + fee_usd,
                        mfe_usd=pos.get("mfe_usd", 0.0),
                        mae_usd=pos.get("mae_usd", 0.0),
                    ))

                self._exit_cooldowns[symbol] = self._now().timestamp()
                SafetyGuard.register_trade_completion(symbol, pnl_usd > 0, sim_time=self._now())
                self._save_state()
                self.refresh_account_summary()
                self._update_status("healthy", "")
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, symbol, "Paper flatten executed"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, "Paper flatten")
                )

        if action == "scale_out":
            if symbol in self.positions:
                pos = self.positions[symbol]
                entry_p = pos["entry_price"]
                opened_at_str = pos.get("opened_at", "")
                pos_side = pos.get("side", "long")

                # Determine fraction to close
                scale_frac = getattr(decision, "scale_out_fraction", None)
                if scale_frac is None:
                    # Parse from notes: "...|scale_frac=0.80|..."
                    notes = decision.notes or ""
                    import re
                    m = re.search(r"scale_frac=([\d.]+)", notes)
                    scale_frac = float(m.group(1)) if m else 0.80

                close_qty = abs(pos["qty"]) * scale_frac
                remain_qty = abs(pos["qty"]) - close_qty

                fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction()
                if is_parity:
                    exit_p = price
                    fee_usd = close_qty * exit_p * self._get_taker_fee(symbol)
                else:
                    exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                    fee_usd = close_qty * exit_p * (fee_pct / 2.0)

                pnl_gross_raw = (exit_p - entry_p) * (close_qty if pos_side == "long" else -close_qty)
                pnl_gross = convert_quote_to_usd(pnl_gross_raw, symbol, exit_p, self.market_provider)
                fee_usd = convert_quote_to_usd(fee_usd, symbol, exit_p, self.market_provider)

                pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), pnl_gross)
                pos["mae_usd"] = min(pos.get("mae_usd", 0.0), pnl_gross)
                
                pnl_usd = pnl_gross - fee_usd
                self.balance += pnl_usd

                duration_secs, duration_str = self._compute_duration(pos)
                pnl_sign = "+" if pnl_usd >= 0 else "-"
                pnl_str = f"{pnl_sign}${abs(pnl_usd):.2f}"
                pnl_pct = (pnl_usd / (entry_p * close_qty)) * 100 if close_qty else 0.0
                spread_cost = (pos.get("entry_fee", 0.0) * scale_frac) + fee_usd
                exit_reason = decision.notes or "paper_scale_out"

                logger.info(
                    f"[PAPER] [EXIT] Paper {exit_reason}: {symbol} {pnl_str} "
                    f"(Pct={pnl_pct:.2f}%) position={pos_side.upper()} | "
                    f"Entry={entry_p:.5f} Exit={exit_p:.5f} | "
                    f"Duration={duration_str} | "
                    f"Est. Spread Cost: ${spread_cost:.2f} | "
                    f"MFE=${pos.get('mfe_usd', 0.0):.2f} MAE=${pos.get('mae_usd', 0.0):.2f}",
                    extra={"broker": "paper", "symbol": symbol, "event": "scale_out",
                           "exit_price": exit_p, "pnl_usd": pnl_usd, "fee_usd": fee_usd,
                           "scale_frac": scale_frac, "remain_qty": remain_qty}
                )

                # Record partial close as trade result
                if self.trade_results:
                    pnl_pct = (pnl_usd / (entry_p * close_qty)) * 100 if close_qty else 0
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=self._wall_clock().isoformat(),
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        is_win=pnl_usd > 0,
                        tier=f"{scale_frac:.0%}",
                        capital_at_close=self.balance,
                        opened_at=opened_at_str,
                        duration_seconds=duration_secs,
                        strategy=pos.get("strategy", "unknown"),
                        exit_reason=decision.notes or "paper_scale_out",
                        side=pos_side,
                        spread_cost=(pos.get("entry_fee", 0.0) * scale_frac) + fee_usd,
                        mfe_usd=pos.get("mfe_usd", 0.0),
                        mae_usd=pos.get("mae_usd", 0.0),
                    ))

                # Update or remove position
                if remain_qty < 1e-6:
                    del self.positions[symbol]
                    self._exit_cooldowns[symbol] = self._now().timestamp()
                else:
                    pos["qty"] = remain_qty
                    pos["size"] = remain_qty if pos_side == "long" else -remain_qty

                self._save_state()
                self.refresh_account_summary()
                self._update_status("healthy", "")
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Paper scale_out {scale_frac:.0%}"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Paper scale_out {scale_frac:.0%}")
                )
        
        if action == "scale_in":
            if symbol in self.positions:
                # [NEW] Bankruptcy Check for pyramiding
                current_equity = self.get_total_equity()
                if current_equity <= 0:
                    logger.error(f"[PAPER] [BANKRUPT] {symbol}: blocked scale_in, account equity is negative (${current_equity:.2f})")
                    self._update_status("critical", "Account equity is negative (Bankrupt)")
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: account bankrupt (pyramid)"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_INSUFFICIENT_EQUITY, symbol, "Paper: account bankrupt (pyramid)")
                    )

                pos = self.positions[symbol]
                side = "buy" if pos["side"] == "long" else "sell"
                
                # Dynamic Paper Sizing
                # BUGFIX: my decision.risk_per_trade_pct for pyramids is a multiplier of the BASE RISK,
                # NOT a percentage of the entire account capital!
                base_risk_pct = getattr(self.profile, "risk_per_trade_pct", 0.01)
                base_risk_usd = self._initial_balance * base_risk_pct
                
                scale_fraction = getattr(decision, "risk_per_trade_pct", None)
                if scale_fraction is not None:
                    risk_usd = base_risk_usd * float(scale_fraction)
                else:
                    risk_usd = base_risk_usd * float(getattr(self.profile, "conductor_pyramid_subsequent_pct", 0.5))
                
                # Use the ORIGINAL risk distance for pyramiding to prevent breakeven slippage bombs
                original_risk_dist = pos.get("initial_risk")
                if original_risk_dist and original_risk_dist > 1e-6:
                    risk_per_unit = original_risk_dist
                    qty = risk_usd / risk_per_unit
                elif decision.stop_loss and abs(price - decision.stop_loss) > 1e-6:
                    risk_per_unit = abs(price - decision.stop_loss)
                    qty = risk_usd / risk_per_unit
                else:
                    qty = risk_usd / price if price > 0 else 0
                
                # [PHASE 2.2] Apply High-Net-Worth / Large Balance Tiered Restrictions
                existing_notional = pos["qty"] * price
                sizing_capital = self.get_total_equity()
                qty, tier_slip_bps, is_blocked, block_reason = self._apply_high_net_worth_restrictions(
                    symbol, action, price, sizing_capital, qty, decision, existing_notional=existing_notional
                )
                if is_blocked:
                    self._update_status("warning", f"Restriction: {block_reason}")
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, f"Paper: {block_reason}"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, f"Paper: {block_reason}")
                    )

                fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction(tier_slip_bps)
                if is_parity:
                    fill_price = price
                    fee_usd = abs(qty * fill_price) * self._get_taker_fee(symbol)
                else:
                    fill_price = price * (1 + friction) if side == "buy" else price * (1 - friction)
                    fee_usd = abs(qty * fill_price) * (fee_pct / 2.0)

                fee_usd = convert_quote_to_usd(fee_usd, symbol, fill_price, self.market_provider)
                self.balance -= fee_usd
                
                # Update position sizing and avg_price
                old_qty = pos["qty"]
                old_avg = pos["avg_price"]
                new_qty = old_qty + qty
                new_avg = ((old_qty * old_avg) + (qty * fill_price)) / new_qty
                
                pos["qty"] = new_qty
                pos["size"] = new_qty if side == "buy" else -new_qty
                pos["avg_price"] = new_avg
                # Do not change entry_price (original) but update stop_loss if provided
                if decision.stop_loss:
                    pos["stop_loss"] = decision.stop_loss
                if decision.take_profit:
                    pos["take_profit"] = decision.take_profit
                    
                pos["entry_fee"] = pos.get("entry_fee", 0) + fee_usd
                pos["risk_usd"] = pos.get("risk_usd", 0.0) + risk_usd

                logger.info(
                    f"[PAPER] [SCALE_IN] {symbol} {qty:.4f} @ {fill_price:.5f} "
                    f"(mid={price:.5f}, new_avg={new_avg:.5f}, new_qty={new_qty:.4f}, Risk=${risk_usd:.2f})",
                    extra={"broker": "paper", "symbol": symbol, "event": "scale_in",
                           "side": side, "qty": qty, "fill_price": fill_price,
                           "fee_usd": fee_usd, "risk_usd": risk_usd}
                )
                self._save_state()
                self._update_status("healthy", "")
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Paper scale_in executed"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Paper scale_in")
                )
            else:
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, "Paper scale_in: no position"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, "scale_in no position")
                )
        
        return (
            ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, "Paper stand aside"),
            ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, "Paper stand aside")
        )

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        pos = self.positions.get(symbol)
        if pos:
            # Update current price and PNL
            price = self._get_current_price(symbol)
            pos["current_price"] = price
            unrealized_pnl_raw = (price - pos["entry_price"]) * pos["size"]
            pos["unrealized_pnl"] = convert_quote_to_usd(unrealized_pnl_raw, symbol, price, self.market_provider)
            pos["pnl_pct"] = (unrealized_pnl_raw / (pos["entry_price"] * abs(pos["size"]))) * 100 if pos["size"] else 0.0
        return pos

    def list_open_position_symbols(self) -> List[str]:
        return list(self.positions.keys())

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        pass

    def flatten_symbol(self, symbol: str) -> None:
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            entry_p = pos["entry_price"]
            pos_side = pos.get("side", "long")
            price = self._get_current_price(symbol)

            fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction()
            if is_parity:
                exit_p = price
                fee_usd = abs(pos["qty"] * exit_p) * self._get_taker_fee(symbol)
            else:
                exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                fee_usd = abs(pos["qty"] * exit_p) * (fee_pct / 2.0)

            pnl_gross_raw = (exit_p - entry_p) * pos["size"]
            pnl_gross = convert_quote_to_usd(pnl_gross_raw, symbol, exit_p, self.market_provider)
            fee_usd = convert_quote_to_usd(fee_usd, symbol, exit_p, self.market_provider)
            pnl_usd = pnl_gross - fee_usd
            self.balance += pnl_usd

            duration_secs, duration_str = self._compute_duration(pos)
            if pnl_usd > 0:
                pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), pnl_usd)
            else:
                pos["mae_usd"] = min(pos.get("mae_usd", 0.0), pnl_usd)

            pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 and pos["size"] != 0 else 0.0
            pnl_sign = "+" if pnl_usd >= 0 else "-"
            pnl_str = f"{pnl_sign}${abs(pnl_usd):.2f}"
            entry_fee = abs(pos.get("entry_fee", 0))
            spread_cost = entry_fee + fee_usd

            logger.info(
                f"[PAPER] [EXIT] Paper Manual Cash-Out: {symbol} {pnl_str} "
                f"(Pct={pnl_pct:.2f}%) position={pos_side.upper()} | "
                f"Entry={entry_p:.5f} Exit={exit_p:.5f} | "
                f"Duration={duration_str} | "
                f"Est. Spread Cost: ${spread_cost:.2f} | "
                f"MFE=${pos.get('mfe_usd', 0.0):.2f} MAE=${pos.get('mae_usd', 0.0):.2f}"
            )

            # Record in trade results
            if self.trade_results:
                self.trade_results.add_result(TradeResult(
                    symbol=symbol,
                    closed_at=self._wall_clock().isoformat(),
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    is_win=pnl_usd > 0,
                    tier="100%",
                    capital_at_close=self.balance,
                    opened_at=pos.get("opened_at", ""),
                    duration_seconds=duration_secs,
                    strategy=pos.get("strategy", "unknown"),
                    exit_reason="manual_cash_out",
                    side=pos_side,
                    spread_cost=pos.get("entry_fee", 0.0) + fee_usd,
                    mfe_usd=pos.get("mfe_usd", 0.0),
                    mae_usd=pos.get("mae_usd", 0.0),
                ))

            self._exit_cooldowns[symbol] = self._now().timestamp()
            self._save_state()
            self.refresh_account_summary()

    def close_all_positions(self, reason: str = "Day Chain Reset") -> None:
        """Close all open positions at current market price.

        Called by loop.py when day-chaining to prevent stale positions
        from the previous replay day leaking into the next day's data.
        Records each closure in the trade result store with proper PnL.
        """
        symbols_to_close = list(self.positions.keys())
        if not symbols_to_close:
            return

        for symbol in symbols_to_close:
            pos = self.positions.pop(symbol)
            try:
                price = self._get_current_price(symbol)
            except Exception:
                price = pos.get("current_price", pos.get("entry_price", 0))

            entry_p = pos.get("entry_price", 0)
            pnl_usd = (price - entry_p) * pos["size"]
            fee_usd = abs(pos.get("qty", abs(pos["size"])) * price) * self._get_taker_fee(symbol)
            pnl_usd -= fee_usd
            self.balance += pnl_usd

            pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 else 0.0
            side = pos.get("side", "long")

            # Compute duration
            duration_secs = None
            entry_time_str = pos.get("entry_time", pos.get("opened_at", ""))
            if entry_time_str:
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str)
                    duration_secs = (self._now() - entry_dt).total_seconds()
                    if duration_secs < 0:
                        duration_secs = abs(duration_secs)
                except Exception:
                    pass

            pnl_sign = "+" if pnl_usd >= 0 else "-"
            logger.info(
                f"[PAPER] [DAY-CHAIN] {symbol}: Closed {side} {pnl_sign}${abs(pnl_usd):.2f} "
                f"({reason})"
            )

            if self.trade_results:
                self.trade_results.add_result(TradeResult(
                    symbol=symbol,
                    closed_at=self._wall_clock().isoformat(),
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    is_win=pnl_usd > 0,
                    tier="100%",
                    capital_at_close=self.balance,
                    opened_at=pos.get("opened_at", ""),
                    duration_seconds=duration_secs,
                    strategy=pos.get("strategy", "unknown"),
                    exit_reason=reason,
                    side=side,
                    spread_cost=pos.get("entry_fee", 0.0) + fee_usd,
                    mfe_usd=pos.get("mfe_usd", 0.0),
                    mae_usd=pos.get("mae_usd", 0.0),
                ))

        self._exit_cooldowns.clear()  # Reset cooldowns for new day
        self._save_state()
        self.refresh_account_summary()
        logger.info(f"[PAPER] [DAY-CHAIN] Closed {len(symbols_to_close)} positions for day chain")

    def should_block_for_hold(self, symbol, decision, open_position):
        return False, None, None

    def evaluate_synthetic_stops(self, market_provider, timeframe):
        """Check SL/TP for all open paper positions using intra-candle OHLC data.
        
        Uses candle HIGH/LOW for TP/SL detection (like real broker stop/limit orders)
        and exits at the exact SL/TP price, not the candle close.
        
        IMPORTANT: The Universal Exit Router runs BEFORE mechanical SL/TP checks.
        This mirrors the backtester fix — giving trend_invalidation, chandelier,
        time_decay, etc. a chance to close at bar-close price before the hard
        stop fires and deletes the position.
        """
        now_epoch = time.time()
        results = []
        for symbol in list(self.positions.keys()):
            # [PHASE 1.1] Emergency Stop Timeout Check — DISABLED for Paper Replay
            # We don't want wall-clock timers killing trades during synthetic replays.
            pass

            pos = self.positions[symbol]
            try:
                price = self._get_current_price(symbol)
            except Exception:
                continue

            # ── Get OHLC of the most recent candle for intra-bar evaluation ──
            candle_high = None
            candle_low = None
            candles_for_router = None
            if market_provider:
                try:
                    candles_for_router = market_provider.get_latest_candles(symbol, timeframe, limit=200)
                    if candles_for_router:
                        last_candle = candles_for_router[-1]
                        candle_high = float(last_candle.high)
                        candle_low = float(last_candle.low)
                except Exception:
                    pass

            # [PHASE 1.5] Update MFE/MAE (floating high/low pnl)
            side = pos.get("side", "long")
            entry_p = pos.get("entry_price", 0)
            
            # Use intra-candle extremes (high/low) OR current ticker price for highest granularity
            tick_price = price
            
            if side == "long":
                # MFE (Favorable) = High - Entry | MAE (Adverse) = Low - Entry
                best_price = max(tick_price, candle_high) if candle_high is not None else tick_price
                worst_price = min(tick_price, candle_low) if candle_low is not None else tick_price
                
                curr_mfe = best_price - entry_p
                curr_mae = worst_price - entry_p
                floating_fav = curr_mfe * abs(pos["size"])
                floating_adv = curr_mae * abs(pos["size"])
            else:
                # MFE (Favorable) = Entry - Low | MAE (Adverse) = Entry - High
                best_price = min(tick_price, candle_low) if candle_low is not None else tick_price
                worst_price = max(tick_price, candle_high) if candle_high is not None else tick_price
                
                curr_mfe = entry_p - best_price
                curr_mae = entry_p - worst_price
                floating_fav = curr_mfe * abs(pos["size"])
                floating_adv = curr_mae * abs(pos["size"])
            
            pos["mfe"] = max(pos.get("mfe", 0.0), curr_mfe)
            pos["mae"] = min(pos.get("mae", 0.0), curr_mae)
            floating_fav_usd = convert_quote_to_usd(floating_fav, symbol, price, self.market_provider)
            floating_adv_usd = convert_quote_to_usd(floating_adv, symbol, price, self.market_provider)
            unrealized_pnl_raw = (price - entry_p) * pos["size"]
            unrealized_pnl_usd = convert_quote_to_usd(unrealized_pnl_raw, symbol, price, self.market_provider)

            pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), floating_fav_usd)
            pos["mae_usd"] = min(pos.get("mae_usd", 0.0), floating_adv_usd)
            pos["unrealized_pnl"] = unrealized_pnl_usd

            # ════════════════════════════════════════════════════════════════
            # UNIVERSAL EXIT ROUTER — runs AFTER mechanical SL/TP
            # ════════════════════════════════════════════════════════════════
            # Gives trend_invalidation, chandelier, time_decay, etc. a chance
            # to close at bar-close price before the hard stop fires.
            # Without this, the SL deletes the position before engine.decide()
            # ever evaluates the exit router (same bug the backtester fixed).
            if candles_for_router and len(candles_for_router) >= 30:
                side = pos.get("side", "long")
                entry_time_str = pos.get("entry_time", "")
                _router_held_s = 0
                if entry_time_str:
                    try:
                        _entry_dt = datetime.fromisoformat(entry_time_str)
                        if _entry_dt.tzinfo is None:
                            _entry_dt = _entry_dt.replace(tzinfo=timezone.utc)
                        _now_dt = self._now()
                        if _now_dt.tzinfo is None:
                            _now_dt = _now_dt.replace(tzinfo=timezone.utc)
                        _router_held_s = (_now_dt - _entry_dt).total_seconds()
                    except Exception:
                        pass
                # Run the exit router for all active positions (age >= 0)
                if _router_held_s >= 0:
                    try:
                        from tradebot_sci.market.trend_consensus import detect_trend_direction
                        from tradebot_sci.strategy.exit_logic import run_universal_exit_logic
                        from tradebot_sci.market.models import MarketSnapshot, TrendState

                        # Build a snapshot for the exit router
                        _neutral = TrendState(direction="neutral", strength=0.0)
                        _router_snapshot = None
                        if market_provider:
                            try:
                                _router_snapshot = market_provider.get_latest_snapshot(symbol, timeframe)
                            except Exception:
                                pass
                        if not _router_snapshot:
                            _router_snapshot = MarketSnapshot(
                                symbol=symbol,
                                timeframe=timeframe,
                                candles=candles_for_router,
                                trend_htf=_neutral,
                                trend_ltf=_neutral,
                            )

                        # Build gates via trend_consensus (same path as engine.decide)
                        _consensus = detect_trend_direction(
                            _router_snapshot.candles, self.profile,
                            htf_candles=getattr(_router_snapshot, 'htf_candles', None),
                            mtf_candles=getattr(_router_snapshot, 'mtf_candles', None),
                            ltf_candles=getattr(_router_snapshot, 'ltf_candles', None),
                        )
                        _router_gates = {
                            "exec_dir": _consensus.exec_dir,
                            "ltf_dir": _consensus.ltf_dir,
                            "mtf_dir": _consensus.mtf_dir,
                            "htf_dir": _consensus.htf_dir,
                        }
                        _router_pos = {
                            'symbol': symbol,
                            'direction': side,
                            'entry_price': pos.get("entry_price", 0),
                            'size': pos.get("size", 0),
                            'stop_price': pos.get("stop_loss"),
                            'stop_loss': pos.get("stop_loss"),
                        'take_profit': pos.get("take_profit"),
                            'entry_time': entry_time_str,
                            'initial_risk': pos.get("initial_risk"),
                            'mfe': pos.get("mfe", 0.0),
                            'mfe_usd': pos.get("mfe_usd", 0.0),
                            'mae': pos.get("mae", 0.0),
                            'mae_usd': pos.get("mae_usd", 0.0),
                            'unrealized_pnl': pos.get("unrealized_pnl", 0.0),
                        }
                        _router_decision = run_universal_exit_logic(
                            snapshot=_router_snapshot,
                            open_position=_router_pos,
                            gates=_router_gates,
                            profile=self.profile,
                            strategy_name=pos.get("strategy", "unknown"),
                        )
                        if _router_decision and getattr(_router_decision, 'action', '') == 'close_position':
                            _router_reason = getattr(_router_decision, 'notes', None) or 'invalidation'
                            
                            if _router_reason == "Hard Stop Loss Hit":
                                # Delegate precise execution to the mechanical SL/TP block below 
                                # instead of exiting at the inaccurate 5m candle close price.
                                pass
                            else:
                                # Apply Hold Guards parity with engine.py
                                is_emergency = getattr(_router_decision, 'emergency_exit', False)
                                hold_guard_enabled = getattr(self.profile, 'enable_hold_guard', True)
                                hold_guard_seconds = int(getattr(self.profile, 'hold_guard_seconds', 900))
                                position_is_young = (hold_guard_enabled and _router_held_s < hold_guard_seconds)

                                enable_negative_hold_guard = getattr(self.profile, 'enable_negative_hold_guard', True)
                                negative_hold_seconds = int(getattr(self.profile, 'negative_hold_seconds', 2700))
                                
                                is_negative = False
                                entry_p = pos.get("entry_price", 0)
                                if enable_negative_hold_guard:
                                    if side == "long":
                                        is_negative = price < entry_p
                                    else:
                                        is_negative = price > entry_p
                                
                                neg_hold_blocked = (
                                    enable_negative_hold_guard
                                    and is_negative
                                    and _router_held_s < negative_hold_seconds
                                )

                                enable_spread_profit_guard = getattr(self.profile, 'enable_spread_profit_guard', True)
                                spread_profit_blocked = False
                                if enable_spread_profit_guard:
                                    fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction()
                                    qty = pos.get("qty", abs(pos["size"]))
                                    if is_parity:
                                        taker_fee = self._get_taker_fee(symbol)
                                        est_spread_usd = abs(qty * price) * taker_fee
                                    else:
                                        est_spread_usd = abs(qty * price) * (fee_pct / 2.0)
                                    
                                    if unrealized_pnl_usd > 0 and unrealized_pnl_usd < est_spread_usd:
                                        spread_profit_blocked = True

                                if (position_is_young or neg_hold_blocked or spread_profit_blocked) and not is_emergency:
                                    if spread_profit_blocked:
                                        block_reason = "spread profit guard"
                                        block_limit_str = f"PnL ${unrealized_pnl_usd:.2f} < Est. Spread Cost ${est_spread_usd:.2f}"
                                    else:
                                        block_reason = "negative hold" if neg_hold_blocked else "hold guard"
                                        block_limit = negative_hold_seconds if neg_hold_blocked else hold_guard_seconds
                                        block_limit_str = f"age {_router_held_s:.0f}s < {block_limit}s"
                                    logger.info(
                                        f"[PAPER HOLD GUARD] {symbol} strategy exit BLOCKED — "
                                        f"{block_limit_str} "
                                        f"(non-emergency exits blocked during {block_reason}). "
                                        f"Reason: {_router_reason}"
                                    )
                                    # Fall through to mechanical stops (do not exit here)
                                else:
                                    if is_emergency and (position_is_young or neg_hold_blocked or spread_profit_blocked):
                                        logger.info(
                                            f"[PAPER HOLD GUARD] {symbol} EMERGENCY EXIT allowed — "
                                            f"bypassed hold/negative/spread profit guards"
                                        )
                                    # Exit router wants to close via strategy — do it at bar close price
                                    _exit_price = candles_for_router[-1].close if candles_for_router else price
                                    entry_p = pos.get("entry_price", 0)
                                    pnl_usd = (_exit_price - entry_p) * pos["size"]
                                    fee_usd = abs(pos.get("qty", abs(pos["size"])) * _exit_price) * self._get_taker_fee(symbol)
                                    pnl_usd -= fee_usd
                                    self.balance += pnl_usd
                                    
                                    # Duration
                                    duration_secs, duration_str = self._compute_duration(pos)
                                    
                                    if pnl_usd > 0:
                                        pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), pnl_usd)
                                    else:
                                        pos["mae_usd"] = min(pos.get("mae_usd", 0.0), pnl_usd)

                                    pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 else 0.0
                                    pnl_sign = "+" if pnl_usd >= 0 else "-"
                                    pnl_str = f"{pnl_sign}${abs(pnl_usd):.2f}"
                                    
                                    entry_fee = abs(pos.get("entry_fee", 0))
                                    spread_cost = entry_fee + fee_usd
        
                                    logger.info(
                                        f"[PAPER] [EXIT] Paper INVALIDATION: {symbol} {pnl_str} "
                                        f"(Pct={pnl_pct:.2f}%) position={side.upper()} | "
                                        f"Entry={entry_p:.5f} Exit={_exit_price:.5f} | "
                                        f"Duration={duration_str} | "
                                        f"Est. Spread Cost: ${spread_cost:.2f} | "
                                        f"MFE=${pos.get('mfe_usd', 0.0):.2f} MAE=${pos.get('mae_usd', 0.0):.2f} | {_router_reason}"
                                    )
        
                                    if self.trade_results:
                                        self.trade_results.add_result(TradeResult(
                                            symbol=symbol,
                                            closed_at=self._wall_clock().isoformat(),
                                            pnl_pct=pnl_pct,
                                            pnl_usd=pnl_usd,
                                            is_win=pnl_usd > 0,
                                            tier="100%",
                                            capital_at_close=self.balance,
                                            opened_at=pos.get("opened_at", ""),
                                            duration_seconds=duration_secs,
                                            strategy=pos.get("strategy", "unknown"),
                                            exit_reason=_router_reason,
                                            side=side,
                                            spread_cost=pos.get("entry_fee", 0.0) + fee_usd,
                                            mfe_usd=pos.get("mfe_usd", 0.0),
                                            mae_usd=pos.get("mae_usd", 0.0),
                                        ))
        
                                    del self.positions[symbol]
                                    self._exit_cooldowns[symbol] = self._now().timestamp()
                                    SafetyGuard.register_trade_completion(symbol, pnl_usd > 0, sim_time=self._now())
                                    self._save_state()
                                    self.refresh_account_summary()
                                    results.append(ExecutionResult(
                                        ExecutionStatus.EXIT_SIGNAL, symbol,
                                        f"Paper INVALIDATION exit PnL={pnl_usd:.2f}"
                                    ))
                                    continue  # Skip SL/TP check — position already closed

                        elif _router_decision and getattr(_router_decision, 'action', '') == 'hold' and _router_decision.stop_loss is not None:
                            # Trailing stop update from router (chandelier, ratchet)
                            old_sl = pos.get("stop_loss")
                            new_sl = _router_decision.stop_loss
                            if old_sl != new_sl:
                                pos["stop_loss"] = new_sl
                                logger.info(f"[PAPER] {symbol} Router trail: stop {old_sl} → {new_sl}")

                    except Exception as _router_err:
                        logger.debug(f"[PAPER] Universal exit router error for {symbol}: {_router_err}")

            # ════════════════════════════════════════════════════════════════
            # MECHANICAL SL/TP CHECK — only if exit router didn't close
            # ════════════════════════════════════════════════════════════════
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            side = pos.get("side", "long")
            entry_p = pos.get("entry_price", 0)
            hit = None
            exit_price = price  # Default to close price

            fee_pct, spread_pct, slip_pct, friction, is_parity = self._get_paper_friction()

            if side == "long":
                # SL: use candle LOW (worst intra-bar price against long)
                check_sl = candle_low if candle_low is not None else price
                # TP: use candle HIGH (best intra-bar price for long)
                check_tp = candle_high if candle_high is not None else price
                
                check_sl_bid = check_sl * (1 - friction)
                check_tp_bid = check_tp * (1 - friction)

                if sl and check_sl_bid <= sl:
                    hit = "SL"
                    exit_price = sl * (1 - friction) if not is_parity else sl
                elif tp and tp > entry_p and check_tp_bid >= tp:
                    hit = "TP"
                    exit_price = tp # Limit orders fill at exact price without spread penalty
                elif tp and tp <= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} <= entry {entry_p} for LONG — ignoring TP")
            else:  # short
                # SL: use candle HIGH (worst intra-bar price against short)
                check_sl = candle_high if candle_high is not None else price
                # TP: use candle LOW (best intra-bar price for short)
                check_tp = candle_low if candle_low is not None else price
                
                check_sl_ask = check_sl * (1 + friction)
                check_tp_ask = check_tp * (1 + friction)

                if sl and check_sl_ask >= sl:
                    hit = "SL"
                    exit_price = sl * (1 + friction) if not is_parity else sl
                elif tp and tp < entry_p and check_tp_ask <= tp:
                    hit = "TP"
                    exit_price = tp # Limit orders fill at exact price without spread penalty
                elif tp and tp >= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} >= entry {entry_p} for SHORT — ignoring TP")

            if hit:
                # exit_price already set to exact SL/TP level from OHLC evaluation above
                pnl_usd = (exit_price - entry_p) * pos["size"]
                if is_parity:
                    fee_usd = abs(pos.get("qty", abs(pos["size"])) * exit_price) * self._get_taker_fee(symbol)
                else:
                    fee_usd = abs(pos.get("qty", abs(pos["size"])) * exit_price) * (fee_pct / 2.0)
                pnl_usd -= fee_usd
                
                if pnl_usd > 0:
                    pos["mfe_usd"] = max(pos.get("mfe_usd", 0.0), pnl_usd)
                else:
                    pos["mae_usd"] = min(pos.get("mae_usd", 0.0), pnl_usd)

                pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 else 0.0
                self.balance += pnl_usd
                # Format PnL as +$X.XX or -$X.XX (sign BEFORE dollar)
                # so the LedgerDaemon RE_EXIT regex can parse it for analytics.
                pnl_sign = "+" if pnl_usd >= 0 else "-"
                pnl_str = f"{pnl_sign}${abs(pnl_usd):.2f}"

                # Spread cost = entry fee + exit fee (round-trip friction)
                entry_fee = abs(pos.get("entry_fee", 0))
                spread_cost = entry_fee + fee_usd

                # Compute trade duration
                duration_secs, duration_str = self._compute_duration(pos)

                logger.info(
                    f"[PAPER] [EXIT] Paper {hit}: {symbol} {pnl_str} "
                    f"(Pct={pnl_pct:.2f}%) position={side.upper()} | "
                    f"Entry={entry_p:.5f} Exit={exit_price:.5f} | "
                    f"Duration={duration_str} | "
                    f"Est. Spread Cost: ${spread_cost:.2f} | "
                    f"MFE=${pos.get('mfe_usd', 0.0):.2f} MAE=${pos.get('mae_usd', 0.0):.2f}"
                )

                # Record in paper-specific TradeResultStore (not the live one).
                # The PaperBroker receives a separate store (paper_trade_results.json)
                # so paper PnL never pollutes the live sidebar stats.
                if self.trade_results:
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=self._wall_clock().isoformat(),
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        is_win=pnl_usd > 0,
                        tier="100%",
                        capital_at_close=self.balance,
                        opened_at=opened_at_str,
                        duration_seconds=duration_secs,
                        strategy=pos.get("strategy", "unknown"),
                        exit_reason=f"paper_{hit.lower()}" if hit else "paper_exit",
                        side=side,
                        spread_cost=pos.get("entry_fee", 0.0) + fee_usd,
                        mfe_usd=pos.get("mfe_usd", 0.0),
                        mae_usd=pos.get("mae_usd", 0.0),
                    ))

                del self.positions[symbol]
                self._exit_cooldowns[symbol] = self._now().timestamp()  # Start re-entry cooldown
                SafetyGuard.register_trade_completion(symbol, pnl_usd > 0, pnl_usd=pnl_usd, sim_time=self._now())
                self._save_state()
                self.refresh_account_summary()
                results.append(ExecutionResult(
                    ExecutionStatus.EXIT_SIGNAL, symbol,
                    f"Paper {hit} exit PnL={pnl_usd:.2f}"
                ))

        # Refresh unrealized PnL for surviving positions so paper_state.json
        # stays current for the GUI analytics panel (trade history active PnL).
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            try:
                cur = self._get_current_price(sym)
                pos["current_price"] = cur
                unrealized_pnl_raw = (cur - pos["entry_price"]) * pos["size"]
                pos["unrealized_pnl"] = convert_quote_to_usd(unrealized_pnl_raw, sym, cur, self.market_provider)
                pos["pnl_pct"] = (unrealized_pnl_raw / (pos["entry_price"] * abs(pos["size"]))) * 100 if pos["size"] else 0.0
            except Exception:
                pass
        self._save_state()

        return results

    def summarize_pnl(self):
        logger.info(f"Session summary: Balance=${self.balance:.2f}, Open positions={len(self.positions)}")
        self._save_state()

    def reset(self, initial_balance: float = 10000.0) -> None:
        """Reset the paper broker to a clean state."""
        self.positions.clear()
        self._exit_cooldowns.clear()
        self._emergency_stop_timers.clear()
        self.balance = initial_balance
        self._initial_balance = initial_balance
        if self.trade_results:
            self.trade_results.clear()
        self._save_state()
        self._update_status("healthy", "")
        logger.info(f"[PAPER] Reset Paper Broker to clean state with balance ${initial_balance:.2f}")

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        return symbol in self.positions

    def sync_profile(self, profile):
        self.profile = profile

    @property
    def position_hold_store(self):
        return None

