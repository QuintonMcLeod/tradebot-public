
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
    hold_decision
)
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
from tradebot_sci.config.models import UserConfig
from tradebot_sci.config.loader import get_settings
from tradebot_sci.runtime.rejection_journal import rejection_journal

logger = logging.getLogger(__name__)

# [ANTIGRAVITY] New Helpers for Safety Guard
def calculate_r_multiple(entry: float, stop: float, current: float, direction: str) -> float:
    risk = abs(entry - stop)
    if risk == 0: return 0.0
    profit = (current - entry) if direction == "long" else (entry - current)
    return profit / risk


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

    # Global State for Safety Measures (Isolated per Asset Class)
    HWM_CAPITAL = {} # {AssetClass: float}
    DRAWDOWN_PAUSE_UNTIL = {} # {AssetClass: datetime}
    
    # State Tracking for New Features (Isolated per Asset Class)
    DAILY_START_CAPITAL = {} # {AssetClass: float}
    DAILY_PNL = {} # {AssetClass: float}
    WEEKLY_START_CAPITAL = {} # {AssetClass: float}
    WEEKLY_PNL = {} # {AssetClass: float}
    MONTHLY_START_CAPITAL = {} # {AssetClass: float}
    MONTHLY_PNL = {} # {AssetClass: float}
    LAST_RESET_DATE = {} # {AssetClass: date}
    LAST_RESET_WEEK = {} # {AssetClass: (year, week)}
    LAST_RESET_MONTH = {} # {AssetClass: (year, month)}
    
    SYMBOL_LOSS_STREAKS = {} # {symbol: count}
    SYMBOL_PAUSE_UNTIL = {} # {symbol: datetime}
    
    TRADE_TIMESTAMPS = {} # {AssetClass: list[datetime]} for Churn Burner
    SENTIMENT_CACHE = {} # {AssetClass: {symbol: (timestamp, sentiment)}}
    WIN_RATE = {} # {AssetClass: float}
    OPEN_POSITIONS = [] # Legacy list of open position dicts

    # [WEALTH MODE] State Tracking - GLOBAL REGISTRY
    # {symbol: position_dict} - Tracks all open trades across OANDA, Gemini, etc.
    GLOBAL_POSITIONS: dict[str, dict] = {} 

    @classmethod
    def update_position(cls, symbol: str, position: Optional[dict]):
        """Updates the global view for a specific symbol to prevent broker blind-spots."""
        if position and isinstance(position, dict):
            cls.GLOBAL_POSITIONS[symbol] = position
        elif symbol in cls.GLOBAL_POSITIONS:
            # If position is None, it means the trade closed or doesn't exist
            del cls.GLOBAL_POSITIONS[symbol]

    @classmethod
    def get_financed_risk_stats(cls):
        """Calculates holistic PnL and count across ALL symbols/brokers."""
        total_pnl = 0.0
        for pos in cls.GLOBAL_POSITIONS.values():
            total_pnl += float(pos.get("unrealized_pnl", 0.0) or 0.0)
        return total_pnl, len(cls.GLOBAL_POSITIONS)

    @classmethod
    def set_current_positions(cls, positions: list[dict]):
        """Legacy helper for single-list updates."""
        for p in positions:
            sym = p.get("symbol")
            if sym: cls.update_position(sym, p)

    @classmethod
    def _update_daily_stats(cls, current_capital: float, asset_class: AssetClass):
        """Updates daily PnL tracking for Greed Guard."""
        today = datetime.now().date()
        if cls.LAST_RESET_DATE.get(asset_class) != today:
            cls.DAILY_START_CAPITAL[asset_class] = current_capital
            cls.DAILY_PNL[asset_class] = 0.0
            cls.LAST_RESET_DATE[asset_class] = today
            cls.TRADE_TIMESTAMPS[asset_class] = [] # Reset churn counter
            cls.SENTIMENT_CACHE[asset_class] = {} # Fix: Dictionary for symbols
            logger.info(f"[SAFETY] New Day Detected for {asset_class.value}. Resetting Daily PnL. Start Capital: ${current_capital:.2f}")
        else:
            start_cap = cls.DAILY_START_CAPITAL.get(asset_class)
            if start_cap:
                cls.DAILY_PNL[asset_class] = current_capital - start_cap

    @classmethod
    def register_trade_completion(cls, symbol: str, is_win: bool):
        """Call this when a trade closes to update streaks."""
        if not is_win:
            cls.SYMBOL_LOSS_STREAKS[symbol] = cls.SYMBOL_LOSS_STREAKS.get(symbol, 0) + 1
            logger.info(f"[STREAK_BREAKER] {symbol} Loss Count: {cls.SYMBOL_LOSS_STREAKS[symbol]}")
        else:
            if symbol in cls.SYMBOL_LOSS_STREAKS:
                 logger.info(f"[STREAK_BREAKER] {symbol} Win. Resetting Streak.")
            cls.SYMBOL_LOSS_STREAKS[symbol] = 0

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

        # 0. State Updates
        hwm = cls.HWM_CAPITAL.get(asset_class, 0.0)
        if current_capital > hwm:
            cls.HWM_CAPITAL[asset_class] = current_capital
        cls._update_daily_stats(current_capital, asset_class)

        # -------------------------------------------------------------
        # P&L PERFORMANCE TARGETS & LIMITS
        # [ANTIGRAVITY] Only activate when capital >= $250.
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
        # Check active pause
        pause_until = cls.DRAWDOWN_PAUSE_UNTIL.get(asset_class)
        if pause_until and now < pause_until:
            return cls._reject(symbol, timeframe, "Drawdown Breaker", f"Drawdown Breaker ({asset_class.value.upper()}) active until {pause_until.strftime('%H:%M')}")
            
        # Check trigger
        if os.getenv("SAFETY_DRAWDOWN_BREAKER_ENABLED", "false").lower() == "true":
            hwm = cls.HWM_CAPITAL.get(asset_class, 0.0)
            if hwm > 0:
                drawdown = (hwm - current_capital) / hwm
                if drawdown > 0.05: # 5% Hard Limit
                     cls.DRAWDOWN_PAUSE_UNTIL[asset_class] = now + timedelta(hours=24)
                     logger.critical(f"[SAFETY] Drawdown Breaker Triggered for {asset_class.value} ({drawdown*100:.1f}%). Pausing 24h.")
                     return cls._reject(symbol, timeframe, "Drawdown Breaker", f"Drawdown Breaker Triggered ({drawdown*100:.1f}%)")

        # -------------------------------------------------------------
        # 2. SESSION LOCKOUT (Time Manager)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_SESSION_LOCKOUT_ENABLED", "false").lower() == "true":
             lockout_hour = int(os.getenv("SAFETY_SESSION_LOCKOUT_HOUR", "12"))
             if est_now.hour >= lockout_hour:
                 return cls._reject(symbol, timeframe, "Session Lockout", f"Session Lockout (After {lockout_hour}:00 EST)")

        # -------------------------------------------------------------
        # 3. [NEW] OPENING RANGE SENTRY (No-Trade Zone)
        # -------------------------------------------------------------
        # Avoid first 15 mins of NYSE Open (9:30 - 9:45 AM EST)
        if os.getenv("SAFETY_OPENING_SENTRY_ENABLED", "false").lower() == "true":
            # Check 9:30-9:45 AM EST
            if est_now.hour == 9 and 30 <= est_now.minute < 45:
                 return cls._reject(symbol, timeframe, "Opening Range Sentry", "Opening Range Sentry (9:30-9:45 AM EST)")

        # -------------------------------------------------------------
        # 4. [NEW] GREED GUARD (Profit Lock)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_GREED_GUARD_ENABLED", "false").lower() == "true":
            target = float(os.getenv("SAFETY_GREED_GUARD_TARGET", "100.0"))
            daily_pnl = cls.DAILY_PNL.get(asset_class, 0.0)
            if daily_pnl >= target:
                return cls._reject(symbol, timeframe, "Greed Guard", f"Greed Guard Active for {asset_class.value} (Daily Goal ${target:.2f} Met)")

        # -------------------------------------------------------------
        # 5. [NEW] STREAK BREAKER (Symbol Cooldown)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_STREAK_BREAKER_ENABLED", "false").lower() == "true":
            # Check Active Pause
            if symbol in cls.SYMBOL_PAUSE_UNTIL:
                if now < cls.SYMBOL_PAUSE_UNTIL[symbol]:
                     return cls._reject(symbol, timeframe, "Streak Breaker", "Streak Breaker Cooldown Active")
                else:
                    del cls.SYMBOL_PAUSE_UNTIL[symbol] # Expired
            
            # Check Trigger (3 Losses)
            if cls.SYMBOL_LOSS_STREAKS.get(symbol, 0) >= 3:
                cls.SYMBOL_PAUSE_UNTIL[symbol] = now + timedelta(hours=4)
                cls.SYMBOL_LOSS_STREAKS[symbol] = 0 # Reset count after triggering
                logger.warning(f"[SAFETY] Streak Breaker triggered for {symbol}. Pausing 4h.")
                return cls._reject(symbol, timeframe, "Streak Breaker", "Streak Breaker Triggered (3 Losses)")

        # -------------------------------------------------------------
        # 6. [NEW] CHURN BURNER (Rate Limit)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_CHURN_BURNER_ENABLED", "false").lower() == "true":
            max_hourly = int(os.getenv("SAFETY_CHURN_BURNER_MAX", "5"))
            cutoff = now - timedelta(hours=1)
            # Prune old timestamps
            timestamps = cls.TRADE_TIMESTAMPS.get(asset_class, [])
            timestamps = [t for t in timestamps if t > cutoff]
            cls.TRADE_TIMESTAMPS[asset_class] = timestamps
            if len(timestamps) >= max_hourly:
                return cls._reject(symbol, timeframe, "Churn Burner", f"Churn Burner ({asset_class.value.upper()}) Active (Max {max_hourly}/hr)")

        # -------------------------------------------------------------
        # 7. [NEW] VOLATILITY VETO (ATR Filter)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_VOLATILITY_VETO_ENABLED", "false").lower() == "true":
            atr = calculate_atr(snapshot.candles, period=14)
            if atr:
                last_price = snapshot.candles[-1].close
                atr_pct = (atr / last_price) * 100
                
                # Min Volatility (Avoiding Dead Markets) - Default 0.05%
                min_vol = float(os.getenv("SAFETY_VOLATILITY_MIN_PCT", "0.05"))
                # Max Volatility (Avoiding Explosions) - Default 5.0%
                max_vol = float(os.getenv("SAFETY_VOLATILITY_MAX_PCT", "5.0"))
                
                if atr_pct < min_vol:
                     return cls._reject(symbol, timeframe, "Volatility Veto", f"Volatility Veto: Too Dead (ATR {atr_pct:.3f}% < {min_vol}%)")
                if atr_pct > max_vol:
                     return cls._reject(symbol, timeframe, "Volatility Veto", f"Volatility Veto: Too Volatile (ATR {atr_pct:.3f}% > {max_vol}%)")

        # 8. [NEW] AI SENTIMENT SHIELD (The Independent Veto)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_SENTIMENT_SHIELD_ENABLED", "false").lower() == "true" and ai_client:
             try:
                 # [ANTIGRAVITY CACHE] Prevent "Itchy Trigger Finger" / excessive API calls
                 class_cache = cls.SENTIMENT_CACHE.get(asset_class, {})
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
                     cls.SENTIMENT_CACHE[asset_class] = class_cache
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
        # [ANTIGRAVITY FIX] Isolated per asset class (Forex entries only care about Forex leverage)
        if os.getenv("SAFETY_LEVERAGE_SENTRY_ENABLED", "true").lower() == "true":
            # Determine asset class of the symbol being checked
            target_class = classify_symbol(symbol)
            
            # [ANTIGRAVITY] Default to general cap, but check for class-specific overrides (e.g. SAFETY_MAX_FOREX_LEVERAGE)
            default_cap = float(os.getenv("SAFETY_MAX_TOTAL_LEVERAGE", "3.0"))
            class_cap_env = f"SAFETY_MAX_{target_class.value.upper()}_LEVERAGE"
            max_leverage = float(os.getenv(class_cap_env, str(default_cap)))
            
            # Calculate total notional value only for positions in the same asset class
            total_notional = 0.0
            for pos_symbol, pos in cls.GLOBAL_POSITIONS.items():
                if classify_symbol(pos_symbol) == target_class:
                    price = float(pos.get("avg_price") or pos.get("entry_price") or 0)
                    size = abs(float(pos.get("size") or 0))
                    total_notional += (price * size)
            
            # current_capital is passed per-broker (already isolated)
            current_leverage = total_notional / current_capital if current_capital > 0 else 0
            if current_leverage > max_leverage:
                logger.warning(f"[SAFETY] Leverage Sentry VETO for {target_class.value}: Current Leverage {current_leverage:.1f}x exceeds Cap {max_leverage}x")
                return cls._reject(symbol, timeframe, "Leverage Sentry", f"Leverage Sentry ({target_class.value.upper()}): {current_leverage:.1f}x > {max_leverage}x")

        # -------------------------------------------------------------
        # 10. [NEW] FEE SHIELD (Capital Bleed Prevention)
        # -------------------------------------------------------------
        # Ensures the trade has enough "meat on the bone" to cover broker fees.
        if os.getenv("SAFETY_FEE_SHIELD_ENABLED", "true").lower() == "true":
            from tradebot_sci.strategy.decisions import AITradeDecision
            if isinstance(ai_client, AITradeDecision): # If passed as decision for validation
                decision = ai_client
                entry = float(decision.entry_price or 0.0)
                tp = float(decision.take_profit or 0.0)
                if entry > 0 and tp > 0:
                    potential_reward_pct = abs(tp - entry) / entry
                    
                    # Estimate round-trip fee (Gemini: 0.4% * 2 = 0.8%)
                    # We add a 1.5x safety multiplier (needs to be 1.5x the fee to be worth taking)
                    est_fee_rt = 0.008 
                    min_edge_pct = est_fee_rt * 1.5 # 1.2% min move expected
                    
                    if potential_reward_pct < min_edge_pct:
                         logger.warning(f"[SAFETY] FEE SHIELD: {symbol} Expected Reward {potential_reward_pct:.2%} < Min Edge {min_edge_pct:.2%} (Fees)")
                         return cls._reject(symbol, timeframe, "Fee Shield", f"Fee Shield: Reward {potential_reward_pct:.2%} < Fees")

        return None


    @classmethod
    def notify_entry(cls, symbol: str):
        """Call this when a trade is effectively entered to update rate limits."""
        asset_class = classify_symbol(symbol)
        if asset_class not in cls.TRADE_TIMESTAMPS:
            cls.TRADE_TIMESTAMPS[asset_class] = []
        cls.TRADE_TIMESTAMPS[asset_class].append(datetime.now())

    @classmethod
    def augment_exit_decision(cls, decision: Optional[AITradeDecision], open_position: dict, snapshot: MarketSnapshot) -> AITradeDecision:
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
                except: pass
            if isinstance(entry_time, datetime):
                bars_since = len([c for c in snapshot.candles if c.timestamp >= entry_time])

        initial_risk = abs(entry_price - current_stop)
        profit_dist = (current_price - entry_price) if direction == "long" else (entry_price - current_price)
        r_multiple = profit_dist / initial_risk if initial_risk > 0 else 0.0

        # 1. CENTRALIZED TARGET MONITOR (TP/SL)
        # Support Moonshot Elevated TP
        pos_record = cls.GLOBAL_POSITIONS.get(snapshot.symbol, {})
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
                 logger.info(f"[SAFETY] Stale Sniper TRIGGERED for {snapshot.symbol} after {bars_since} bars.")
                 return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Stale Exit ({bars_since} bars)")

        # B. Flash-Trap / Blow-off Seller (Volatility Exhaustion)
        shield_v = settings.safety.safety_flash_trap_enabled
        weapon_v = settings.safety.wealth_exit_blowoff_enabled
        if (shield_v or weapon_v) and len(snapshot.candles) >= 14:
            # [ANTIGRAVITY FIX] Usage of keyword-only period
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
                is_contradiction = (direction == "long" and htf_dir == "bearish") or \
                                   (direction == "short" and htf_dir == "bullish")
                if is_contradiction:
                    logger.info(f"[SAFETY] Regime-Flip TRIGGERED for {snapshot.symbol}. HTF is {htf_dir}.")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Regime Flip: {htf_dir.upper()}")

        # 3. OFFENSIVE WEALTH WEAPONS
        # A. Moonshot Target Elevator (Impulse Hold)
        if settings.safety.wealth_exit_moonshot_enabled:
            # If 1R hit within 3 bars, double the elevator
            if bars_since <= 3 and r_multiple >= 1.0 and not elevated_tp:
                 orig_tp = float(open_position.get("take_profit") or open_position.get("tp_price") or 0.0)
                 if orig_tp > 0:
                      new_tp = entry_price + (orig_tp - entry_price) * 2
                      cls.GLOBAL_POSITIONS[snapshot.symbol]["elevated_tp"] = new_tp
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

        # B. THE GREEDY EXIT (Standard Trailing Stop)
        # -------------------------------------------------------------------------
        # Uses ATR-based or fixed pct trails to chase runs.
        # "Trailing Stop Enabled" in UI maps to this.
        use_greedy_exit = os.getenv("TRAILING_STOP_ENABLED", "false").lower() == "true"
        
        if use_greedy_exit:
             # Default to ATR-based if available, or fallback to fixed 0.5%
             # [ANTIGRAVITY FIX] Usage of keyword-only period
             atr = calculate_atr(snapshot.candles[-14:], period=14)
             trail_dist = 0.0
             
             if atr:
                 trail_dist = atr * 1.5 # Standard 1.5 ATR trail
             else:
                 trail_dist = current_price * 0.005 # Fallback 0.5%
             
             if direction == "long":
                 potential_stop = current_price - trail_dist
                 # Only move UP
                 if potential_stop > current_stop:
                      if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss < potential_stop)):
                           return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="long",
                                phase="management",
                                reason=f"[SAFETY] The Greedy Exit: Trailing by {trail_dist:.4f}",
                                stop_loss=potential_stop
                           )
             else: # short
                 potential_stop = current_price + trail_dist
                 # Only move DOWN
                 if current_stop == 0 or potential_stop < current_stop:
                      if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > potential_stop)):
                           return hold_decision(
                                symbol=snapshot.symbol,
                                timeframe=snapshot.timeframe,
                                bias="short",
                                phase="management",
                                reason=f"[SAFETY] The Greedy Exit: Trailing by {trail_dist:.4f}",
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


        # [ANTIGRAVITY] Enabled ATR Armor logic
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
            cls.WIN_RATE[asset_class] = wr
        else:
            # Fallback: Apply to all
            for ac in AssetClass:
                cls.WIN_RATE[ac] = wr

    @classmethod
    def set_current_positions(cls, positions: list[dict]):
        """Updates the global view of positions for risk-based calculations."""
        # This updates GLOBAL_POSITIONS via set_current_positions(legacy) logic
        # But we also have OPEN_POSITIONS which might be redundant now. 
        # Let's keep them in sync if used by legacy performance modes.
        cls.OPEN_POSITIONS = positions
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
    def augment_entry_decision(cls, decision: AITradeDecision, score: float, htf_strength: float, snapshot: MarketSnapshot, ai_client: Optional[Any] = None) -> AITradeDecision:
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
        # Default if no foundation is found
        base_risk = decision.risk_per_trade_pct or 0.015 
        
        # Priority Check: Detect which Foundation is active (start with "simplicity" default)
        # If multiple foundations are accidentally set, we pick priority: Kelly > Flywheel > Smooth > Simplicity
        
        # A. KELLY CRITERION (Math Edge)
        if "kelly" in modes:
            w = cls.WIN_RATE.get(asset_class, 0.55)
            r = 2.0 # Assume 2:1 RR conservative average
            kelly_f = w - (1 - w) / r
            if kelly_f > 0:
                base_risk = kelly_f * 0.5 # Half-Kelly for safety
                decision.notes = (decision.notes or "") + f" [WEALTH] Kelly Base ({asset_class.value}): {base_risk*100:.1f}%"
        
        # B. COMPOUND FLYWHEEL (Growth Based)
        elif "flywheel" in modes:
             daily_pnl = cls.DAILY_PNL.get(asset_class, 0.0)
             if daily_pnl > 0:
                  milestone = 200.0
                  boost = (daily_pnl // milestone) * 0.001
                  base_risk = min(0.015 + boost, 0.05) # Cap base at 5%
                  decision.notes = (decision.notes or "") + f" [WEALTH] Flywheel Base ({asset_class.value}): {base_risk*100:.1f}%"

        # C. EQUITY SMOOTHING (Anti-Tilt / Mean Reversion)
        elif "smooth" in modes:
            # Boost if at ATH, slash if in drawdown
            hwm = cls.HWM_CAPITAL.get(asset_class, 0.0)
            daily_pnl = cls.DAILY_PNL.get(asset_class, 0.0)
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
                # [ANTIGRAVITY FIX] Usage of keyword-only period
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
            for pos in cls.GLOBAL_POSITIONS.values():
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
