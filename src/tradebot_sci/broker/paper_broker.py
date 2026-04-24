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
from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass

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

    # Hard leverage cap for paper trading.
    # Profile target_leverage (e.g. 50x) is for OANDA forex — way too high for
    # crypto paper trading.  Cap at 3x to prevent catastrophic position sizing.
    PAPER_MAX_LEVERAGE = float(os.getenv("PAPER_MAX_LEVERAGE", "50.0"))
    
    def __init__(self, profile_settings, market_provider=None, trade_results=None, initial_balance=10000.0):
        self.profile = profile_settings
        self.market_provider = market_provider
        self.trade_results = trade_results
        self.positions = {} # symbol -> position_dict
        self.history = []
        self._exit_cooldowns = {}  # symbol -> timestamp of last exit
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
            if sim_time is not None:
                return sim_time
        return datetime.now(timezone.utc)

    def _wall_clock(self) -> datetime:
        """Return real wall-clock UTC time for display timestamps.

        Used for opened_at/closed_at in trade results so the Trade History
        shows when trades actually happened, not the replay candle time
        (which races ahead of real time in turbo mode).
        """
        return datetime.now(timezone.utc)

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

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        action = decision.action
        symbol = decision.symbol
        price = self._get_current_price(symbol)
        
        if action in {"enter_long", "enter_short"}:
            # Skip if we already have a position in this symbol
            if symbol in self.positions:
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, f"Paper: already holding {symbol}"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, f"Paper: duplicate entry blocked")
                )

            # Re-entry cooldown — prevent churning after SL/TP exits
            if symbol in self._exit_cooldowns:
                elapsed = time.time() - self._exit_cooldowns[symbol]
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
            # ── Prop Firm Auto-Sizer ──
            prop_tier = float(getattr(self.profile, "prop_challenge_tier_usd", 0.0))
            prop_loss = float(getattr(self.profile, "prop_challenge_max_loss_pct", 0.0))
            
            if prop_tier > 0 and prop_loss <= 0:
                prop_loss = 0.04 if prop_tier <= 50000 else 0.03
            
            if prop_tier > 0 and prop_loss > 0:
                sizing_capital = prop_tier * prop_loss
                logger.info(f"[PAPER] [PROP FIRM SIZER] True Equity scaling active: ${sizing_capital:,.2f} ({prop_loss*100}% max loss of ${prop_tier:,.0f} nominal tier)")
            else:
                sizing_capital = self._initial_balance
                
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
                min_stop_distance = price * 0.0015  # 0.15% of entry (matches backtester)
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
            
            # [DEBUG] Trace sizing pipeline
            logger.info(
                f"[PAPER] [SIZING DEBUG] {symbol}: sizing_capital=${sizing_capital:.2f}, "
                f"risk_pct={risk_pct}, risk_usd=${risk_usd:.2f}, price={price:.5f}, "
                f"SL={decision.stop_loss}, qty_before_cap={qty:.4f}, "
                f"notional_before_cap=${qty * price:,.0f}"
            )

            # [FIX] Leverage-based sizing cap — capped at PAPER_MAX_LEVERAGE
            profile_leverage = getattr(self.profile, "target_leverage", 1.0) or 1.0
            target_leverage = min(profile_leverage, self.PAPER_MAX_LEVERAGE)
            if profile_leverage > self.PAPER_MAX_LEVERAGE:
                logger.info(
                    f"[PAPER] [LEVERAGE] {symbol}: profile leverage {profile_leverage}x "
                    f"capped to paper max {self.PAPER_MAX_LEVERAGE}x"
                )
            max_notional = sizing_capital * target_leverage
            max_qty = max_notional / price if price > 0 else 0
            
            logger.info(
                f"[PAPER] [CAP DEBUG] {symbol}: profile_leverage={profile_leverage}, "
                f"target_leverage={target_leverage}, max_notional=${max_notional:,.0f}, "
                f"max_qty={max_qty:.4f}, qty={qty:.4f}, "
                f"will_cap={qty > max_qty and max_qty > 0}"
            )
            
            if qty > max_qty and max_qty > 0:
                logger.warning(
                    f"[PAPER] [LEVERAGE CAP] {symbol}: qty {qty:.4f} -> {max_qty:.4f} "
                    f"(notional ${qty * price:,.0f} exceeds {target_leverage}x leverage cap ${max_notional:,.0f})",
                    extra={"broker": "paper", "symbol": symbol, "event": "leverage_cap", "original_qty": qty, "capped_qty": max_qty}
                )
                qty = max_qty

            # Affordability guard: reject if notional exceeds leveraged sizing capital
            notional = qty * price
            if notional > sizing_capital * max(target_leverage, 1.0) * 1.01:
                logger.warning(
                    f"[PAPER] [BLOCKED] {symbol}: notional ${notional:,.0f} exceeds balance ${self.balance:.2f}",
                    extra={"broker": "paper", "symbol": symbol, "event": "blocked", "notional": notional, "balance": self.balance}
                )
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: insufficient balance"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_INSUFFICIENT_EQUITY, symbol, "Paper: insufficient balance")
                )

            if qty <= 0:
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper position size too small"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, "Paper size zero")
                )

            # Check Paper config for UI overrides
            import json
            try:
                with open(_paths.CONFIG_FILE, "r") as f:
                    _p_conf = json.load(f).get("paper", {})
            except Exception:
                _p_conf = {}
            
            fee_bps = float(_p_conf.get("fee_bps", 0.0))
            spread_bps = float(_p_conf.get("spread_bps", 0.0))
            slip_bps = float(_p_conf.get("slippage_bps", 0.0))

            if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
                # Parity Mode: use backtester equivalent fees and NO artificial spread
                friction = 0.0
                fill_price = price
                fee_usd = abs(qty * fill_price) * self._get_taker_fee(symbol)
            else:
                # Custom UI Override Mode
                fee_pct = fee_bps / 10000.0
                spread_pct = spread_bps / 10000.0
                slip_pct = slip_bps / 10000.0
                friction = (spread_pct / 2.0) + slip_pct
                fill_price = price * (1 + friction) if side == "buy" else price * (1 - friction)
                fee_usd = abs(qty * fill_price) * (fee_pct / 2.0)  # Half on entry

            self.balance -= fee_usd  # Deduct taker fee immediately

            stop_loss_val = getattr(decision, "stop_loss", None)
            initial_risk_val = abs(fill_price - stop_loss_val) if stop_loss_val else None

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
            }
            logger.info(
                f"[PAPER] [FILL] {symbol} {qty:.4f} @ {fill_price:.5f} "
                f"(mid={price:.5f}, spread+slip={friction*100:.2f}%, fee=${fee_usd:.4f}, Risk=${risk_usd:.2f})",
                extra={"broker": "paper", "symbol": symbol, "event": "order_filled",
                       "side": side, "qty": qty, "fill_price": fill_price,
                       "fee_usd": fee_usd, "risk_usd": risk_usd}
            )
            self._save_state()
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

                # Check Paper config for UI overrides
                import json
                try:
                    with open(_paths.CONFIG_FILE, "r") as f:
                        _p_conf = json.load(f).get("paper", {})
                except Exception:
                    _p_conf = {}
                
                fee_bps = float(_p_conf.get("fee_bps", 0.0))
                spread_bps = float(_p_conf.get("spread_bps", 0.0))
                slip_bps = float(_p_conf.get("slippage_bps", 0.0))
                
                if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
                    exit_p = price
                    fee_usd = abs(pos["qty"] * exit_p) * self._get_taker_fee(symbol)
                else:
                    fee_pct = fee_bps / 10000.0
                    spread_pct = spread_bps / 10000.0
                    slip_pct = slip_bps / 10000.0
                    friction = (spread_pct / 2.0) + slip_pct
                    exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                    fee_usd = abs(pos["qty"] * exit_p) * (fee_pct / 2.0)

                pnl_usd = (exit_p - entry_p) * pos["size"]
                pnl_usd -= fee_usd
                self.balance += pnl_usd

                # Duration — use entry_time (sim_time domain) not opened_at (wall-clock)
                # In turbo replay, wall-clock trades open/close seconds apart = 0m.
                duration_secs = 0.0
                entry_time_str = pos.get("entry_time", "")
                try:
                    if entry_time_str:
                        entry_dt = datetime.fromisoformat(entry_time_str)
                        duration_secs = (self._now() - entry_dt).total_seconds()
                except Exception:
                    pass

                logger.info(
                    f"[PAPER] [EXIT] {symbol} @ {exit_p:.5f} | PNL: ${pnl_usd:.2f} "
                    f"(fee=${fee_usd:.4f}) (Paper Mode)",
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
                    ))

                self._exit_cooldowns[symbol] = time.time()
                self._save_state()
                self.refresh_account_summary()
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

                # Check Paper config for UI overrides
                import json
                try:
                    with open(_paths.CONFIG_FILE, "r") as f:
                        _p_conf = json.load(f).get("paper", {})
                except Exception:
                    _p_conf = {}
                
                fee_bps = float(_p_conf.get("fee_bps", 0.0))
                spread_bps = float(_p_conf.get("spread_bps", 0.0))
                slip_bps = float(_p_conf.get("slippage_bps", 0.0))
                
                if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
                    exit_p = price
                    fee_usd = close_qty * exit_p * self._get_taker_fee(symbol)
                else:
                    fee_pct = fee_bps / 10000.0
                    spread_pct = spread_bps / 10000.0
                    slip_pct = slip_bps / 10000.0
                    friction = (spread_pct / 2.0) + slip_pct
                    exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                    fee_usd = close_qty * exit_p * (fee_pct / 2.0)

                pnl_usd = (exit_p - entry_p) * (close_qty if pos_side == "long" else -close_qty)
                pnl_usd -= fee_usd
                self.balance += pnl_usd

                # Duration — use entry_time (sim_time domain)
                duration_secs = 0.0
                entry_time_str = pos.get("entry_time", "")
                try:
                    if entry_time_str:
                        entry_dt = datetime.fromisoformat(entry_time_str)
                        duration_secs = (self._now() - entry_dt).total_seconds()
                except Exception:
                    pass

                logger.info(
                    f"[PAPER] [EXIT] {symbol} @ {exit_p:.5f} | PNL: ${pnl_usd:.2f} "
                    f"(fee=${fee_usd:.4f}) (scale_out {scale_frac:.0%}, remain={remain_qty:.4f}) (Paper Mode)",
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
                    ))

                # Update or remove position
                if remain_qty < 1e-6:
                    del self.positions[symbol]
                    self._exit_cooldowns[symbol] = time.time()
                else:
                    pos["qty"] = remain_qty
                    pos["size"] = remain_qty if pos_side == "long" else -remain_qty

                self._save_state()
                self.refresh_account_summary()
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Paper scale_out {scale_frac:.0%}"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Paper scale_out {scale_frac:.0%}")
                )
        
        if action == "scale_in":
            if symbol in self.positions:
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
                
                # [FIX] Leverage cap for scale_in — same cap as initial entry
                # Without this, pyramids bypass the leverage limit entirely,
                # allowing positions to balloon to millions in notional.
                profile_leverage = getattr(self.profile, "target_leverage", 1.0) or 1.0
                target_leverage = min(profile_leverage, self.PAPER_MAX_LEVERAGE)
                max_notional = self._initial_balance * target_leverage
                existing_notional = pos["qty"] * price
                remaining_notional = max(0, max_notional - existing_notional)
                max_add_qty = remaining_notional / price if price > 0 else 0
                
                if qty > max_add_qty:
                    if max_add_qty <= 0:
                        logger.warning(
                            f"[PAPER] [SCALE_IN BLOCKED] {symbol}: existing notional "
                            f"${existing_notional:,.0f} already at {target_leverage}x "
                            f"leverage cap ${max_notional:,.0f}"
                        )
                        return (
                            ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: pyramid blocked by leverage cap"),
                            ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, "Paper: pyramid leverage cap")
                        )
                    logger.info(
                        f"[PAPER] [SCALE_IN CAP] {symbol}: pyramid qty {qty:.4f} -> {max_add_qty:.4f} "
                        f"(existing notional ${existing_notional:,.0f}, "
                        f"cap ${max_notional:,.0f} at {target_leverage}x)"
                    )
                    qty = max_add_qty
                
                # Check Paper config for UI overrides
                import json
                try:
                    with open(_paths.CONFIG_FILE, "r") as f:
                        _p_conf = json.load(f).get("paper", {})
                except Exception:
                    _p_conf = {}
                
                fee_bps = float(_p_conf.get("fee_bps", 0.0))
                spread_bps = float(_p_conf.get("spread_bps", 0.0))
                slip_bps = float(_p_conf.get("slippage_bps", 0.0))

                if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
                    friction = 0.0
                    fill_price = price
                    fee_usd = abs(qty * fill_price) * self._get_taker_fee(symbol)
                else:
                    fee_pct = fee_bps / 10000.0
                    spread_pct = spread_bps / 10000.0
                    slip_pct = slip_bps / 10000.0
                    friction = (spread_pct / 2.0) + slip_pct
                    fill_price = price * (1 + friction) if side == "buy" else price * (1 - friction)
                    fee_usd = abs(qty * fill_price) * (fee_pct / 2.0)

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

                logger.info(
                    f"[PAPER] [SCALE_IN] {symbol} {qty:.4f} @ {fill_price:.5f} "
                    f"(mid={price:.5f}, new_avg={new_avg:.5f}, new_qty={new_qty:.4f}, Risk=${risk_usd:.2f})",
                    extra={"broker": "paper", "symbol": symbol, "event": "scale_in",
                           "side": side, "qty": qty, "fill_price": fill_price,
                           "fee_usd": fee_usd, "risk_usd": risk_usd}
                )
                self._save_state()
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
            pos["unrealized_pnl"] = (price - pos["entry_price"]) * pos["size"]
            pos["pnl_pct"] = (pos["unrealized_pnl"] / (pos["entry_price"] * abs(pos["size"]))) * 100
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

            # Compute fees (same logic as close_position)
            import json
            try:
                with open(_paths.CONFIG_FILE, "r") as f:
                    _p_conf = json.load(f).get("paper", {})
            except Exception:
                _p_conf = {}

            fee_bps = float(_p_conf.get("fee_bps", 0.0))
            spread_bps = float(_p_conf.get("spread_bps", 0.0))
            slip_bps = float(_p_conf.get("slippage_bps", 0.0))

            if fee_bps == 0.0 and spread_bps == 0.0 and slip_bps == 0.0:
                exit_p = price
                fee_usd = abs(pos["qty"] * exit_p) * self._get_taker_fee(symbol)
            else:
                fee_pct = fee_bps / 10000.0
                spread_pct = spread_bps / 10000.0
                slip_pct = slip_bps / 10000.0
                friction = (spread_pct / 2.0) + slip_pct
                exit_p = price * (1 - friction) if pos_side == "long" else price * (1 + friction)
                fee_usd = abs(pos["qty"] * exit_p) * (fee_pct / 2.0)

            pnl_usd = (exit_p - entry_p) * pos["size"]
            pnl_usd -= fee_usd
            self.balance += pnl_usd

            # Duration
            duration_secs = 0.0
            entry_time_str = pos.get("entry_time", "")
            try:
                if entry_time_str:
                    entry_dt = datetime.fromisoformat(entry_time_str)
                    duration_secs = (self._now() - entry_dt).total_seconds()
            except Exception:
                pass

            pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 and pos["size"] != 0 else 0.0
            pnl_sign = "+" if pnl_usd >= 0 else "-"
            entry_fee = abs(pos.get("entry_fee", 0))
            spread_cost = entry_fee + fee_usd

            logger.info(
                f"[PAPER] [EXIT] Manual Cash-Out: {symbol} {pnl_sign}${abs(pnl_usd):.2f} "
                f"(Pct={pnl_pct:.2f}%) position={pos_side.upper()} | "
                f"Entry={entry_p:.5f} Exit={exit_p:.5f} | "
                f"Est. Spread Cost: ${spread_cost:.2f}"
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
                ))

            self._exit_cooldowns[symbol] = time.time()
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
        results = []
        for symbol in list(self.positions.keys()):
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
                        _router_held_s = (self._now() - _entry_dt).total_seconds()
                    except Exception:
                        pass
                # Only run after hold guard (300s = 5 minutes)
                if _router_held_s >= 300:
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
                                # Exit router wants to close via strategy — do it at bar close price
                                _exit_price = candles_for_router[-1].close if candles_for_router else price
                                entry_p = pos.get("entry_price", 0)
                                pnl_usd = (_exit_price - entry_p) * pos["size"]
                                fee_usd = abs(pos.get("qty", abs(pos["size"])) * _exit_price) * self._get_taker_fee(symbol)
                                pnl_usd -= fee_usd
                                self.balance += pnl_usd
                                
                                # Duration
                                duration_secs = _router_held_s
                                duration_str = "N/A"
                                if duration_secs is not None:
                                    _m = int(duration_secs // 60)
                                    _s = int(duration_secs % 60)
                                    if _m >= 60:
                                        _h = _m // 60
                                        _m = _m % 60
                                        duration_str = f"{_h}h {_m}m {_s}s"
                                    else:
                                        duration_str = f"{_m}m {_s}s"
                                
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
                                    f"Est. Spread Cost: ${spread_cost:.2f} | {_router_reason}"
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
                                    ))
    
                                del self.positions[symbol]
                                self._exit_cooldowns[symbol] = time.time()
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

            if side == "long":
                # SL: use candle LOW (worst intra-bar price against long)
                check_sl = candle_low if candle_low is not None else price
                # TP: use candle HIGH (best intra-bar price for long)
                check_tp = candle_high if candle_high is not None else price
                if sl and check_sl <= sl:
                    hit = "SL"
                    exit_price = sl  # Exit at exact SL level
                elif tp and tp > entry_p and check_tp >= tp:
                    hit = "TP"
                    exit_price = tp  # Exit at exact TP level
                elif tp and tp <= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} <= entry {entry_p} for LONG — ignoring TP")
            else:  # short
                # SL: use candle HIGH (worst intra-bar price against short)
                check_sl = candle_high if candle_high is not None else price
                # TP: use candle LOW (best intra-bar price for short)
                check_tp = candle_low if candle_low is not None else price
                if sl and check_sl >= sl:
                    hit = "SL"
                    exit_price = sl  # Exit at exact SL level
                elif tp and tp < entry_p and check_tp <= tp:
                    hit = "TP"
                    exit_price = tp  # Exit at exact TP level
                elif tp and tp >= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} >= entry {entry_p} for SHORT — ignoring TP")

            if hit:
                # exit_price already set to exact SL/TP level from OHLC evaluation above
                pnl_usd = (exit_price - entry_p) * pos["size"]
                fee_usd = abs(pos.get("qty", abs(pos["size"])) * exit_price) * self._get_taker_fee(symbol)
                pnl_usd -= fee_usd
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
                opened_at_str = pos.get("opened_at")
                duration_secs = None
                duration_str = "N/A"
                if opened_at_str:
                    try:
                        # Use entry_time (sim_time domain) for duration, not opened_at (wall-clock)
                        entry_time_str = pos.get("entry_time", opened_at_str)
                        entry_dt = datetime.fromisoformat(entry_time_str)
                        closed_sim = self._now()
                        duration_secs = (closed_sim - entry_dt).total_seconds()
                        if duration_secs < 0:
                            duration_secs = abs(duration_secs)
                        # Human-readable duration
                        mins = int(duration_secs // 60)
                        secs = int(duration_secs % 60)
                        if mins >= 60:
                            hrs = mins // 60
                            mins = mins % 60
                            duration_str = f"{hrs}h {mins}m {secs}s"
                        else:
                            duration_str = f"{mins}m {secs}s"
                    except Exception:
                        pass

                logger.info(
                    f"[PAPER] [EXIT] Paper {hit}: {symbol} {pnl_str} "
                    f"(Pct={pnl_pct:.2f}%) position={side.upper()} | "
                    f"Entry={entry_p:.5f} Exit={exit_price:.5f} | "
                    f"Duration={duration_str} | "
                    f"Est. Spread Cost: ${spread_cost:.2f}"
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
                    ))

                del self.positions[symbol]
                self._exit_cooldowns[symbol] = time.time()  # Start re-entry cooldown
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
                pos["unrealized_pnl"] = (cur - pos["entry_price"]) * pos["size"]
                pos["pnl_pct"] = (pos["unrealized_pnl"] / (pos["entry_price"] * abs(pos["size"]))) * 100
            except Exception:
                pass
        self._save_state()

        return results

    def summarize_pnl(self):
        logger.info(f"Session summary: Balance=${self.balance:.2f}, Open positions={len(self.positions)}")
        self._save_state()

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        return symbol in self.positions

    def sync_profile(self, profile):
        self.profile = profile

    @property
    def position_hold_store(self):
        return None

