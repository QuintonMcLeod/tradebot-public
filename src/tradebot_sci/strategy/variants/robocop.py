from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision, stand_aside_decision, hold_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import (
    detect_continuation, 
    detect_liquidity_sweep, 
    detect_indication, 
    detect_correction,
    detect_structure_invalidation,
    calculate_atr
)
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class RoboCopStrategy(BaseStrategy):
    """
    RoboCop (Iteration 17): THE ABSOLUTE SNIPER.
    
    User-driven "Surefire" approach.
    - Zero Strength Filter (Quiet markets allowed)
    - Strict Triple Confluence: HTF Alignment + Sweep + BOS
    - Anchored Stop: Absolute Sweep Extremes.
    - Risk: 2% Probe / 15% Load.
    """
    
    def __init__(self):
        super().__init__("RoboCop")

    def _compute_score(self, snapshot, gates=None):
        """Internal scoring used by both score_signal() and check_entry_signal()."""
        lookback = 2
        score = 0.0
        breakdown = []

        htf_dir = snapshot.trend_htf.direction
        ltf_dir = snapshot.trend_ltf.direction

        if htf_dir != "neutral" and htf_dir == ltf_dir:
            score += 30.0
            breakdown.append("Align(+30)")

        target_dir = ltf_dir
        if target_dir == "neutral":
            return score, breakdown, target_dir

        sweep = detect_liquidity_sweep(snapshot.candles, target_dir, swing_lookback=lookback)
        if sweep:
            sweep_age = len(snapshot.candles) - 1 - sweep.index
            if sweep_age <= 5:
                score += 25.0
                breakdown.append("Sweep(+25)")

        ind = detect_indication(snapshot.candles, swing_lookback=lookback)
        if ind and ind.direction == target_dir:
            score += 25.0
            breakdown.append("BOS(+25)")

        htf_strength = snapshot.trend_htf.strength
        if htf_strength >= 0.5:
            score += 15.0
            breakdown.append(f"StrongHTF({htf_strength:.1f}=+15)")

        if sweep and ind:
            score += 5.0
            breakdown.append("Phase(+5)")

        return score, breakdown, target_dir

    def score_signal(self, snapshot, gates=None):
        """RoboCop-specific scoring: Align(30) + Sweep(25) + BOS(25) + StrongHTF(15) + Phase(5)."""
        score, breakdown, _ = self._compute_score(snapshot, gates)
        grade = self.grade_from_score_100(score)
        summary = f"RoboCop {score:.0f}/100: {', '.join(breakdown)}" if breakdown else f"RoboCop {score:.0f}/100"
        return score, grade, summary

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if open_position and float(open_position.get("size", 0)) > 0:
            return None

        score, score_breakdown, target_dir = self._compute_score(snapshot, gates)

        # [TREND GUIDANCE] Follow HTF direction from gates; only fall back to LTF if neutral
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        if htf_dir in ("long", "short"):
            target_dir = htf_dir

        if target_dir == "neutral":
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Neutral LTF")

        # FILTER: Minimum Score 60
        if score < 60.0:
            return stand_aside_decision(
                snapshot.symbol, 
                snapshot.timeframe, 
                f"Sniper: Low Score {score:.0f}/60 ({', '.join(score_breakdown)})"
            )

        # --- EXECUTION LOGIC (If Score >= 60) ---
        lookback = 2
        sweep = detect_liquidity_sweep(snapshot.candles, target_dir, swing_lookback=lookback)
        
        # Re-verify STRICT entry conditions for the specific order parameters
        # 1. Must have Fresh Sweep (<= 2 bars) 
        if not sweep:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Hunting Sweep (Score Pass, No Sweep)")
             
        sweep_age = len(snapshot.candles) - 1 - sweep.index
        if sweep_age > 2:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"Sniper: Stale Sweep ({sweep_age} bars)")

        # 2. Must have BOS (Indication)
        ind = detect_indication(snapshot.candles, swing_lookback=lookback)
        if not ind or ind.direction != target_dir:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Seeking BOS Alignment")


        last_close = snapshot.candles[-1].close
        
        # [ARMOR] 2x ATR Stops & Targets
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        
        # [ARMOR] Dynamic Stops based on UserConfig
        dist = atr * UserConfig.STOP_ATR_MULTIPLIER
        
        if target_dir == "long":
            stop_loss = last_close - dist
            take_profit = last_close + (dist * 2.0)  # 2:1 R:R
        else:
            stop_loss = last_close + dist
            take_profit = last_close - (dist * 2.0)  # 2:1 R:R
        
        return AITradeDecision(
            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            bias=target_dir, phase="continuation", action="enter_long" if target_dir == "long" else "enter_short",
            entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=f"RoboCop Scorer: {score:.0f}/100 ({', '.join(score_breakdown)})",
            invalidation_conditions=f"ATR Armor ({stop_loss:.2f}) breached",
            management_instructions=f"Net-Zero at 1xATR, Rising Floors at 5% (Using {UserConfig.STOP_ATR_MULTIPLIER}x ATR Stop)",
            notes=f"Score {score:.0f}: {', '.join(score_breakdown)}",
            urgency="high"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        pos_dir = open_position.get("direction")
        entry_price = float(open_position.get("entry_price", 0))
        current_stop = float(open_position.get("stop_loss", 0))
        current_pnl = float(open_position.get("unrealized_pnl", 0))
        capital = current_capital or 1000.0
        
        last_close = snapshot.candles[-1].close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        
        # 1. Smart Exit: HTF Reversal (User Request: "Usually it's the htf that invalidates")
        # If we are long, and HTF flips to short (or neutral?), bail.
        htf_dir = snapshot.trend_htf.direction
        if (pos_dir == "long" and htf_dir == "short") or (pos_dir == "short" and htf_dir == "long"):
             return close_position_decision(snapshot.symbol, snapshot.timeframe, f"Sniper Exit: HTF Reversal ({htf_dir})")

        # 2. Smart Exit: Opposing Indication (BOS against us)
        # If we see a structure break against our position, get out before the stop.
        opposing_ind = detect_indication(snapshot.candles, swing_lookback=2)
        if opposing_ind and opposing_ind.direction != pos_dir:
             return close_position_decision(snapshot.symbol, snapshot.timeframe, f"Sniper Exit: Opposing BOS ({opposing_ind.direction})")

        # 3. Structure Invalidation (Tight)
        inval = detect_structure_invalidation(snapshot.candles, pos_dir, atr_mult=0.5)
        if inval:
             return close_position_decision(snapshot.symbol, snapshot.timeframe, "Sniper Defeat: Structure Broken")

        # [SAFETY] Managed by StrategyEngine via SafetyGuard
        
        # [NEW] Take Profit Check
        tp_target = float(open_position.get("take_profit") or 0.0)
        if tp_target > 0:
            if (pos_dir == "long" and last_close >= tp_target) or \
               (pos_dir == "short" and last_close <= tp_target):
                return close_position_decision(snapshot.symbol, snapshot.timeframe, f"Sniper TP: Target Hit @ {tp_target:.4f}")

        return None
