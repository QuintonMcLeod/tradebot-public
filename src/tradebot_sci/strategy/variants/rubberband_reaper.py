
from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr, detect_structure_invalidation

logger = logging.getLogger(__name__)

class RubberbandReaperStrategy(BaseStrategy):
    """
    Rubberband Reaper: CONFIG 20 (The Staircase Ratchet).
    - Strict Thresholds (Config 13 Quality).
    - Staircase Floor (User Milestones + 2x Cushion).
    - 20% Profit Scaling (The Hammer).
    """
    
    def __init__(self, bb_period=20, bb_std=2.5, rsi_period=7, rsi_overbought=75, rsi_oversold=25, **kwargs):
        logger.debug(f"Loaded RubberbandReaper from {__file__}")
        super().__init__("Rubberband Reaper")
        
        self.bb_period = int(kwargs.get('bb_period', bb_period))
        self.bb_std = float(kwargs.get('bb_std', bb_std))
        self.rsi_period = int(kwargs.get('rsi_period', rsi_period))
        self.rsi_overbought = float(kwargs.get('rsi_overbought', rsi_overbought))
        self.rsi_oversold = float(kwargs.get('rsi_oversold', rsi_oversold))
        
        logger.debug(f"Reaper Config 20 (Staircase Ratchet) Loaded. BB={self.bb_std}, RSI={self.rsi_oversold}/{self.rsi_overbought}")

    def score_signal(self, snapshot, gates=None):
        """Reaper-specific scoring: BB Pos(25) + RSI(25) + HTF Align(20) + BB Width(15) + LTF/HTF(15)."""
        gates = gates or {}
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period:
            return 0.0, "F-", "Reaper: Insufficient data"

        last_close = closes[-1]
        
        # Sourced securely from dual-purpose consensus extraction (Decoupled execution timeframe).
        exec_bollinger = gates.get("exec_bollinger", {})
        lower = exec_bollinger.get("lower", float('-inf'))
        mid = exec_bollinger.get("middle", last_close)
        upper = exec_bollinger.get("upper", float('inf'))
        
        rsi = gates.get("exec_rsi", 50.0)

        score = 0.0
        breakdown = []

        # 1. BB Position (25 pts) — how close to a band extreme
        bb_range = upper - lower if upper > lower else 1e-9
        if last_close <= lower:
            score += 25.0
            breakdown.append("BB-Low(+25)")
        elif last_close >= upper:
            score += 25.0
            breakdown.append("BB-High(+25)")
        else:
            dist_to_edge = min(last_close - lower, upper - last_close) / bb_range
            pts = max(0, 25 * (1 - dist_to_edge * 3))
            if pts > 0:
                score += pts
                breakdown.append(f"BB-Near(+{pts:.0f})")

        # 2. RSI Extremity (25 pts)
        if rsi <= self.rsi_oversold:
            score += 25.0
            breakdown.append(f"RSI-OS({rsi:.0f}=+25)")
        elif rsi >= self.rsi_overbought:
            score += 25.0
            breakdown.append(f"RSI-OB({rsi:.0f}=+25)")
        else:
            # Partial credit — closer to extremes = more points
            dist_to_extreme = min(abs(rsi - self.rsi_oversold), abs(rsi - self.rsi_overbought))
            mid_dist = (self.rsi_overbought - self.rsi_oversold) / 2
            pts = max(0, 25 * (1 - dist_to_extreme / mid_dist))
            if pts > 5:
                score += pts
                breakdown.append(f"RSI-Near({rsi:.0f}=+{pts:.0f})")

        # 3. HTF Alignment (20 pts) [REMOVED]
        # Trades purely off extremes regardless of macro trend.
        score += 20.0

        # 4. BB Width / Volatility (15 pts) — wider = better for mean-reversion
        bb_width = (upper - lower) / mid if mid > 0 else 0
        if bb_width >= 0.03:
            score += 15.0
            breakdown.append(f"Width({bb_width:.3f}=+15)")
        elif bb_width >= 0.015:
            pts = 15 * ((bb_width - 0.01) / 0.02)
            score += pts
            breakdown.append(f"Width({bb_width:.3f}=+{pts:.0f})")

        # 5. LTF/HTF Agreement (15 pts) [REMOVED]
        # Pure rubberband
        score += 15.0

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"Reaper {score:.0f}/100: {', '.join(breakdown)}" if breakdown else f"Reaper {score:.0f}/100"
        return score, grade, summary

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        # --- RISK GOVERNANCE ---
        # Use profile-configured risk (no more dynamic staircase/martingale)
        final_risk_pct = self.get_risk_pct()

        closes = [c.close for c in snapshot.candles]
        last_close = closes[-1]
        
        # Sourced securely from dual-purpose consensus extraction (Decoupled execution timeframe).
        exec_bollinger = gates.get("exec_bollinger", {})
        lower = exec_bollinger.get("lower", float('-inf'))
        mid = exec_bollinger.get("middle", last_close)
        upper = exec_bollinger.get("upper", float('inf'))
        
        rsi = gates.get("exec_rsi", 50.0)
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # [HARDENED] BB Squeeze Guard: If bands are very narrow, skip.
        # Narrow bands = low volatility = breakout imminent, NOT mean-reversion.
        bb_width = (upper - lower) / mid if mid > 0 else 0
        if bb_width < 0.01:  # Less than 1% band width = squeezed
            logger.debug(f"[REAPER] BB Squeeze detected for {snapshot.symbol} (width={bb_width:.4f}). Skipping.")
            return None

        # [HARDENED] HTF Trend Alignment Gate [REMOVED]
        # Pure rubberband: We NO LONGER check the HTF trend so we can properly trade
        # exhaustion reversals against a strong trend.

        # 1. THE HAMMER (Scale-In / Pyramid)
        if open_position:
            if open_position.get("pyramid_count", 1) > 1:
                return None
            pos_dir = open_position.get("direction")
            
            # [HARDENED] Hammer requires RSI re-confirmation.
            # Long hammer needs RSI still below 30 (not just "price above lower band").
            # Short hammer needs RSI still above 70.
            is_long_hammer = pos_dir == "long" and last_close > lower and rsi < 30
            is_short_hammer = pos_dir == "short" and last_close < upper and rsi > 70

            if is_long_hammer or is_short_hammer:
                 target = upper if pos_dir == "long" else lower
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias=pos_dir, phase="continuation", action="scale_in",
                    entry_price=last_close, stop_loss=open_position.get("stop_loss") or open_position.get("stop_price") or (last_close - atr * 2.0 if pos_dir == "long" else last_close + atr * 2.0), take_profit=target,
                    risk_per_trade_pct=final_risk_pct,
                    structure_summary=f"STAIRCASE HAMMER ({final_risk_pct*100:.2f}%)",
                    urgency="high",
                    notes=f"Staircase Floor logic active. Risk={final_risk_pct*100:.2f}%",
                    invalidation_conditions="Price breaks structure.",
                    management_instructions="Aggressive TP."
                )
            return None

        # 2. THE SCOUT (Initial Entry)
        # Long: Trade the rubberband bounce purely on exhaustion
        if last_close < lower and rsi < self.rsi_oversold:
            # [ARMOR] 2x ATR Dynamic Stops
            stop_loss = last_close - (atr * 2.0)
            take_profit = max(mid, last_close + (atr * 2.0) * 2.0)  # Middle band or 2:1 R:R floor
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Armor Entry (2x ATR). Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close below stop loss.",
                management_instructions="Net-Zero at 1xATR."
            )

        # Short: Trade the rubberband bounce purely on exhaustion
        if last_close > upper and rsi > self.rsi_overbought:
            # [ARMOR] 2x ATR Dynamic Stops
            stop_loss = last_close + (atr * 2.0)
            take_profit = min(mid, last_close - (atr * 2.0) * 2.0)  # Middle band or 2:1 R:R floor
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=final_risk_pct,
                structure_summary=f"Staircase Scout (RSI={rsi:.1f})",
                urgency="high",
                notes=f"Armor Entry (2x ATR). Risk={final_risk_pct*100:.2f}%",
                invalidation_conditions="Close above stop loss.",
                management_instructions="Net-Zero at 1xATR."
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """All exits managed by SafetyGuard. No strategy-level exit authority."""
        return None
