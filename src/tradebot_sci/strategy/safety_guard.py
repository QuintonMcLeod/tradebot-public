
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Any


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import (
    AITradeDecision, 
    stand_aside_decision, 
    close_position_decision,
    hold_decision,
    scale_out_decision,
)
from tradebot_sci.strategy.icc_signals import calculate_atr, detect_structure_invalidation
from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
from tradebot_sci.config.models import UserConfig
from tradebot_sci.config.loader import get_settings
from tradebot_sci.runtime.scheduling import is_market_open
from tradebot_sci.runtime.rejection_journal import rejection_journal
from tradebot_sci.strategy.safety_state import SafetyState

logger = logging.getLogger(__name__)

# New Helpers for Safety Guard
def calculate_r_multiple(entry: float, stop: float, current: float, direction: str) -> float:
    risk = abs(entry - stop)
    if risk == 0: return 0.0
    profit = (current - entry) if direction == "long" else (entry - current)
    return profit / risk


def adaptive_drawdown_limit(capital: float) -> float:
    """
    Scale drawdown limit based on account size.
    Small accounts get a more generous threshold (smoke alarm analogy —
    a single trade can swing 5% on a $50 account, so 5% is too tight).

    Returns a fraction (e.g. 0.25 = 25%).
    
    Curve:  max(0.05, 0.25 × (500 / capital)^0.4)
    
        ≤$100   → ~25%
        $500    → ~15%
        $1,000  → ~10%
        $5,000  → ~7%
        ≥$10,000→  5%
    """
    if capital <= 0:
        return 0.25  # Safeguard: be generous with unknown/zero capital
    raw = 0.25 * (500.0 / max(capital, 1.0)) ** 0.4
    return max(0.05, min(0.25, raw))


class SafetyGuard:
    """
    Centralized Guardian for Account Safety.
    Consolidates disparate safety logic and implements advanced shields.
    
    INTEGRATED FEATURES:
    1.  [EXISTING] Drawdown Breaker (Stop @ 5% DD)
    2.  [EXISTING] Session Lockout (Time-based exit)
    3.  [EXISTING] Friday Fade (Reduce risk)
    4.  [EXISTING] Smart Positions (Financed Risk)
    5.  [EXISTING] ATR Armor (Breakeven & Trailing)
    
    NEW FEATURES:
    6.  [NEW] Greed Guard (Daily Profit Lock)
    7.  [NEW] Churn Burner (Max Trades/Hour)
    8.  [NEW] Volatility Veto (ATR Range)
    9.  [NEW] Streak Breaker (Pause after 3 Losses)
    10. [NEW] Opening Range Sentry (15-min avoidance)
    """

    # All mutable state consolidated into an injectable dataclass.
    _state: SafetyState = SafetyState()

    @classmethod
    def reset_state(cls) -> None:
        """Reset all mutable state — useful for tests."""
        cls._state = SafetyState()

    @classmethod
    def update_position(cls, symbol: str, position: Optional[dict]):
        """Updates the global view for a specific symbol to prevent broker blind-spots."""
        if position and isinstance(position, dict):
            cls._state.global_positions[symbol] = position
        elif symbol in cls._state.global_positions:
            # If position is None, it means the trade closed or doesn't exist
            del cls._state.global_positions[symbol]

    @classmethod
    def get_financed_risk_stats(cls):
        """Calculates holistic PnL and count across ALL symbols/brokers."""
        total_pnl = 0.0
        for pos in cls._state.global_positions.values():
            total_pnl += float(pos.get("unrealized_pnl", 0.0) or 0.0)
        return total_pnl, len(cls._state.global_positions)


    @classmethod
    def _update_daily_stats(cls, current_capital: float, asset_class: AssetClass):
        """Updates daily PnL tracking for Greed Guard."""
        today = datetime.now(ZoneInfo("America/New_York")).date()
        if cls._state.last_reset_date.get(asset_class) != today:
            cls._state.daily_start_capital[asset_class] = current_capital
            cls._state.daily_pnl[asset_class] = 0.0
            cls._state.last_reset_date[asset_class] = today
            cls._state.trade_timestamps[asset_class] = [] # Reset churn counter
            cls._state.sentiment_cache[asset_class] = {} # Fix: Dictionary for symbols
            # Reset HWM to current capital on new session — prevents stale
            # high-water marks from prior weeks triggering false drawdowns
            # at session open (e.g., Sunday 6 PM) when no trades have occurred.
            cls._state.hwm_capital[asset_class] = current_capital
            cls._state.drawdown_pause_until.pop(asset_class, None)
            logger.info(f"[SAFETY] New Day Detected for {asset_class.value}. Resetting Daily PnL + HWM. Start Capital: ${current_capital:.2f}")
        else:
            start_cap = cls._state.daily_start_capital.get(asset_class)
            if start_cap:
                cls._state.daily_pnl[asset_class] = current_capital - start_cap

    @classmethod
    def register_trade_completion(cls, symbol: str, is_win: bool):
        """Call this when a trade closes to update streaks and set cooldown."""
        # Per-symbol exit cooldown — prevents death spiral re-entry on LOSSES.
        # Winning trades skip cooldown so the bot can re-enter immediately.
        if not is_win:
            cls._state.symbol_exit_cooldown[symbol] = datetime.now() + timedelta(minutes=5)
            logger.info(f"[SAFETY] Exit cooldown set for {symbol}: 5 min (loss)")
        else:
            # Clear any existing cooldown on a win
            cls._state.symbol_exit_cooldown.pop(symbol, None)
            logger.info(f"[SAFETY] Exit cooldown SKIPPED for {symbol} (win)")

        if not is_win:
            cls._state.symbol_loss_streaks[symbol] = cls._state.symbol_loss_streaks.get(symbol, 0) + 1
            logger.info(f"[STREAK_BREAKER] {symbol} Loss Count: {cls._state.symbol_loss_streaks[symbol]}")
        else:
            if symbol in cls._state.symbol_loss_streaks:
                 logger.info(f"[STREAK_BREAKER] {symbol} Win. Resetting Streak.")
            cls._state.symbol_loss_streaks[symbol] = 0

    @classmethod
    def _reject(cls, symbol: str, timeframe: str, gate_name: str, reason: str) -> AITradeDecision:
        """Creates a stand-aside decision AND logs it to the rejection journal."""
        rejection_journal.log(symbol, timeframe, gate_name, reason)
        return stand_aside_decision(symbol, timeframe, reason)

    @classmethod
    def check_entry_safety(cls, symbol: str, timeframe: str, current_capital: float, snapshot: MarketSnapshot, ai_client: Optional[Any] = None, settings: Optional[Any] = None, trade_results: Optional[Any] = None) -> Optional[AITradeDecision]:
        """
        Runs ALL pre-entry checks.
        Returns a stand_aside_decision if unsafe. Returns None if safe to proceed.
        """
        now = datetime.now()
        est_now = datetime.now(ZoneInfo("America/New_York"))
        asset_class = classify_symbol(symbol)
        safety = getattr(settings, 'safety', None) if settings else None

        # 0. State Updates — with deposit detection
        hwm = cls._state.hwm_capital.get(asset_class, 0.0)
        deposit_just_detected = False
        if current_capital > hwm:
            # Detect deposits: if capital jumped >20% in one cycle, it's a
            # deposit, not a trade win.  Reset HWM and clear drawdown pause
            # so partially-settled deposits don't trigger false drawdowns.
            if hwm > 0 and (current_capital - hwm) / hwm > 0.20:
                logger.info(
                    f"[SAFETY] Deposit detected for {asset_class.value}: "
                    f"${hwm:.2f} → ${current_capital:.2f} "
                    f"(+{(current_capital - hwm)/hwm*100:.0f}%). "
                    f"Resetting HWM and clearing drawdown pause."
                )
                cls._state.drawdown_pause_until.pop(asset_class, None)
                deposit_just_detected = True
            cls._state.hwm_capital[asset_class] = current_capital
        cls._update_daily_stats(current_capital, asset_class)

        # -------------------------------------------------------------
        # 0.5 EXIT COOLDOWN (per-symbol, prevents death spiral re-entry)
        # -------------------------------------------------------------
        cooldown_until = cls._state.symbol_exit_cooldown.get(symbol)
        if cooldown_until and now < cooldown_until:
            remaining = int((cooldown_until - now).total_seconds())
            return cls._reject(symbol, timeframe, "Exit Cooldown", f"Exit Cooldown: {remaining}s remaining (no re-entry within 5 min of exit)")
        elif cooldown_until:
            del cls._state.symbol_exit_cooldown[symbol]  # Expired

        # -------------------------------------------------------------
        # P&L PERFORMANCE TARGETS & LIMITS
        # Only activate when capital >= $250.
        # On small accounts, percentage-based limits trip on a single
        # trade and lock the bot out — more harm than good.
        # -------------------------------------------------------------
        PNL_LIMIT_MIN_CAPITAL = 250.0
        if settings and trade_results and current_capital >= PNL_LIMIT_MIN_CAPITAL:
            # Check Daily, Weekly, Monthly P&L
            for tf_code, interval_name in [('24h', 'Daily'), ('week', 'Weekly'), ('month', 'Monthly')]:
                stats = trade_results.get_stats_for_timeframe(tf_code)
                realized_pnl = stats.get('pnl_usd', 0.0)
                
                # Check Limits (Losses)
                limit_attr = f"limit_loss_{tf_code if tf_code != '24h' else 'daily'}_pct"
                limit_pct = getattr(settings, limit_attr, 0.0)
                if limit_pct > 0:
                    start_cap = current_capital - realized_pnl # Approximation of start capital for interval
                    if start_cap > 0:
                        max_loss = start_cap * limit_pct
                        if realized_pnl < -max_loss:
                            return cls._reject(symbol, timeframe, f"{interval_name} Loss Limit", f"{interval_name} Loss Limit Reached ({realized_pnl:.0f} < -{max_loss:.0f})")

                # Check Targets (Profits)
                target_attr = f"target_profit_{tf_code if tf_code != '24h' else 'daily'}_pct"
                target_pct = getattr(settings, target_attr, 0.0)
                if target_pct > 0:
                    start_cap = current_capital - realized_pnl
                    if start_cap > 0:
                        target_profit = start_cap * target_pct
                        if realized_pnl >= target_profit:
                             return cls._reject(symbol, timeframe, f"{interval_name} Profit Target", f"{interval_name} Profit Target Reached ({realized_pnl:.0f} >= {target_profit:.0f})")

        # -------------------------------------------------------------
        # 1. DRAWDOWN BREAKER (Account Circuit Breaker)
        # -------------------------------------------------------------
        if safety and safety.safety_drawdown_breaker_enabled:
            # Check active pause
            pause_until = cls._state.drawdown_pause_until.get(asset_class)
            if pause_until and now < pause_until:
                return cls._reject(symbol, timeframe, "Drawdown Breaker", f"Drawdown Breaker ({asset_class.value.upper()}) active until {pause_until.strftime('%H:%M')}")

            # Skip drawdown trigger check if a deposit was just detected.
            # The HWM may have been set with aggregate capital from one
            # broker check, while current_capital is per-broker for the
            # next check — causing a phantom drawdown (e.g., HWM=$10K
            # aggregate vs $7.5K per-broker = 25% false drawdown).
            if not deposit_just_detected:
                # Check trigger
                hwm = cls._state.hwm_capital.get(asset_class, 0.0)
                if hwm > 0:
                    drawdown = (hwm - current_capital) / hwm
                    # Adaptive scaling: use configured value as floor, but never
                    # tighter than what the account size warrants.
                    configured_limit = getattr(safety, 'safety_drawdown_max_pct', 0.05)
                    adaptive_limit = adaptive_drawdown_limit(current_capital)
                    drawdown_limit = max(configured_limit, adaptive_limit)
                    if drawdown > drawdown_limit:
                         cls._state.drawdown_pause_until[asset_class] = now + timedelta(hours=24)
                         logger.critical(f"[SAFETY] Drawdown Breaker Triggered for {asset_class.value} ({drawdown*100:.1f}% > {drawdown_limit*100:.1f}% limit, adaptive={adaptive_limit*100:.0f}%). Pausing 24h.")
                         return cls._reject(symbol, timeframe, "Drawdown Breaker", f"Drawdown Breaker Triggered ({drawdown*100:.1f}%)")
        else:
            # Breaker disabled — clear any lingering pause so it takes
            # effect immediately on hot-plug toggle-off.
            cls._state.drawdown_pause_until.pop(asset_class, None)

        # -------------------------------------------------------------
        # 2. SESSION LOCKOUT (Time Manager)
        # -------------------------------------------------------------
        if safety and safety.safety_session_lockout_enabled:
             lockout_hour = safety.safety_session_lockout_hour
             if est_now.hour >= lockout_hour:
                 return cls._reject(symbol, timeframe, "Session Lockout", f"Session Lockout (After {lockout_hour}:00 EST)")

        # -------------------------------------------------------------
        # 3. [NEW] OPENING RANGE SENTRY (No-Trade Zone)
        # -------------------------------------------------------------
        # Avoid first 15 mins of NYSE Open (9:30 - 9:45 AM EST)
        if safety and safety.safety_opening_sentry_enabled:
            # Check 9:30-9:45 AM EST
            if est_now.hour == 9 and 30 <= est_now.minute < 45:
                 return cls._reject(symbol, timeframe, "Opening Range Sentry", "Opening Range Sentry (9:30-9:45 AM EST)")

        # -------------------------------------------------------------
        # 4. [NEW] GREED GUARD (Profit Lock)
        # -------------------------------------------------------------
        if safety and safety.safety_greed_guard_enabled:
            target = safety.safety_greed_guard_target
            daily_pnl = cls._state.daily_pnl.get(asset_class, 0.0)
            if daily_pnl >= target:
                return cls._reject(symbol, timeframe, "Greed Guard", f"Greed Guard Active for {asset_class.value} (Daily Goal ${target:.2f} Met)")

        # -------------------------------------------------------------
        # 5. [NEW] STREAK BREAKER (Symbol Cooldown)
        # -------------------------------------------------------------
        if safety and safety.safety_streak_breaker_enabled:
            # Check Active Pause
            if symbol in cls._state.symbol_pause_until:
                if now < cls._state.symbol_pause_until[symbol]:
                     return cls._reject(symbol, timeframe, "Streak Breaker", "Streak Breaker Cooldown Active")
                else:
                    del cls._state.symbol_pause_until[symbol] # Expired
            
            streak_limit = getattr(safety, 'safety_streak_max_losses', 3)
            if cls._state.symbol_loss_streaks.get(symbol, 0) >= streak_limit:
                cls._state.symbol_pause_until[symbol] = now + timedelta(hours=4)
                cls._state.symbol_loss_streaks[symbol] = 0 # Reset count after triggering
                logger.warning(f"[SAFETY] Streak Breaker triggered for {symbol} ({streak_limit} losses). Pausing 4h.")
                return cls._reject(symbol, timeframe, "Streak Breaker", f"Streak Breaker Triggered ({streak_limit} Losses)")

        # -------------------------------------------------------------
        # 6. [NEW] CHURN BURNER (Rate Limit)
        # -------------------------------------------------------------
        if safety and safety.safety_churn_burner_enabled:
            max_hourly = safety.safety_churn_burner_max
            cutoff = now - timedelta(hours=1)
            # Prune old timestamps
            timestamps = cls._state.trade_timestamps.get(asset_class, [])
            timestamps = [t for t in timestamps if t > cutoff]
            cls._state.trade_timestamps[asset_class] = timestamps
            if len(timestamps) >= max_hourly:
                return cls._reject(symbol, timeframe, "Churn Burner", f"Churn Burner ({asset_class.value.upper()}) Active (Max {max_hourly}/hr)")

        # -------------------------------------------------------------
        # 7. [NEW] VOLATILITY VETO (ATR Filter)
        # -------------------------------------------------------------
        if safety and safety.safety_volatility_veto_enabled:
            atr = calculate_atr(snapshot.candles, period=14)
            if atr:
                last_price = snapshot.candles[-1].close
                atr_pct = (atr / last_price) * 100
                
                # Min Volatility (Avoiding Dead Markets) - Default 0.05%
                min_vol = safety.safety_volatility_min_pct
                # Max Volatility (Avoiding Explosions) - Default 5.0%
                max_vol = safety.safety_volatility_max_pct
                
                if atr_pct < min_vol - 0.01:  # 0.01% tolerance — if it's ~around the threshold, let it trade
                     return cls._reject(symbol, timeframe, "Volatility Veto", f"Volatility Veto: Too Dead (ATR {atr_pct:.3f}% < {min_vol}%)")
                if atr_pct > max_vol:
                     return cls._reject(symbol, timeframe, "Volatility Veto", f"Volatility Veto: Too Volatile (ATR {atr_pct:.3f}% > {max_vol}%)")

        # 8. [NEW] AI SENTIMENT SHIELD (The Independent Veto)
        # -------------------------------------------------------------
        if safety and safety.safety_sentiment_shield_enabled and ai_client:
             try:
                 # Prevent "Itchy Trigger Finger" / excessive API calls
                 class_cache = cls._state.sentiment_cache.get(asset_class, {})
                 cached = class_cache.get(symbol)
                 cache_valid = False
                 if cached:
                     ts, sentiment_val = cached
                     # Valid if less than 15 mins old
                     if (now - ts) < timedelta(minutes=15):
                         cache_valid = True
                         sentiment = sentiment_val
                 
                 if not cache_valid:
                     sentiment_prompt = f"Analyze market structure for {symbol} based on H1 trend: {snapshot.trend_htf} and recent 5 candles. Is the structure DANGEROUS or SAFE? One word."
                     # Simple prompt to avoid complex analysis cost
                     sentiment = ai_client.generate_text([{"role": "user", "content": sentiment_prompt}]).upper()
                     # Update Cache
                     class_cache[symbol] = (now, sentiment)
                     cls._state.sentiment_cache[asset_class] = class_cache
                     logger.info(f"[SAFETY] AI Shield Refreshed for {symbol}: {sentiment}")
                 
                 if "DANGEROUS" in sentiment:
                      if not cache_valid: logger.warning(f"[SAFETY] AI Sentiment Shield blocked {symbol}: {sentiment}")
                      return cls._reject(symbol, timeframe, "AI Sentiment Shield", f"AI Sentiment Shield: {sentiment}")
                       
             except Exception as e:
                 logger.warning(f"[SAFETY] AI Shield failed request: {e}")

        # -------------------------------------------------------------
        # 9. [NEW] SEGMENTED LEVERAGE SENTRY (Max Account Leverage)
        # -------------------------------------------------------------
        # Prevents "Account Blowing Up" by capping total notional leverage
        # Isolated per asset class (Forex entries only care about Forex leverage)
        if safety and safety.safety_leverage_sentry_enabled:
            # Determine asset class of the symbol being checked
            target_class = classify_symbol(symbol)
            
            # Default to general cap, but check for class-specific overrides
            default_cap = safety.safety_max_total_leverage
            class_cap_env = f"SAFETY_MAX_{target_class.value.upper()}_LEVERAGE"
            max_leverage = float(os.getenv(class_cap_env, str(default_cap)))
            
            # Calculate total notional value only for positions in the same asset class
            total_notional = 0.0
            for pos_symbol, pos in cls._state.global_positions.items():
                if classify_symbol(pos_symbol) == target_class:
                    price = float(pos.get("avg_price") or pos.get("entry_price") or 0)
                    size = abs(float(pos.get("size") or 0))
                    contrib = price * size
                    total_notional += contrib
                    logger.debug(f"[SAFETY-LEV] {pos_symbol}: price={price} size={size} notional=${contrib:.2f}")
            
            # current_capital is passed per-broker (already isolated)
            current_leverage = total_notional / current_capital if current_capital > 0 else 0
            if current_leverage > max_leverage:
                logger.warning(f"[SAFETY] Leverage Sentry VETO for {target_class.value}: Current Leverage {current_leverage:.1f}x exceeds Cap {max_leverage}x (notional=${total_notional:.2f} / equity=${current_capital:.2f})")
                return cls._reject(symbol, timeframe, "Leverage Sentry", f"Leverage Sentry ({target_class.value.upper()}): {current_leverage:.1f}x > {max_leverage}x")

        # [FEE SHIELD] — Moved to engine.py:decide() post-entry where the decision
        # object (with entry_price/take_profit) is actually available. The isinstance
        # check here always returned False because ai_client is a TradeSciAIClient,
        # never an AITradeDecision.

        return None


    @classmethod
    def notify_entry(cls, symbol: str):
        """Call this when a trade is effectively entered to update rate limits."""
        asset_class = classify_symbol(symbol)
        if asset_class not in cls._state.trade_timestamps:
            cls._state.trade_timestamps[asset_class] = []
        cls._state.trade_timestamps[asset_class].append(datetime.now())

    @classmethod
    def augment_exit_decision(cls, decision: Optional[AITradeDecision], open_position: dict, snapshot: MarketSnapshot, sim_time: Optional[datetime] = None) -> AITradeDecision:
        """
        Applies Advanced Shields and Wealth Weapon exit safeguards.
        If the Strategy suggests an exit, we usually respect it (unless Vetoed).
        If the Strategy is silent (None), SafetyGuard can propose a management exit.
        """
        # 0. INITIALIZATION & DATA GATHERING
        entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0.0)
        if entry_price == 0: return decision
        
        if not snapshot.candles:
            return decision
            
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction") or open_position.get("side")
        current_stop = float(open_position.get("stop_price") or 0.0)
        if not direction: return decision

        modes = cls.get_active_wealth_modes()
        
        # Calculate Progress Metrics
        entry_time = open_position.get("entry_time")
        bars_since = 0
        if entry_time:
            if isinstance(entry_time, str):
                try: entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    logger.debug(f"[SAFETY] Failed to parse entry_time '{entry_time}' for bars_since calculation")
            if isinstance(entry_time, datetime):
                bars_since = len([c for c in snapshot.candles if c.timestamp >= entry_time])

        # [CHURN GUARD] Minimum hold time — refuse non-SL/TP exits for young positions.
        # Prevents the 30-40s churn cycle where strategies re-evaluate and exit immediately.
        MIN_HOLD_SECONDS = 120  # 2 minutes
        position_age_seconds = 0
        if entry_time and isinstance(entry_time, datetime):
            _now = sim_time or (datetime.now(tz=entry_time.tzinfo) if entry_time.tzinfo else datetime.now(tz=timezone.utc))
            if _now.tzinfo is None:
                _now = _now.replace(tzinfo=timezone.utc)
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            position_age_seconds = (_now - entry_time).total_seconds()
            if position_age_seconds < MIN_HOLD_SECONDS:
                logger.debug(
                    f"[SAFETY] Churn Guard: {snapshot.symbol} position age {position_age_seconds:.0f}s "
                    f"< {MIN_HOLD_SECONDS}s minimum — skipping non-SL/TP exit checks"
                )
                return decision  # Let TP/SL fire via broker, but no SafetyGuard exits

        initial_risk = abs(entry_price - current_stop)
        profit_dist = (current_price - entry_price) if direction == "long" else (entry_price - current_price)
        r_multiple = profit_dist / initial_risk if initial_risk > 0 else 0.0

        # 1. CENTRALIZED TARGET MONITOR (TP/SL)
        # Support Moonshot Elevated TP
        pos_record = cls._state.global_positions.get(snapshot.symbol, {})
        elevated_tp = pos_record.get("elevated_tp")
        
        tp_target = float(elevated_tp or open_position.get("take_profit") or open_position.get("tp_price") or 0.0)
        sl_target = float(open_position.get("stop_loss") or open_position.get("stop_price") or 0.0)
        
        if tp_target > 0:
            if (direction == "long" and current_price >= tp_target) or \
               (direction == "short" and current_price <= tp_target):
                logger.info(f"[SAFETY] TP TRIGGERED for {snapshot.symbol} at {current_price} (Target: {tp_target})")
                return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"TP Hit @ {tp_target}")

        if sl_target > 0:
            if (direction == "long" and current_price <= sl_target) or \
               (direction == "short" and current_price >= sl_target):
                logger.info(f"[SAFETY] SL TRIGGERED for {snapshot.symbol} at {current_price} (Target: {sl_target})")
                return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"SL Hit @ {sl_target}")

        settings = get_settings()

        # 2. DEFENSIVE SHIELDS
        # A. Stale-Position Sniper (Time Decay)
        if settings.safety.safety_stale_sniper_enabled:
            bars_limit = settings.safety.safety_stale_sniper_bars
            if bars_since >= bars_limit:
                # PROFIT GUARD: NEVER stale-exit a profitable trade.
                # If the trade is in the green, let TP/trail handle the exit.
                # Only stale-exit trades that are underwater.
                if r_multiple < 0.0:
                    logger.info(f"[SAFETY] Stale Sniper TRIGGERED for {snapshot.symbol} after {bars_since} bars (R={r_multiple:.2f}).")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Stale Exit ({bars_since} bars)")
                else:
                    logger.debug(f"[SAFETY] Stale Sniper SKIPPED for {snapshot.symbol}: profitable ({r_multiple:.2f}R), letting run.")

        # B. Flash-Trap / Blow-off Seller (Volatility Exhaustion)
        shield_v = settings.safety.safety_flash_trap_enabled
        weapon_v = settings.safety.wealth_exit_blowoff_enabled
        if (shield_v or weapon_v) and len(snapshot.candles) >= 14:
            # Usage of keyword-only period
            curr_atr = calculate_atr(snapshot.candles[-14:], period=14)
            hist_atr = calculate_atr(snapshot.candles[-50:], period=14)
            if curr_atr and hist_atr:
                multiplier = 3.5 if weapon_v else 2.5
                if curr_atr > (hist_atr * multiplier):
                    logger.info(f"[SAFETY] Volatility Peak TRIGGERED for {snapshot.symbol} (ATR: {curr_atr:.4f})")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason="Volatility Blow-off Exit")

        # C. Regime-Flip Veto (HTF Alignment)
        if settings.safety.safety_regime_flip_enabled:
            htf_dir = snapshot.trend_htf.direction
            if htf_dir and htf_dir != "neutral":
                is_contradiction = (direction == "long" and htf_dir == "short") or \
                                   (direction == "short" and htf_dir == "long")
                if is_contradiction:
                    # PROFIT GUARD: Don't regime-flip exit a strongly profitable trade.
                    # If trade is > 1.0R, the original entry thesis was right — let it run.
                    # Note: Tested r < 0.0 but it HURT ICC Core and Bearish Eng — they need
                    # regime protection to cut contradicting trades before full stop hit.
                    if r_multiple < 1.0:
                        logger.info(f"[SAFETY] Regime-Flip TRIGGERED for {snapshot.symbol}. HTF is {htf_dir} (R={r_multiple:.2f}).")
                        return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Regime Flip: {htf_dir.upper()}")
                    else:
                        logger.debug(f"[SAFETY] Regime-Flip SKIPPED for {snapshot.symbol}: profitable ({r_multiple:.2f}R), ignoring HTF flip.")

        # ─────────────────────────────────────────────────────────────
        # C2. STRUCTURE INVALIDATION (Centralized)
        # ─────────────────────────────────────────────────────────────
        # If the trade's structural thesis is broken (swing level violated
        # by ATR buffer), cut it. This was previously scattered across
        # individual strategies — now lives here as part of Safety Guard.
        if False and getattr(settings.safety, 'safety_structure_invalidation_enabled', True):  # DISABLED: ICC Core has its own StructInval in check_exit_signal
            if direction in ("long", "short") and snapshot.candles and len(snapshot.candles) >= 20:
                inval = detect_structure_invalidation(snapshot.candles, direction, atr_mult=0.5)
                if inval:
                    logger.info(
                        f"[SAFETY] Structure Invalidation for {snapshot.symbol} ({direction}): "
                        f"close={inval.last_close:.4f} broke swing={inval.swing_level:.4f} "
                        f"(buffer={inval.buffer:.4f})"
                    )
                    return close_position_decision(
                        snapshot.symbol, snapshot.timeframe,
                        reason=f"Structure Invalidation (swing={inval.swing_level:.4f})",
                        emergency_exit=True,  # Bypass hold guard — cut losers immediately
                    )

        # ─────────────────────────────────────────────────────────────
        # D. DAY TRADE ENFORCER (Max Hold Time)
        # ─────────────────────────────────────────────────────────────
        # Prevents the bot from becoming a swing trader.  Uses the
        # profile-level `max_hold_hours` setting with 3-phase logic:
        #   Phase 1 (0 → 70%):   Normal — strategy manages the trade
        #   Phase 2 (70 → 100%): Grace  — profitable exits, losers get tightened stops
        #   Phase 3 (> 100%):    Emergency — force close lost causes
        try:
            active_profile = settings.get_active_profile()
            max_hold_h = float(getattr(active_profile, "max_hold_hours", 0.0) or 0.0)
        except Exception:
            max_hold_h = 0.0

        if max_hold_h > 0 and entry_time and isinstance(entry_time, datetime):
            now_tz = sim_time or datetime.now(entry_time.tzinfo or ZoneInfo("UTC"))
            if now_tz.tzinfo is None:
                now_tz = now_tz.replace(tzinfo=ZoneInfo("UTC"))
            hours_held = (now_tz - entry_time).total_seconds() / 3600

            phase1_end = max_hold_h * 0.70     # normal phase ends
            phase2_end = max_hold_h             # grace period ends
            hard_kill   = max_hold_h * 1.30     # absolute hard kill

            if hours_held >= phase1_end:
                is_profitable = profit_dist > 0

                # ── Market-halted guard: don't issue kill orders when the
                #    broker can't execute them (e.g., forex weekends) ──
                _now_utc = sim_time or datetime.now(ZoneInfo("UTC"))
                if _now_utc.tzinfo is None:
                    _now_utc = _now_utc.replace(tzinfo=ZoneInfo("UTC"))
                if not is_market_open(snapshot.symbol, _now_utc, settings):
                    if not getattr(cls, '_weekend_warn_logged', {}).get(snapshot.symbol):
                        logger.warning(
                            f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} held "
                            f"{hours_held:.1f}h but market is CLOSED. "
                            f"Suppressing kill until market reopens."
                        )
                        if not hasattr(cls, '_weekend_warn_logged'):
                            cls._weekend_warn_logged = {}
                        cls._weekend_warn_logged[snapshot.symbol] = True
                    return None  # Skip — market can't execute the close
                else:
                    # Clear weekend warning flag when market reopens
                    if hasattr(cls, '_weekend_warn_logged'):
                        cls._weekend_warn_logged.pop(snapshot.symbol, None)

                # Phase 2 — Grace Period (70% → 100% of max_hold)
                if hours_held < phase2_end:
                    if is_profitable:
                        # Profitable? Lock in gains — exit now.
                        logger.info(
                            f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} profitable "
                            f"after {hours_held:.1f}h (grace). Taking profit."
                        )
                        return close_position_decision(
                            snapshot.symbol, snapshot.timeframe,
                            reason=f"Day Enforcer: Profit @ {hours_held:.1f}h (grace)"
                        )
                    else:
                        # Underwater — tighten stop by 50% to limit further damage
                        if initial_risk > 0 and current_stop > 0:
                            tighten_dist = initial_risk * 0.5
                            if direction == "long":
                                new_stop = max(current_stop, current_price - tighten_dist)
                                if new_stop > current_stop:
                                    logger.info(
                                        f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} "
                                        f"underwater {hours_held:.1f}h — tightening stop "
                                        f"{current_stop:.5f} → {new_stop:.5f}"
                                    )
                                    return hold_decision(
                                        symbol=snapshot.symbol,
                                        timeframe=snapshot.timeframe,
                                        bias="long", phase="management",
                                        reason=f"[SAFETY] Day Enforcer: Tighten stop ({hours_held:.1f}h held)",
                                        stop_loss=new_stop
                                    )
                            else:  # short
                                new_stop = min(current_stop, current_price + tighten_dist) if current_stop > 0 else current_price + tighten_dist
                                if current_stop == 0 or new_stop < current_stop:
                                    logger.info(
                                        f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} "
                                        f"underwater {hours_held:.1f}h — tightening stop "
                                        f"{current_stop:.5f} → {new_stop:.5f}"
                                    )
                                    return hold_decision(
                                        symbol=snapshot.symbol,
                                        timeframe=snapshot.timeframe,
                                        bias="short", phase="management",
                                        reason=f"[SAFETY] Day Enforcer: Tighten stop ({hours_held:.1f}h held)",
                                        stop_loss=new_stop
                                    )

                # Phase 3 — Emergency Exit (> 100% of max_hold)
                elif hours_held >= phase2_end:
                    if not is_profitable:
                        # Lost cause — force close immediately
                        logger.warning(
                            f"[SAFETY] Day Trade Enforcer: EMERGENCY EXIT {snapshot.symbol} "
                            f"after {hours_held:.1f}h (underwater, max={max_hold_h}h). "
                            f"P&L: {profit_dist:.4f}"
                        )
                        return close_position_decision(
                            snapshot.symbol, snapshot.timeframe,
                            reason=f"Day Enforcer: Emergency ({hours_held:.1f}h, losing)"
                        )
                    elif hours_held >= hard_kill:
                        # Even profitable — time's up at 130%
                        logger.warning(
                            f"[SAFETY] Day Trade Enforcer: HARD KILL {snapshot.symbol} "
                            f"after {hours_held:.1f}h (max={max_hold_h}h, hard={hard_kill:.1f}h)"
                        )
                        return close_position_decision(
                            snapshot.symbol, snapshot.timeframe,
                            reason=f"Day Enforcer: Hard Kill ({hours_held:.1f}h)"
                        )
                    else:
                        # Profitable past max_hold but before hard_kill — ultra-tight trail
                        tight_trail = current_price * 0.002  # 0.2% trail
                        if direction == "long":
                            tight_stop = current_price - tight_trail
                            if tight_stop > current_stop:
                                logger.info(
                                    f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} "
                                    f"profitable overtime — ultra-tight trail {tight_stop:.5f}"
                                )
                                return hold_decision(
                                    symbol=snapshot.symbol,
                                    timeframe=snapshot.timeframe,
                                    bias="long", phase="management",
                                    reason=f"[SAFETY] Day Enforcer: Overtime trail ({hours_held:.1f}h)",
                                    stop_loss=tight_stop
                                )
                        else:  # short
                            tight_stop = current_price + tight_trail
                            if current_stop == 0 or tight_stop < current_stop:
                                logger.info(
                                    f"[SAFETY] Day Trade Enforcer: {snapshot.symbol} "
                                    f"profitable overtime — ultra-tight trail {tight_stop:.5f}"
                                )
                                return hold_decision(
                                    symbol=snapshot.symbol,
                                    timeframe=snapshot.timeframe,
                                    bias="short", phase="management",
                                    reason=f"[SAFETY] Day Enforcer: Overtime trail ({hours_held:.1f}h)",
                                    stop_loss=tight_stop
                                )

        # 3. OFFENSIVE WEALTH WEAPONS
        # A. Moonshot Target Elevator (Impulse Hold)
        if settings.safety.wealth_exit_moonshot_enabled:
            # If 1R hit within 3 bars, double the elevator
            if bars_since <= 3 and r_multiple >= 1.0 and not elevated_tp:
                 orig_tp = float(open_position.get("take_profit") or open_position.get("tp_price") or 0.0)
                 if orig_tp > 0:
                      new_tp = entry_price + (orig_tp - entry_price) * 2
                      cls._state.global_positions[snapshot.symbol]["elevated_tp"] = new_tp
                      logger.info(f"[WEALTH] Moonshot Elevator ACTIVE for {snapshot.symbol}: Target doubled to {new_tp:.4f}")

        # =========================================================================
        # 4. PROFIT RETENTION PROTOCOLS ("The Last Mile")
        # =========================================================================
        
        # A. THE LOCK-IN (Breakeven Trail)
        # -------------------------------------------------------------------------
        # Standardizes Breakeven + Buffer Logic. 
        # Can be configured via Env (legacy) or passed in args (future). 
        # Currently we read Env or fallback to Defaults.
        be_trail_pct = settings.safety.breakeven_trail_pct
        if be_trail_pct > 0 and r_multiple >= 1.0: # Only activate after 1R secured
            # Calculate target lock-in price
            if direction == "long":
                lock_price = entry_price * (1 + be_trail_pct)
                # If current stop is below lock price, move it UP
                if current_stop < lock_price:
                     if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss < lock_price)):
                        return hold_decision(
                            symbol=snapshot.symbol,
                            timeframe=snapshot.timeframe,
                            bias="long",
                            phase="management",
                            reason=f"[SAFETY] The Lock-In: Secured Entry + {be_trail_pct*100:.1f}%",
                            stop_loss=lock_price
                        )
            else: # short
                lock_price = entry_price * (1 - be_trail_pct)
                # If current stop is above lock price, move it DOWN
                if current_stop == 0 or current_stop > lock_price:
                     if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > lock_price)):
                        return hold_decision(
                            symbol=snapshot.symbol,
                            timeframe=snapshot.timeframe,
                            bias="short",
                            phase="management",
                            reason=f"[SAFETY] The Lock-In: Secured Entry + {be_trail_pct*100:.1f}%",
                            stop_loss=lock_price
                        )

        # B. THE GREEDY EXIT (Standard Trailing Stop + Time Decay)
        # -------------------------------------------------------------------------
        # Uses ATR-based or fixed pct trails to chase runs.
        # "Trailing Stop Enabled" in UI maps to this.
        # 3-phase time-bounded escalation prevents infinite holds:
        #   Phase 1 (0 → max/2): Normal 1.5× ATR trail
        #   Phase 2 (max/2 → max): Trail tightens linearly from 1.5× → 0.5× ATR
        #   Phase 3 (> max): Force close — capital is freed
        use_greedy_exit = (settings.performance.trailing_stop_enabled if settings
                           else os.getenv("TRAILING_STOP_ENABLED", "false").lower() == "true")
        
        if use_greedy_exit:
             # Time-bounded escalation
             greedy_max_hours = settings.safety.greedy_exit_max_hold_hours if settings else 8.0
             hours_held = 0.0
             if entry_time and isinstance(entry_time, datetime):
                 now_tz = sim_time or datetime.now(entry_time.tzinfo or ZoneInfo("UTC"))
                 if now_tz.tzinfo is None:
                     now_tz = now_tz.replace(tzinfo=ZoneInfo("UTC"))
                 hours_held = (now_tz - entry_time).total_seconds() / 3600

             # Phase 3: Force close after max hold
             if greedy_max_hours > 0 and hours_held >= greedy_max_hours:
                 logger.info(f"[SAFETY] Greedy Exit TIMEOUT: {snapshot.symbol} held {hours_held:.1f}h >= {greedy_max_hours}h. Forcing close.")
                 return close_position_decision(snapshot.symbol, snapshot.timeframe,
                                                reason=f"Greedy Exit Timeout ({hours_held:.1f}h)")

             # Phase 2: Tighten trail multiplier (linear decay from 1.5 to 0.5 ATR)
             trail_multiplier = 1.5  # Phase 1 default
             if greedy_max_hours > 0 and hours_held > greedy_max_hours * 0.5:
                 progress = (hours_held - greedy_max_hours * 0.5) / (greedy_max_hours * 0.5)
                 trail_multiplier = max(0.5, 1.5 - (1.0 * min(progress, 1.0)))
                 logger.debug(f"[SAFETY] Greedy Exit TIGHTENING: {snapshot.symbol} trail={trail_multiplier:.2f}x ATR ({hours_held:.1f}h held)")

             # Default to ATR-based if available, or fallback to fixed 0.5%
             # Usage of keyword-only period
             atr = calculate_atr(snapshot.candles[-14:], period=14)
             trail_dist = 0.0
             
             if atr:
                 trail_dist = atr * trail_multiplier
             else:
                 trail_dist = current_price * 0.005 # Fallback 0.5%
             
             if direction == "long":
                 potential_stop = current_price - trail_dist
                 # FLOOR: The Greedy Exit never loses money — stop can't go below entry
                 potential_stop = max(potential_stop, entry_price)
                 # If price is at/below entry AND trade previously reached meaningful profit,
                 # the setup proved itself then reversed — close to protect capital.
                 # We check the PEAK R (highest high since entry), not current R
                 # (which is ~0 at entry). Without peak R, the gate never fires.
                 min_greedy_age = getattr(settings.safety, 'safety_greedy_min_age_seconds', 300) if settings else 300
                 relevant_candles = [c for c in snapshot.candles if entry_time and isinstance(entry_time, datetime) and c.timestamp >= entry_time]
                 peak_price = max(c.high for c in relevant_candles) if relevant_candles else entry_price
                 peak_r = (peak_price - entry_price) / initial_risk if initial_risk > 0 else 0
                 if hours_held * 3600 >= min_greedy_age and peak_r >= 0.5 and current_price <= entry_price:
                     logger.info(f"[SAFETY] Greedy Exit FLOOR: {snapshot.symbol} back at entry ({current_price:.5f} <= {entry_price:.5f}, peak was {peak_r:.1f}R). Closing at breakeven.")
                     return close_position_decision(snapshot.symbol, snapshot.timeframe,
                                                    reason=f"Greedy Exit: Back to entry (breakeven)")
                 # Only move UP
                 if potential_stop > current_stop:
                      if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss < potential_stop)):
                           return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="long",
                                phase="management",
                                reason=f"[SAFETY] The Greedy Exit: Trailing by {trail_dist:.4f} ({trail_multiplier:.1f}x ATR, {hours_held:.1f}h held)",
                                stop_loss=potential_stop
                           )
             else: # short
                 potential_stop = current_price + trail_dist
                 # FLOOR: The Greedy Exit never loses money — stop can't go above entry
                 potential_stop = min(potential_stop, entry_price)
                 # If price is at/above entry AND trade previously reached meaningful profit,
                 # the setup proved itself then reversed — close to protect capital.
                 min_greedy_age = getattr(settings.safety, 'safety_greedy_min_age_seconds', 300) if settings else 300
                 relevant_candles = [c for c in snapshot.candles if entry_time and isinstance(entry_time, datetime) and c.timestamp >= entry_time]
                 trough_price = min(c.low for c in relevant_candles) if relevant_candles else entry_price
                 peak_r = (entry_price - trough_price) / initial_risk if initial_risk > 0 else 0
                 if hours_held * 3600 >= min_greedy_age and peak_r >= 0.5 and current_price >= entry_price:
                     logger.info(f"[SAFETY] Greedy Exit FLOOR: {snapshot.symbol} back at entry ({current_price:.5f} >= {entry_price:.5f}, peak was {peak_r:.1f}R). Closing at breakeven.")
                     return close_position_decision(snapshot.symbol, snapshot.timeframe,
                                                    reason=f"Greedy Exit: Back to entry (breakeven)")
                 # Only move DOWN
                 if current_stop == 0 or potential_stop < current_stop:
                      if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > potential_stop)):
                           return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="short",
                                phase="management",
                                reason=f"[SAFETY] The Greedy Exit: Trailing by {trail_dist:.4f} ({trail_multiplier:.1f}x ATR, {hours_held:.1f}h held)",
                                stop_loss=potential_stop
                           )


        # C. THE SNIPER TARGET (Hard TP by R-Multiple)
        # -------------------------------------------------------------------------
        # If Risk/Reward Ratio is set, enforce it as a hard profit target.
        rr_target = settings.safety.risk_reward_ratio
        if rr_target > 0 and initial_risk > 0:
            target_price = 0.0
            if direction == "long":
                target_price = entry_price + (initial_risk * rr_target)
                if current_price >= target_price:
                    logger.info(f"[SAFETY] Sniper Target Hit: {current_price} >= {target_price} ({rr_target}R)")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Sniper Target ({rr_target}R)")
            else: # short
                target_price = entry_price - (initial_risk * rr_target)
                if current_price <= target_price:
                    logger.info(f"[SAFETY] Sniper Target Hit: {current_price} <= {target_price} ({rr_target}R)")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Sniper Target ({rr_target}R)")


        # Enabled ATR Armor logic
        # 4. ATR ARMOR (Consolidated with Gamma Squeeze)
        if settings.safety.safety_atr_shield_enabled:
            # 1. Breakeven (1R)
            if initial_risk > 0 and r_multiple >= 1.0:
                if (direction == "long" and current_stop < entry_price) or \
                   (direction == "short" and current_stop > entry_price):
                    if not decision: 
                         return hold_decision(
                             symbol=snapshot.symbol,
                             timeframe=snapshot.timeframe,
                             bias="long" if direction == "long" else "short", 
                             phase="management",
                             reason="[SAFETY] Armor: Breakeven (1R)",
                             stop_loss=entry_price
                         )

            # 2. Dynamic Trailing (with Gamma Squeeze)
            trailing_pct = 0.05
            if settings.safety.wealth_exit_gamma_enabled:
                 # Exponential tightening if in strong profit
                 if r_multiple >= 2.0: trailing_pct = 0.02
                 elif r_multiple >= 1.0: trailing_pct = 0.035

            relevant = [c for c in snapshot.candles if c.timestamp >= entry_time] if entry_time else []
            if relevant:
                if direction == "long":
                    peak = max(c.high for c in relevant)
                    target_stop = peak * (1 - trailing_pct)
                    if target_stop > current_stop:
                        if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss < target_stop)):
                            return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="long",
                                phase="management",
                                reason=f"[SAFETY] Armor: {f'Gamma Trail' if trailing_pct < 0.05 else 'Trailing'} (${peak:.2f})",
                                stop_loss=target_stop
                            )
                else:
                    trough = min(c.low for c in relevant)
                    target_stop = trough * (1 + trailing_pct)
                    if current_stop == 0 or target_stop < current_stop:
                        if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > target_stop)):
                            return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="short",
                                phase="management",
                                reason=f"[SAFETY] Armor: {f'Gamma Trail' if trailing_pct < 0.05 else 'Trailing'} (${trough:.2f})",
                                stop_loss=target_stop
                            )

        return decision
 
    # =========================================================================
    # PERFORMANCE & PROFITS (WEALTH CREATION)
    # =========================================================================
    # [WEALTH MODE] State Tracking
    @classmethod
    def set_win_rate(cls, wr: float, asset_class: Optional[AssetClass] = None):
        if asset_class:
            cls._state.win_rate[asset_class] = wr
        else:
            # Fallback: Apply to all
            for ac in AssetClass:
                cls._state.win_rate[ac] = wr

    @classmethod
    def set_current_positions(cls, positions: list[dict]):
        """Updates the global view of positions for risk-based calculations."""
        # This updates GLOBAL_POSITIONS via set_current_positions(legacy) logic
        # But we also have OPEN_POSITIONS which might be redundant now. 
        # Let's keep them in sync if used by legacy performance modes.
        cls._state.open_positions = positions
        for p in positions:
            sym = p.get("symbol")
            if sym: cls.update_position(sym, p)

    @classmethod
    def get_active_wealth_modes(cls) -> list[str]:
        """Returns a list of active performance modes from the settings (comma-separated)."""
        settings = get_settings()
        raw = settings.performance.performance_mode.lower()
        modes = []
        if raw and raw != "none":
            modes = [m.strip() for m in raw.split(",") if m.strip()]
        
        # [STABILITY] Force stability mode if active in config
        if UserConfig.STABILITY_MODE_ACTIVE:
            if "stability" not in modes:
                modes.insert(0, "stability")
        
        return modes

    @classmethod
    def get_wealth_mode(cls) -> str | None:
        """Returns the first active wealth mode (singular), or None if no mode is active."""
        modes = cls.get_active_wealth_modes()
        return modes[0] if modes else None

    @classmethod
    def augment_entry_decision(cls, decision: AITradeDecision, score: float, htf_strength: float, snapshot: MarketSnapshot, ai_client: Optional[Any] = None, settings=None) -> AITradeDecision:
        """
        Applies "Offensive" performance overrides to an entry decision.
        Supports STACKING: Foundation (Base) + Multipliers (Boosts).
        """
        if not decision or decision.action not in ["enter_long", "enter_short", "scale_in"]:
            return decision

        modes = cls.get_active_wealth_modes()
        if not modes:
            return decision

        # -------------------------------------------------------------
        # 0. RESOLVE ASSET CLASS
        # -------------------------------------------------------------
        asset_class = classify_symbol(snapshot.symbol)

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # 1. ESTABLISH BASE RISK (The Foundation)
        # -------------------------------------------------------------
        # Read from profile settings first, then decision, then fallback.
        # This ensures the user's configured risk_per_trade_pct is actually respected.
        profile_risk = getattr(settings, 'risk_per_trade_pct', None) if settings else None
        base_risk = decision.risk_per_trade_pct or profile_risk or 0.015 
        
        # Priority Check: Detect which Foundation is active (start with "simplicity" default)
        # If multiple foundations are accidentally set, we pick priority: Kelly > Flywheel > Smooth > Simplicity
        
        # A. KELLY CRITERION (Math Edge)
        if "kelly" in modes:
            w = cls._state.win_rate.get(asset_class, 0.55)
            r = 2.0 # Assume 2:1 RR conservative average
            kelly_f = w - (1 - w) / r
            if kelly_f > 0:
                base_risk = kelly_f * 0.5 # Half-Kelly for safety
                decision.notes = (decision.notes or "") + f" [WEALTH] Kelly Base ({asset_class.value}): {base_risk*100:.1f}%"
        
        # B. COMPOUND FLYWHEEL (Growth Based)
        elif "flywheel" in modes:
             daily_pnl = cls._state.daily_pnl.get(asset_class, 0.0)
             if daily_pnl > 0:
                  milestone = 200.0
                  boost = (daily_pnl // milestone) * 0.001
                  base_risk = min(0.015 + boost, 0.05) # Cap base at 5%
                  decision.notes = (decision.notes or "") + f" [WEALTH] Flywheel Base ({asset_class.value}): {base_risk*100:.1f}%"

        # C. EQUITY SMOOTHING (Anti-Tilt / Mean Reversion)
        elif "smooth" in modes:
            # Boost if at ATH, slash if in drawdown
            hwm = cls._state.hwm_capital.get(asset_class, 0.0)
            daily_pnl = cls._state.daily_pnl.get(asset_class, 0.0)
            if hwm > 0 and daily_pnl < -0.02 * hwm: # 2% Daily Drawdown
                base_risk = 0.005 # Slash to 0.5%
                decision.notes = (decision.notes or "") + f" [WEALTH] Anti-Tilt Base ({asset_class.value}) (Defensive)"
            elif hwm > 0 and daily_pnl > 0:
                base_risk = 0.02 # Boost to 2%
                decision.notes = (decision.notes or "") + f" [WEALTH] Momentum Base ({asset_class.value})"

        # D. STABILITY MODE (Ultra Conservative Foundation)
        if "stability" in modes:
            base_risk = min(base_risk, 0.01)
            decision.notes = (decision.notes or "") + f" [STABILITY] Foundation Risk: {base_risk*100:.1f}%"

        # Apply the determined base
        decision.risk_per_trade_pct = base_risk

        # -------------------------------------------------------------
        # 2. APPLY MULTIPLIERS (The Boosters)
        # -------------------------------------------------------------
        
        # A. THE SNIPER GRADE (Quality Boost)
        if "sniper" in modes:
            if score >= 90:
                decision.risk_per_trade_pct *= 1.5
                decision.notes = (decision.notes or "") + " | Sniper Boost (1.5x)"
                logger.info(f"[WEALTH] SNIPER BOOST: {decision.symbol} (Score: {score})")

        # B. REGIME SYNC (Trend Alignment)
        if "regime_sync" in modes:
            if htf_strength >= 0.7:
                decision.risk_per_trade_pct *= 1.5
                decision.notes = (decision.notes or "") + f" | Regime Boost (+{htf_strength:.2f})"
            elif htf_strength <= 0.3:
                decision.risk_per_trade_pct *= 0.5
                decision.notes = (decision.notes or "") + f" | Regime Dampen (-{htf_strength:.2f})"

        # C. TIME-OF-DAY ALPHA (Power Hour)
        if "alpha" in modes:
            est_now = datetime.now(ZoneInfo("America/New_York"))
            if 9 <= est_now.hour <= 11:
                decision.risk_per_trade_pct *= 1.2
                decision.notes = (decision.notes or "") + " | Power Hour (1.2x)"

        # D. GAMMA SQUEEZE (Velocity)
        if "gamma" in modes:
            if len(snapshot.candles) >= 5:
                start = snapshot.candles[-4].close
                end = snapshot.candles[-1].close
                velocity = abs(end - start) / start
                if velocity > 0.01:
                    decision.risk_per_trade_pct *= 1.2
                    decision.notes = (decision.notes or "") + " | Gamma Squeeze (1.2x)"

        # E. VOLATILITY COIL (Compression)
        if "coil" in modes:
            candles = snapshot.candles
            if len(candles) >= 100:
                # Usage of keyword-only period
                recent_atr = calculate_atr(candles[-14:], period=14)
                hist_atr = calculate_atr(candles, period=100)
                if recent_atr and hist_atr and recent_atr < (hist_atr * 0.6):
                    decision.risk_per_trade_pct *= 2.0
                    decision.notes = (decision.notes or "") + " | Coil Breakout (2.0x)"

        # F. HARMONIC GHOST (Liquidity Magnet)
        if "ghost" in modes and snapshot.candles:
            last_price = snapshot.candles[-1].close
            if abs(last_price - round(last_price)) < (last_price * 0.001):
                decision.risk_per_trade_pct *= 1.5
                decision.notes = (decision.notes or "") + " | Ghost Level (1.5x)"

        # G. AI SENTIMENT CONFIRMATION (Hype)
        if "sentiment" in modes and ai_client:
            try:
                sentiment_prompt = f"Analyze price action for {snapshot.symbol}. Short-term sentiment: BULLISH or BEARISH? One word."
                sentiment = ai_client.generate_text([{"role": "user", "content": sentiment_prompt}]).upper()
                is_bull = "long" in decision.action
                if (sentiment == "BULLISH" and is_bull) or (sentiment == "BEARISH" and not is_bull):
                    decision.risk_per_trade_pct *= 1.5
                    decision.notes = (decision.notes or "") + f" | AI Sentiment Boost ({sentiment})"
                elif sentiment != "NEUTRAL":
                    # If sentiment contradicts, we might VETO entirely (Safety Shield style)
                    # For performance mode, we simply don't boost, OR we dampen.
                    # Let's dampen to be safe.
                    decision.risk_per_trade_pct *= 0.5
                    decision.notes = (decision.notes or "") + f" | AI Sentiment Drag ({sentiment})"
            except Exception:
                pass

        # I. THE WHALE WATCHER (Volume Profile)
        if "whale" in modes and snapshot.candles:
            # Simple Proxy: If recent volume is > 2x average, we assume institutional interest
            volumes = [c.volume for c in snapshot.candles[-20:]]
            if len(volumes) >= 20:
                avg_vol = sum(volumes) / len(volumes)
                current_vol = snapshot.candles[-1].volume
                if current_vol > (avg_vol * 2.0):
                    decision.risk_per_trade_pct *= 1.3
                    decision.notes = (decision.notes or "") + " | Whale Volume (1.3x)"

        # J. THE CONTRARIAN (RSI Fades)
        if "contrarian" in modes and snapshot.candles:
            # Calculate 14-period RSI (Approximation if libs missing, or use helper if available)
            # We'll do a simple gain/loss calc for last 14 bars to estimate
            closes = [c.close for c in snapshot.candles[-15:]]
            if len(closes) >= 15:
                # Basic Logic: If we are Shorting and Price rose sharply (RSI high), it's a fade.
                last_close = closes[-1]
                prev_close = closes[-14]
                pct_change = (last_close - prev_close) / prev_close
                
                is_short = "short" in decision.action
                is_long = "long" in decision.action
                
                # If price pumped > 3% and we are shorting -> Contrarian Fade
                if is_short and pct_change > 0.03:
                    decision.risk_per_trade_pct *= 1.5
                    decision.notes = (decision.notes or "") + " | Contrarian Fade Top (1.5x)"
                # If price dumped > 3% and we are longing -> Contrarian Knife
                elif is_long and pct_change < -0.03:
                     decision.risk_per_trade_pct *= 1.5
                     decision.notes = (decision.notes or "") + " | Contrarian Catch Bottom (1.5x)"

        # L. STABILITY OVERRIDE (Final Clamp)
        if "stability" in modes:
            # Enforce max 1% regardless of boosters
            if decision.risk_per_trade_pct > 0.01:
                decision.risk_per_trade_pct = 0.01
                decision.notes = (decision.notes or "") + " | Stability Override (Capped @ 1%)"
            
            # Enhance Score Requirement (Veto if score below 75 in stability mode)
            if score < 75.0:
                 logger.warning(f"[STABILITY] Vetoing {decision.symbol} entry: Score {score} < 75 (Stability Enabled)")
                 return stand_aside_decision(decision.symbol, decision.timeframe, f"Stability Veto: Score {score} < 75")

        # K. THE NEWS SURFER (Volatility Compression)
        if "surfer" in modes and snapshot.candles:
            # Logic: If ATR is dropping (Correction) but Strategy signals Entry (Breakout imminent)
            recent_atr = calculate_atr(snapshot.candles[-5:], period=5)
            med_atr = calculate_atr(snapshot.candles[-20:], period=20)
            if recent_atr and med_atr and recent_atr < (med_atr * 0.8):
                decision.risk_per_trade_pct *= 2.0
                decision.notes = (decision.notes or "") + " | News/Compression Breakout (2.0x)"
        
        # H. HOUSE MONEY (Leveled Up)
        if "house_money" in modes:
            financed = False
            for pos in cls._state.global_positions.values():
                entry = float(pos.get("entry_price") or 0)
                stop = float(pos.get("stop_price") or 0)
                if abs(entry-stop) > 0:
                    curr = snapshot.candles[-1].close
                    pnl_r = ((curr - entry) if pos.get("side")=="long" else (entry - curr)) / abs(entry - stop)
                    if pnl_r >= 2.0: financed = True; break
            if financed:
                decision.risk_per_trade_pct *= 1.5
                decision.notes = (decision.notes or "") + " | House Money (1.5x)"

        # -------------------------------------------------------------
        # 3. THE CLAMP (Nuclear Limiter)
        # -------------------------------------------------------------
        risk_cap = 0.05 # Default hard wall
        if hasattr(snapshot, 'profile') and snapshot.profile:
            if getattr(snapshot.profile, 'nuclear_overrides_enabled', False):
                risk_cap = getattr(snapshot.profile, 'max_risk_cap_override', 0.05)
                # Only log warning if we are actually capped or nearing it
                if decision.risk_per_trade_pct > 0.05:
                    logger.warning(f"☢️ [NUCLEAR] Risk scaling allowed up to {risk_cap*100:.1f}%")

        if decision.risk_per_trade_pct > risk_cap:
            decision.risk_per_trade_pct = risk_cap
            decision.notes = (decision.notes or "") + " | [CLAMPED]"

        return decision

 
    @classmethod
    def handle_runner_exit(cls, decision: AITradeDecision, open_position: dict) -> AITradeDecision:
        """Modifies a TP exit into a partial exit if 'The Runner' is active."""
        if not decision or decision.action not in ["close_position", "exit_long", "exit_short"]:
            return decision
 
        if cls.get_wealth_mode() == "runner":
            # If this is a Target Profit hit (not an emergency or SL)
            if "Target" in (decision.notes or "") or "Armor" in (decision.notes or ""):
                decision.action = "scale_out" # Changed to partial
                decision.notes = (decision.notes or "") + " [WEALTH] Runner Mode: Scaling 50% & Holding for moonshot."
        
        return decision
