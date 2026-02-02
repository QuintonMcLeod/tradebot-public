
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision, close_position_decision
from tradebot_sci.strategy.icc_signals import calculate_atr
# Import AI Client type for type hinting if needed, but Optional[Any] works to avoid circular imports
from typing import Any

logger = logging.getLogger(__name__)

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

    # Global State for Safety Measures
    HWM_CAPITAL = 0.0
    DRAWDOWN_PAUSE_UNTIL = None
    
    # State Tracking for New Features
    DAILY_START_CAPITAL = None
    DAILY_PNL = 0.0
    LAST_RESET_DATE = None
    
    SYMBOL_LOSS_STREAKS = {} # {symbol: count}
    SYMBOL_PAUSE_UNTIL = {} # {symbol: datetime}
    
    TRADE_TIMESTAMPS = [] # List of datetimes for Churn Burner
    SENTIMENT_CACHE = {} # {(symbol): (timestamp, sentiment)}

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
    def _update_daily_stats(cls, current_capital: float):
        """Updates daily PnL tracking for Greed Guard."""
        today = datetime.now().date()
        if cls.LAST_RESET_DATE != today:
            cls.DAILY_START_CAPITAL = current_capital
            cls.DAILY_PNL = 0.0
            cls.LAST_RESET_DATE = today
            cls.TRADE_TIMESTAMPS = [] # Reset churn counter
            cls.SENTIMENT_CACHE = {} # Reset daily sentiment cache
            logger.info(f"[SAFETY] New Day Detected. Resetting Daily PnL. Start Capital: ${current_capital:.2f}")
        else:
            if cls.DAILY_START_CAPITAL:
                cls.DAILY_PNL = current_capital - cls.DAILY_START_CAPITAL

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
    def check_entry_safety(cls, symbol: str, timeframe: str, current_capital: float, snapshot: MarketSnapshot, ai_client: Optional[Any] = None) -> Optional[AITradeDecision]:
        """
        Runs ALL pre-entry checks.
        Returns a stand_aside_decision if unsafe. Returns None if safe to proceed.
        """
        now = datetime.now()
        est_now = datetime.now(ZoneInfo("America/New_York"))

        # 0. State Updates
        if current_capital > cls.HWM_CAPITAL:
            cls.HWM_CAPITAL = current_capital
        cls._update_daily_stats(current_capital)

        # -------------------------------------------------------------
        # 1. DRAWDOWN BREAKER (Account Circuit Breaker)
        # -------------------------------------------------------------
        # Check active pause
        if cls.DRAWDOWN_PAUSE_UNTIL and now < cls.DRAWDOWN_PAUSE_UNTIL:
            return stand_aside_decision(symbol, timeframe, f"Drawdown Breaker Active until {cls.DRAWDOWN_PAUSE_UNTIL.strftime('%H:%M')}")
            
        # Check trigger
        if os.getenv("SAFETY_DRAWDOWN_BREAKER_ENABLED", "false").lower() == "true" and cls.HWM_CAPITAL > 0:
            drawdown = (cls.HWM_CAPITAL - current_capital) / cls.HWM_CAPITAL
            if drawdown > 0.05: # 5% Hard Limit
                 cls.DRAWDOWN_PAUSE_UNTIL = now + timedelta(hours=24)
                 logger.critical(f"[SAFETY] Drawdown Breaker Triggered ({drawdown*100:.1f}%). Pausing 24h.")
                 return stand_aside_decision(symbol, timeframe, f"Drawdown Breaker Triggered ({drawdown*100:.1f}%)")

        # -------------------------------------------------------------
        # 2. SESSION LOCKOUT (Time Manager)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_SESSION_LOCKOUT_ENABLED", "false").lower() == "true":
             lockout_hour = int(os.getenv("SAFETY_SESSION_LOCKOUT_HOUR", "12"))
             if est_now.hour >= lockout_hour:
                 return stand_aside_decision(symbol, timeframe, f"Session Lockout (After {lockout_hour}:00 EST)")

        # -------------------------------------------------------------
        # 3. [NEW] OPENING RANGE SENTRY (No-Trade Zone)
        # -------------------------------------------------------------
        # Avoid first 15 mins of NYSE Open (9:30 - 9:45 AM EST)
        if os.getenv("SAFETY_OPENING_SENTRY_ENABLED", "false").lower() == "true":
            # Check 9:30-9:45 AM EST
            if est_now.hour == 9 and 30 <= est_now.minute < 45:
                 return stand_aside_decision(symbol, timeframe, "Opening Range Sentry (9:30-9:45 AM EST)")

        # -------------------------------------------------------------
        # 4. [NEW] GREED GUARD (Profit Lock)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_GREED_GUARD_ENABLED", "false").lower() == "true":
            target = float(os.getenv("SAFETY_GREED_GUARD_TARGET", "100.0"))
            if cls.DAILY_PNL >= target:
                return stand_aside_decision(symbol, timeframe, f"Greed Guard Active (Daily Goal ${target:.2f} Met)")

        # -------------------------------------------------------------
        # 5. [NEW] STREAK BREAKER (Symbol Cooldown)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_STREAK_BREAKER_ENABLED", "false").lower() == "true":
            # Check Active Pause
            if symbol in cls.SYMBOL_PAUSE_UNTIL:
                if now < cls.SYMBOL_PAUSE_UNTIL[symbol]:
                     return stand_aside_decision(symbol, timeframe, "Streak Breaker Cooldown Active")
                else:
                    del cls.SYMBOL_PAUSE_UNTIL[symbol] # Expired
            
            # Check Trigger (3 Losses)
            if cls.SYMBOL_LOSS_STREAKS.get(symbol, 0) >= 3:
                cls.SYMBOL_PAUSE_UNTIL[symbol] = now + timedelta(hours=4)
                cls.SYMBOL_LOSS_STREAKS[symbol] = 0 # Reset count after triggering
                logger.warning(f"[SAFETY] Streak Breaker triggered for {symbol}. Pausing 4h.")
                return stand_aside_decision(symbol, timeframe, "Streak Breaker Triggered (3 Losses)")

        # -------------------------------------------------------------
        # 6. [NEW] CHURN BURNER (Rate Limit)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_CHURN_BURNER_ENABLED", "false").lower() == "true":
            max_hourly = int(os.getenv("SAFETY_CHURN_BURNER_MAX", "5"))
            cutoff = now - timedelta(hours=1)
            # Prune old timestamps
            cls.TRADE_TIMESTAMPS = [t for t in cls.TRADE_TIMESTAMPS if t > cutoff]
            if len(cls.TRADE_TIMESTAMPS) >= max_hourly:
                return stand_aside_decision(symbol, timeframe, f"Churn Burner Active (Max {max_hourly}/hr)")

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
                     return stand_aside_decision(symbol, timeframe, f"Volatility Veto: Too Dead (ATR {atr_pct:.3f}% < {min_vol}%)")
                if atr_pct > max_vol:
                     return stand_aside_decision(symbol, timeframe, f"Volatility Veto: Too Volatile (ATR {atr_pct:.3f}% > {max_vol}%)")

        # 8. [NEW] AI SENTIMENT SHIELD (The Independent Veto)
        # -------------------------------------------------------------
        if os.getenv("SAFETY_SENTIMENT_SHIELD_ENABLED", "false").lower() == "true" and ai_client:
             try:
                 # [ANTIGRAVITY CACHE] Prevent "Itchy Trigger Finger" / excessive API calls
                 cached = cls.SENTIMENT_CACHE.get(symbol)
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
                     cls.SENTIMENT_CACHE[symbol] = (now, sentiment)
                     logger.info(f"[SAFETY] AI Shield Refreshed for {symbol}: {sentiment}")
                 
                 if "DANGEROUS" in sentiment:
                      if not cache_valid: logger.warning(f"[SAFETY] AI Sentiment Shield blocked {symbol}: {sentiment}")
                      return stand_aside_decision(symbol, timeframe, f"AI Sentiment Shield: {sentiment}")
                      
             except Exception as e:
                 logger.warning(f"[SAFETY] AI Shield failed request: {e}")

        return None

    @classmethod
    def notify_entry(cls):
        """Call this when a trade is effectively entered to update rate limits."""
        cls.TRADE_TIMESTAMPS.append(datetime.now())

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

        # 2. DEFENSIVE SHIELDS
        # A. Stale-Position Sniper (Time Decay)
        if os.getenv("SAFETY_STALE_SNIPER_ENABLED", "false").lower() == "true":
            bars_limit = int(os.getenv("SAFETY_STALE_SNIPER_BARS", "20"))
            if bars_since >= bars_limit:
                 logger.info(f"[SAFETY] Stale Sniper TRIGGERED for {snapshot.symbol} after {bars_since} bars.")
                 return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Stale Exit ({bars_since} bars)")

        # B. Flash-Trap / Blow-off Seller (Volatility Exhaustion)
        shield_v = os.getenv("SAFETY_FLASH_TRAP_ENABLED", "false").lower() == "true"
        weapon_v = os.getenv("WEALTH_EXIT_BLOWOFF_ENABLED", "false").lower() == "true"
        if (shield_v or weapon_v) and len(snapshot.candles) >= 14:
            curr_atr = calculate_atr(snapshot.candles[-14:], 14)
            hist_atr = calculate_atr(snapshot.candles[-50:], 14)
            if curr_atr and hist_atr:
                multiplier = 3.5 if weapon_v else 2.5
                if curr_atr > (hist_atr * multiplier):
                    logger.info(f"[SAFETY] Volatility Peak TRIGGERED for {snapshot.symbol} (ATR: {curr_atr:.4f})")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason="Volatility Blow-off Exit")

        # C. Regime-Flip Veto (HTF Alignment)
        if os.getenv("SAFETY_REGIME_FLIP_ENABLED", "false").lower() == "true":
            htf_dir = snapshot.trend_htf.direction
            if htf_dir and htf_dir != "neutral":
                is_contradiction = (direction == "long" and htf_dir == "bearish") or \
                                   (direction == "short" and htf_dir == "bullish")
                if is_contradiction:
                    logger.info(f"[SAFETY] Regime-Flip TRIGGERED for {snapshot.symbol}. HTF is {htf_dir}.")
                    return close_position_decision(snapshot.symbol, snapshot.timeframe, reason=f"Regime Flip: {htf_dir.upper()}")

        # 3. OFFENSIVE WEALTH WEAPONS
        # A. Moonshot Target Elevator (Impulse Hold)
        if os.getenv("WEALTH_EXIT_MOONSHOT_ENABLED", "false").lower() == "true":
            # If 1R hit within 3 bars, double the elevator
            if bars_since <= 3 and r_multiple >= 1.0 and not elevated_tp:
                 orig_tp = float(open_position.get("take_profit") or open_position.get("tp_price") or 0.0)
                 if orig_tp > 0:
                      new_tp = entry_price + (orig_tp - entry_price) * 2
                      cls.GLOBAL_POSITIONS[snapshot.symbol]["elevated_tp"] = new_tp
                      logger.info(f"[WEALTH] Moonshot Elevator ACTIVE for {snapshot.symbol}: Target doubled to {new_tp:.4f}")

        # 4. ATR ARMOR (Consolidated with Gamma Squeeze)
        if os.getenv("SAFETY_ATR_SHIELD_ENABLED", "true").lower() == "true":
            # 1. Breakeven (1R)
            if initial_risk > 0 and r_multiple >= 1.0:
                if (direction == "long" and current_stop < entry_price) or \
                   (direction == "short" and current_stop > entry_price):
                    if not decision: 
                         return AITradeDecision(
                            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                            bias="long" if direction == "long" else "short", 
                            phase="management", action="hold", stop_loss=entry_price,
                            notes="[SAFETY] Armor: Breakeven (1R)"
                        )

            # 2. Dynamic Trailing (with Gamma Squeeze)
            trailing_pct = 0.05
            if os.getenv("WEALTH_EXIT_GAMMA_ENABLED", "false").lower() == "true":
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
                            return AITradeDecision(
                                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                                bias="long", phase="management", action="hold", stop_loss=target_stop,
                                notes=f"[SAFETY] Armor: {f'Gamma Trail' if trailing_pct < 0.05 else 'Trailing'} (${peak:.2f})"
                            )
                else:
                    trough = min(c.low for c in relevant)
                    target_stop = trough * (1 + trailing_pct)
                    if current_stop == 0 or target_stop < current_stop:
                        if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > target_stop)):
                            return AITradeDecision(
                                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                                bias="short", phase="management", action="hold", stop_loss=target_stop,
                                notes=f"[SAFETY] Armor: {f'Gamma Trail' if trailing_pct < 0.05 else 'Trailing'} (${trough:.2f})"
                            )

        return decision
 
    # =========================================================================
    # PERFORMANCE & PROFITS (WEALTH CREATION)
    # =========================================================================
    # [WEALTH MODE] State Tracking
    OPEN_POSITIONS = [] # List of open position dicts
    WIN_RATE = 0.55 # Default win rate for Kelly
    
    @classmethod
    def set_win_rate(cls, wr: float):
        cls.WIN_RATE = wr

    @classmethod
    def set_current_positions(cls, positions: list[dict]):
        """Updates the global view of positions for risk-based calculations."""
        cls.OPEN_POSITIONS = positions

    @classmethod
    def get_active_wealth_modes(cls) -> list[str]:
        """Returns a list of active performance modes from the env var (comma-separated)."""
        raw = os.getenv("PERFORMANCE_MODE", "none").lower()
        if not raw or raw == "none":
            return []
        return [m.strip() for m in raw.split(",") if m.strip()]

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
        # 1. ESTABLISH BASE RISK (The Foundation)
        # -------------------------------------------------------------
        # Default if no foundation is found
        base_risk = decision.risk_per_trade_pct or 0.015 
        
        # Priority Check: Detect which Foundation is active (start with "simplicity" default)
        # If multiple foundations are accidentally set, we pick priority: Kelly > Flywheel > Smooth > Simplicity
        
        # A. KELLY CRITERION (Math Edge)
        if "kelly" in modes:
            w = cls.WIN_RATE
            r = 2.0 # Assume 2:1 RR conservative average
            kelly_f = w - (1 - w) / r
            if kelly_f > 0:
                base_risk = kelly_f * 0.5 # Half-Kelly for safety
                decision.notes = (decision.notes or "") + f" [WEALTH] Kelly Base: {base_risk*100:.1f}%"
        
        # B. COMPOUND FLYWHEEL (Growth Based)
        elif "flywheel" in modes:
             if cls.DAILY_PNL > 0:
                  milestone = 200.0
                  boost = (cls.DAILY_PNL // milestone) * 0.001
                  base_risk = min(0.015 + boost, 0.05) # Cap base at 5%
                  decision.notes = (decision.notes or "") + f" [WEALTH] Flywheel Base: {base_risk*100:.1f}%"

        # C. EQUITY SMOOTHING (Anti-Tilt / Mean Reversion)
        elif "smooth" in modes:
            # Boost if at ATH, slash if in drawdown
            if cls.DAILY_PNL < -0.02 * cls.HWM_CAPITAL: # 2% Daily Drawdown
                base_risk = 0.005 # Slash to 0.5%
                decision.notes = (decision.notes or "") + " [WEALTH] Anti-Tilt Base (Defensive)"
            elif cls.HWM_CAPITAL > 0 and cls.DAILY_PNL > 0:
                base_risk = 0.02 # Boost to 2%
                decision.notes = (decision.notes or "") + " [WEALTH] Momentum Base"

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
                recent_atr = calculate_atr(candles[-14:], 14)
                hist_atr = calculate_atr(candles, 100)
                if recent_atr and hist_atr and recent_atr < (hist_atr * 0.6):
                    decision.risk_per_trade_pct *= 2.0
                    decision.notes = (decision.notes or "") + " | Coil Breakout (2.0x)"

        # F. HARMONIC GHOST (Liquidity Magnet)
        if "ghost" in modes:
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
