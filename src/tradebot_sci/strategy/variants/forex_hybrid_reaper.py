from __future__ import annotations
import logging
from typing import Optional


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class ForexHybridReaperStrategy(BaseStrategy):
    SESSION_PROFILE = ["forex_hybrid_scalper:hybrid_overlap", "forex_hybrid_scalper:london_open"]
    """
    Forex Hybrid Scalper — Router inspired high-frequency 5m Forex strategy.
    Combines HyperScalper's trend filter (EMA 200) with Rubberband Reaper's 
    kinetic entry signals (RSI + Bollinger Bands), wrapped in strict 
    session and volatility guards to avoid Asian chop.
    
    Optimized for major pairs (EUR/USD, GBP/USD).
    """
    def __init__(self, target_r=2.5, **kwargs):
        super().__init__("ForexHybridScalper")
        self.target_r = target_r
        
        # Rubberband Reaper default kinetics parameters
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 1.5))
        self.rsi_period = int(kwargs.get('rsi_period', 7))
        self.rsi_overbought = float(kwargs.get('rsi_overbought', 60))
        self.rsi_oversold = float(kwargs.get('rsi_oversold', 40))
        
        # Hyper Scalper default trend parameters
        self.trend_ema_period = int(kwargs.get('trend_ema', 200))
        
        logger.debug(f"Loaded ForexHybridReaper with TargetR={self.target_r}, TrendEMA={self.trend_ema_period}")

    def score_signal(self, snapshot: MarketSnapshot, gates: dict = None) -> tuple[float, str, str]:
        """Hybrid Reaper specific scoring: HTF/LTF Alignment (40) + BB Position (30) + RSI Extremity (30)."""
        gates = gates or {}
        closes = [c.close for c in snapshot.candles]
        
        # If we don't have enough data to calculate EMA, default F
        if len(closes) < getattr(self, 'trend_ema_period', 200):
            return 0.0, "-", "HybridScalper: Insufficient data"

        last_close = closes[-1]
        
        exec_bollinger = gates.get("exec_bollinger", {})
        lower_bb = exec_bollinger.get("lower", float('-inf'))
        upper_bb = exec_bollinger.get("upper", float('inf'))
        
        rsi = gates.get("exec_rsi", 50.0)
        
        # Default Profile Fallbacks if available
        overbought_thresh = float(getattr(self._profile, 'rsi_overbought', self.rsi_overbought)) if getattr(self, '_profile', None) else self.rsi_overbought
        oversold_thresh = float(getattr(self._profile, 'rsi_oversold', self.rsi_oversold)) if getattr(self, '_profile', None) else self.rsi_oversold
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        
        score = 0.0
        breakdown = []
        
        # Determine internal strategy bias
        is_long_bias = last_close > trend_ema
        strat_bias = "long" if is_long_bias else "short"
        
        # 1. Global HTF / LTF Alignment (40 pts)
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        
        if htf_dir == strat_bias:
            score += 20.0
            breakdown.append(f"HTF-Align(+20)")
        if ltf_dir == strat_bias:
            score += 20.0
            breakdown.append(f"LTF-Align(+20)")
            
        # 2. Bollinger Band Position (30 pts) - STRICT: only full pierce gets points
        if is_long_bias:
            if last_close <= lower_bb:
                score += 30.0
                breakdown.append("BB-Pierced(+30)")
        else:
            if last_close >= upper_bb:
                score += 30.0
                breakdown.append("BB-Pierced(+30)")
                    
        # 3. RSI Extremity (30 pts) - STRICT: only extreme gets points
        if is_long_bias:
            if rsi <= oversold_thresh:
                score += 30.0
                breakdown.append(f"RSI-OS({rsi:.1f}=+30)")
        else:
            if rsi >= overbought_thresh:
                score += 30.0
                breakdown.append(f"RSI-OB({rsi:.1f}=+30)")

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"HybridScalper {score:.0f}/100: {', '.join(breakdown)}"
        return score, grade, summary


    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        if len(candles) < self.trend_ema_period:
            return None
        
        # ---------------------------------------------------------
        # 1. Volatility Guard (Avoid chop/flat markets)
        # ---------------------------------------------------------
        # Requirement: calculate_atr value must NOT be 30% below 
        # its 20-period average.
        if len(candles) < 40:
            return None
            
        # Re-using the exact calculate_atr function logic natively
        # Calculating the SMA of the ATR over the last 20 periods
        atr_history = []
        for i in range(-20, 0):
            # calculate ATR up to candle i
            slice_candles = candles[:len(candles)+i+1] if i < -1 else candles
            a = calculate_atr(slice_candles, period=14)
            if a:
                atr_history.append(a)
        
        if not atr_history:
            return None
            
        avg_atr_20 = sum(atr_history) / len(atr_history)
        current_atr = calculate_atr(candles, period=14)
        
        if not current_atr or current_atr < (avg_atr_20 * 0.5):
            logger.info(f"[ForexHybridReaper] {snapshot.symbol} BLOCKED: Volatility Guard. ATR ({current_atr:.5f}) < 50% of 20-period average ({avg_atr_20:.5f})")
            return None

        # ---------------------------------------------------------
        # 3. Hybrid Entry Logic (STRICT CONSISTENCY POLICY)
        # ---------------------------------------------------------
        closes = [c.close for c in candles]
        
        # We retain EMA filter since 200 EMA is structural to the specific trend logic
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        last_close = closes[-1]
        
        # Sourced securely from dual-purpose consensus extraction (Decoupled execution timeframe).
        exec_bollinger = gates.get("exec_bollinger", {})
        lower_bb = exec_bollinger.get("lower", float('-inf'))
        mid_bb = exec_bollinger.get("middle", last_close)
        upper_bb = exec_bollinger.get("upper", float('inf'))
        
        rsi = gates.get("exec_rsi", 50.0)
        
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        
        # Override local thresholds with any potential Profile overrides provided in UI
        overbought_thresh = float(getattr(self._profile, 'rsi_overbought', self.rsi_overbought)) if getattr(self, '_profile', None) else self.rsi_overbought
        oversold_thresh = float(getattr(self._profile, 'rsi_oversold', self.rsi_oversold)) if getattr(self, '_profile', None) else self.rsi_oversold
        
        # Guard: No scale-ins for simple strategy unless specified by open_position logic
        if open_position:
            return None
            
        # Generate strategic score to evaluate holistic setup quality
        score, grade, summary = self.score_signal(snapshot, gates)

        logger.info(f"[HybridReaper Debug {snapshot.symbol}] Close={last_close:.5f} | EMA={trend_ema:.5f} | GlobalRSI={rsi:.1f} | GlobalLBB={lower_bb:.5f} | GlobalUBB={upper_bb:.5f} | HTF={htf_dir} | Score={score:.1f}")

        # ---------------------------------------------------------
        # 4. 3-Bar Momentum Gate (Anti-Exhaustion)
        # ---------------------------------------------------------
        # Block entry if all 3 recent bars moved against the proposed direction.
        # BB+RSI can fire at the TAIL of an exhausted move (price pierced BB then
        # reversed). If the last 3 closes are already running against us, the
        # bounce has not materialized — skip and wait for actual reversal.
        #
        # Gate fires when:  ALL of bar[-3]→[-2], [-2]→[-1] move against direction.
        # i.e. for LONG: every close-to-close delta is negative (pure sell momentum)
        #      for SHORT: every close-to-close delta is positive (pure buy momentum)
        is_long_setup = last_close > trend_ema
        if len(closes) >= 4:
            deltas = [closes[-i] - closes[-i-1] for i in range(1, 4)]  # last 3 bar moves
            all_against_long  = all(d < 0 for d in deltas)  # 3 consecutive down bars
            all_against_short = all(d > 0 for d in deltas)  # 3 consecutive up bars
            if is_long_setup and all_against_long:
                logger.info(
                    f"[HybridReaper] {snapshot.symbol} BLOCKED: 3-bar momentum gate — "
                    f"3 consecutive down bars into long setup (exhaustion, not reversal)"
                )
                return None
            if not is_long_setup and all_against_short:
                logger.info(
                    f"[HybridReaper] {snapshot.symbol} BLOCKED: 3-bar momentum gate — "
                    f"3 consecutive up bars into short setup (exhaustion, not reversal)"
                )
                return None
            
        # LONG: Price > 200 EMA + Strict BB/RSI Touch + Minimum Score (no OR condition)
        if last_close > trend_ema and rsi <= oversold_thresh and last_close <= lower_bb and score >= 60.0:
            stop_dist = max(current_atr * 1.5, last_close * 0.0008)  # Safe floor distance
            stop_loss = last_close - stop_dist
            tr = float(getattr(self._profile, "target_r", self.target_r)) if getattr(self, "_profile", None) else self.target_r
            target = last_close + (stop_dist * tr)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"HybridReaper Long (RSI={rsi:.1f}, BBTouch, Score={score:.0f})",
                invalidation_conditions="Close below stop loss.",
                management_instructions=f"Target {self.target_r}R.",
                urgency="high",
                strategy_name=self.name
            )

        # SHORT: Price < 200 EMA + Strict BB/RSI Touch + Minimum Score (no OR condition)
        if last_close < trend_ema and rsi >= overbought_thresh and last_close >= upper_bb and score >= 60.0:
            stop_dist = max(current_atr * 1.5, last_close * 0.0008)
            stop_loss = last_close + stop_dist
            tr = float(getattr(self._profile, "target_r", self.target_r)) if getattr(self, "_profile", None) else self.target_r
            target = last_close - (stop_dist * tr)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"HybridReaper Short (RSI={rsi:.1f}, BBTouch, Score={score:.0f})",
                invalidation_conditions="Close above stop loss.",
                management_instructions=f"Target {self.target_r}R.",
                urgency="high",
                strategy_name=self.name
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """All exits managed by structural lifecycle/safety guards."""
        return None
