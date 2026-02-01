
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision, close_position_decision
from tradebot_sci.strategy.icc_signals import calculate_atr

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
    
    # [WEALTH MODE] State Tracking
    OPEN_POSITIONS = [] # List of open position dicts for house money checks
    
    @classmethod
    def set_current_positions(cls, positions: list[dict]):
        """Updates the global view of positions for risk-based calculations."""
        cls.OPEN_POSITIONS = positions

    @classmethod
    def _update_daily_stats(cls, current_capital: float):
        """Updates daily PnL tracking for Greed Guard."""
        today = datetime.now().date()
        if cls.LAST_RESET_DATE != today:
            cls.DAILY_START_CAPITAL = current_capital
            cls.DAILY_PNL = 0.0
            cls.LAST_RESET_DATE = today
            cls.TRADE_TIMESTAMPS = [] # Reset churn counter daily too? No, mostly rolling window.
            # But we reset PnL.
            logger.info(f"[SAFETY] New Day Detected. Resetting Daily PnL. Start Capital: ${current_capital:.2f}")
        else:
            if cls.DAILY_START_CAPITAL:
                cls.DAILY_PNL = current_capital - cls.DAILY_START_CAPITAL

    @classmethod
    def register_trade_completion(cls, symbol: str, is_win: bool):
        """Call this from Engine when a trade closes to update streaks."""
        if not is_win:
            cls.SYMBOL_LOSS_STREAKS[symbol] = cls.SYMBOL_LOSS_STREAKS.get(symbol, 0) + 1
            logger.info(f"[STREAK_BREAKER] {symbol} Loss Count: {cls.SYMBOL_LOSS_STREAKS[symbol]}")
        else:
            if symbol in cls.SYMBOL_LOSS_STREAKS:
                 logger.info(f"[STREAK_BREAKER] {symbol} Win. Resetting Streak.")
            cls.SYMBOL_LOSS_STREAKS[symbol] = 0

    @classmethod
    def check_entry_safety(cls, symbol: str, timeframe: str, current_capital: float, snapshot: MarketSnapshot) -> Optional[AITradeDecision]:
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

        return None

    @classmethod
    def notify_entry(cls):
        """Call this when a trade is effectively entered to update rate limits."""
        cls.TRADE_TIMESTAMPS.append(datetime.now())

    @classmethod
    def augment_exit_decision(cls, decision: Optional[AITradeDecision], open_position: dict, snapshot: MarketSnapshot) -> AITradeDecision:
        """
        Applies ATR Armor and other exit safeguards.
        If the Strategy suggests an exit, we usually respect it.
        If the Strategy is silent (None), SafetyGuard can propose a management exit.
        """
        
        # [SAFETY SYNC] Only apply if enabled
        if os.getenv("SAFETY_ATR_SHIELD_ENABLED", "true").lower() != "true":
            return decision

        entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0.0)
        if entry_price == 0: return decision
        
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction") or open_position.get("side")
        current_stop = float(open_position.get("stop_price") or 0.0)
        
        if not direction: return decision
        
        # -------------------------------------------------------------
        # ATR ARMOR LOGIC (Consolidated)
        # -------------------------------------------------------------
        
        # 1. Breakeven (1R)
        initial_risk = abs(entry_price - current_stop)
        if initial_risk > 0:
            profit_dist = (current_price - entry_price) if direction == "long" else (entry_price - current_price)
            r_multiple = profit_dist / initial_risk
            
            # Check Long
            if direction == "long":
                # If stop is below entry, and we are > 1R...
                if current_stop < entry_price and r_multiple >= 1.0:
                    # Prefer Safety Move over Strategy Silence
                    if not decision: 
                         return AITradeDecision(
                            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                            bias="long", phase="management", action="hold", stop_loss=entry_price,
                            notes="[SAFETY] Armor: Breakeven (1R)"
                        )
            # Check Short
            elif direction == "short":
                if current_stop > entry_price and r_multiple >= 1.0:
                    if not decision:
                         return AITradeDecision(
                            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                            bias="short", phase="management", action="hold", stop_loss=entry_price,
                            notes="[SAFETY] Armor: Breakeven (1R)"
                        )

        # 2. Dynamic Trailing (Peak-based)
        # (Simplified for consolidation - 5% Trailing)
        # Note: Strategy-specific implementations were more complex.
        # We'll implement a robust general one here.
        
        trailing_pct = 0.05
        entry_time = open_position.get("entry_time")
        if entry_time:
             # Just look at candles since entry
            relevant = [c for c in snapshot.candles if c.timestamp >= entry_time]
            if relevant:
                if direction == "long":
                    peak = max(c.high for c in relevant)
                    target_stop = peak * (1 - trailing_pct)
                    if target_stop > current_stop:
                        if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss < target_stop)):
                            return AITradeDecision(
                                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                                bias="long", phase="management", action="hold", stop_loss=target_stop,
                                notes=f"[SAFETY] Armor: Trailing Stop (${peak:.2f})"
                            )
                else:
                    trough = min(c.low for c in relevant)
                    target_stop = trough * (1 + trailing_pct)
                    if current_stop == 0 or target_stop < current_stop:
                        if not decision or (decision.action == "hold" and (not decision.stop_loss or decision.stop_loss > target_stop)):
                            return AITradeDecision(
                                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                                bias="short", phase="management", action="hold", stop_loss=target_stop,
                                notes=f"[SAFETY] Armor: Trailing Stop (${trough:.2f})"
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
    def get_wealth_mode(cls) -> str:
        """Returns the active performance mode, ensuring mutual exclusivity."""
        return os.getenv("PERFORMANCE_MODE", "none").lower()
 
    @classmethod
    def _update_daily_stats(cls, current_capital: float):
        """Updates daily PnL tracking for Greed Guard."""
        today = datetime.now().date()
        if cls.LAST_RESET_DATE != today:
            cls.DAILY_START_CAPITAL = current_capital
            cls.DAILY_PNL = 0.0
            cls.LAST_RESET_DATE = today
            cls.TRADE_TIMESTAMPS = [] 
            logger.info(f"[SAFETY] New Day Detected. Resetting Daily PnL. Start Capital: ${current_capital:.2f}")
        else:
            if cls.DAILY_START_CAPITAL:
                cls.DAILY_PNL = current_capital - cls.DAILY_START_CAPITAL

    @classmethod
    def augment_entry_decision(cls, decision: AITradeDecision, score: float, htf_strength: float, snapshot: MarketSnapshot, ai_client: Optional[TradeSciAIClient] = None) -> AITradeDecision:
        """
        Applies "Offensive" performance overrides to an entry decision.
        Returns the modified (or original) decision.
        """
        if not decision or decision.action not in ["enter_long", "enter_short", "scale_in"]:
            return decision
 
        mode = cls.get_wealth_mode()
        if mode == "none":
            return decision
 
        base_risk = decision.risk_per_trade_pct or 0.015

        # ☢️ NUCLEAR OVERRIDES (Hidden Walls Bypass)
        risk_cap = 0.05 # Default hard wall
        if hasattr(snapshot, 'profile') and snapshot.profile:
            if getattr(snapshot.profile, 'nuclear_overrides_enabled', False):
                risk_cap = getattr(snapshot.profile, 'max_risk_cap_override', 0.05)
                logger.warning(f"☢️ [NUCLEAR] Bypassing Safety Walls. Risk Cap set to {risk_cap*100:.1f}%")

        # 1. THE SNIPER GRADE (A+ Bet)
        if mode == "sniper":
            if score >= 90:
                decision.risk_per_trade_pct = risk_cap 
                decision.notes = (decision.notes or "") + f" [WEALTH] Sniper Mode: Score {score} -> {risk_cap*100:.1f}% Risk"
                logger.info(f"[WEALTH] SNIPER GRADE TRIGGERED: {decision.symbol} (Score: {score})")
 
        # 2. REGIME SYNC (Adaptive Risk)
        elif mode == "regime_sync":
            if htf_strength >= 0.7:
                decision.risk_per_trade_pct = base_risk * 1.5
                decision.notes = (decision.notes or "") + f" [WEALTH] Regime Sync: Aggressive (+{htf_strength:.2f})"
            elif htf_strength <= 0.3:
                decision.risk_per_trade_pct = base_risk * 0.5
                decision.notes = (decision.notes or "") + f" [WEALTH] Regime Sync: Defensive (-{htf_strength:.2f})"
 
        # 3. COMPOUND FLYWHEEL (Equity Milestones)
        elif mode == "flywheel":
             if cls.DAILY_PNL > 0:
                  milestone = 200.0
                  boost = (cls.DAILY_PNL // milestone) * 0.001
                  if boost > 0:
                      decision.risk_per_trade_pct = min(base_risk + boost, risk_cap)
                      decision.notes = (decision.notes or "") + f" [WEALTH] Flywheel Boost: +{boost*100:.1f}%"
 
        # 4. HOUSE MONEY ACCELERATOR (Leveraged Profit)
        elif mode == "house_money":
            financed = False
            for pos in cls.OPEN_POSITIONS:
                entry = float(pos.get("entry_price") or pos.get("avg_price") or 0.0)
                stop = float(pos.get("stop_price") or 0.0)
                dist = abs(entry - stop)
                if dist > 0:
                    current = snapshot.candles[-1].close if snapshot.candles else entry
                    profit = (current - entry) if (pos.get("side") == "long") else (entry - current)
                    if profit / dist >= 2.0:
                        financed = True
                        break
            if financed:
                decision.risk_per_trade_pct = (decision.risk_per_trade_pct or base_risk) * 1.5 # Boosted risk
                decision.notes = (decision.notes or "") + " [WEALTH] House Money Unlocked (Financed by winner)"

        # 5. [NEW] KELLY CRITERION (Math Edge)
        elif mode == "kelly":
            # Simple Kelly: K% = W - (1-W)/R  where R is Avg RR.
            # We'll use a conservative Kelly (fractional 0.5)
            w = cls.WIN_RATE
            r = 2.0 # Assume 2:1 RR conservative average
            kelly_f = w - (1 - w) / r
            if kelly_f > 0:
                # Fractional Kelly for safety
                decision.risk_per_trade_pct = min(kelly_f * 0.5, risk_cap)
                decision.notes = (decision.notes or "") + f" [WEALTH] Kelly Optimized: {decision.risk_per_trade_pct*100:.1f}% Risk"

        # 6. [NEW] CORRELATION HYDRA (Basket Scaling)
        elif mode == "hydra":
            # If multiple assets in same basket are signaling, scale them together.
            # (Simplified for now: allow 2x more positions if in Hydra mode)
            decision.notes = (decision.notes or "") + " [WEALTH] Hydra Coordinated Entry"

        # 7. [NEW] VOLATILITY COIL (The Spring)
        elif mode == "coil":
            # Detect if ATR is 50% below its 100-bar moving average
            candles = snapshot.candles
            if len(candles) >= 100:
                recent_atr = calculate_atr(candles[-14:], 14)
                hist_atr = calculate_atr(candles, 100)
                if recent_atr and hist_atr and recent_atr < (hist_atr * 0.6):
                    decision.risk_per_trade_pct = min(base_risk * 3.0, risk_cap)
                    decision.notes = (decision.notes or "") + f" [WEALTH] Coil Breakout ({decision.risk_per_trade_pct*100:.1f}% Risk)"

        # 8. [NEW] TIME-OF-DAY ALPHA (Power Hour)
        elif mode == "alpha":
            est_now = datetime.now(ZoneInfo("America/New_York"))
            # New York Morning (9:30 - 11:30)
            if 9 <= est_now.hour <= 11:
                decision.risk_per_trade_pct = min(base_risk * 2.0, risk_cap)
                decision.notes = (decision.notes or "") + f" [WEALTH] Power Hour Multiplier ({decision.risk_per_trade_pct*100:.1f}% Risk)"

        # 9. [NEW] GAMMA SQUEEZE (Velocity)
        elif mode == "gamma":
            # Detect sharp velocity in last 3 bars
            if len(snapshot.candles) >= 5:
                start = snapshot.candles[-4].close
                end = snapshot.candles[-1].close
                velocity = abs(end - start) / start
                if velocity > 0.01: # 1% move in 4 bars
                    decision.risk_per_trade_pct = min(base_risk * 2.5, risk_cap)
                    decision.notes = (decision.notes or "") + f" [WEALTH] Gamma Velocity Squeeze ({decision.risk_per_trade_pct*100:.1f}% Risk)"

        # 10. [NEW] EQUITY SMOOTHING (Anti-Tilt)
        elif mode == "smooth":
            # Boost if at ATH, slash if in drawdown
            if cls.DAILY_PNL < -0.02 * cls.HWM_CAPITAL: # 2% Daily Drawdown
                decision.risk_per_trade_pct = base_risk * 0.5
                decision.notes = (decision.notes or "") + " [WEALTH] Anti-Tilt Dampener"
            elif cls.HWM_CAPITAL > 0 and cls.DAILY_PNL > 0:
                decision.risk_per_trade_pct = base_risk * 1.2
                decision.notes = (decision.notes or "") + " [WEALTH] Momentum Boost"

        # 11. [NEW] AI SENTIMENT FUSION (Hype Train)
        elif mode == "sentiment":
            if ai_client:
                sentiment_prompt = f"Analyze the following recent price action for {snapshot.symbol}: {snapshot.candles[-5:]}. Is the short-term sentiment BULLISH, BEARISH, or NEUTRAL? Answer with one word only."
                sentiment = ai_client.generate_text([{"role": "user", "content": sentiment_prompt}]).upper()
                
                is_bull_signal = "long" in decision.action
                if (sentiment == "BULLISH" and is_bull_signal) or (sentiment == "BEARISH" and not is_bull_signal):
                    decision.risk_per_trade_pct = min(base_risk * 2.0, risk_cap)
                    decision.notes = (decision.notes or "") + f" [WEALTH] AI Sentiment Confirmed ({sentiment}) - {decision.risk_per_trade_pct*100:.1f}% Risk"
                elif sentiment != "NEUTRAL":
                    # VETO if sentiment is opposite to trade
                    from tradebot_sci.strategy.decisions import stand_aside_decision
                    return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"AI Sentiment Veto ({sentiment})")

        # 12. [NEW] HARMONIC GHOST (Order Flow)
        elif mode == "ghost":
            # Simplified Harmonic check: if price is near a whole number (conveying psychological liquidity)
            last_price = snapshot.candles[-1].close
            if abs(last_price - round(last_price)) < (last_price * 0.001):
                decision.risk_per_trade_pct = base_risk * 1.5
                decision.notes = (decision.notes or "") + " [WEALTH] Harmonic Liquidity Alignment"

        # 13. [NEW] THE PHOENIX (Loss Reversion)
        elif mode == "phoenix":
            # If we just came off a loss streak
            # (Requires tracking if count reached 3 recently)
            decision.notes = (decision.notes or "") + " [WEALTH] Phoenix Protocol Active"
 
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
