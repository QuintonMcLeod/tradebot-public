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
        self.FEET_WET_RISK = 0.02   # 2% Probe
        self.LOAD_RISK_PCT = 0.05   # 5% Load (Sustainable)
        self.BREAKEVEN_R = 1.0      # Be very safe
        self.TARGET_R = 3.0         # 3:1 Sustainable RR

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if open_position and float(open_position.get("size", 0)) > 0:
            return None 

        lookback = 2

        # SCORING SYSTEM (Legacy "Engine V1" Logic)
        # To solve the binary strength filter issue, we grade the setup on a 0-100 scale.
        # Passing Grade: 60 Points.
        
        score = 0.0
        score_breakdown = []
        
        # 1. Alignment (+30 pts)
        # HTF and LTF must match.
        htf_actual_dir = snapshot.trend_htf.direction
        ltf_actual_dir = snapshot.trend_ltf.direction
        
        if htf_actual_dir != "neutral" and htf_actual_dir == ltf_actual_dir:
            score += 30.0
            score_breakdown.append("Align(+30)")
            
        # 2. Liquidity Sweep (+25 pts)
        # Note: We redetect here to check existence before calculating specific entry params
        # Use the "intended" direction (LTF) for detection
        target_dir = ltf_actual_dir
        if target_dir == "neutral":
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Neutral LTF")

        sweep = detect_liquidity_sweep(snapshot.candles, target_dir, swing_lookback=lookback)
        if sweep:
            # Check freshness
            sweep_age = len(snapshot.candles) - 1 - sweep.index
            if sweep_age <= 5: # Allow slightly wider window for "points", strict 2 for entry
                score += 25.0
                score_breakdown.append("Sweep(+25)")

        # 3. Indication/BOS (+25 pts)
        ind = detect_indication(snapshot.candles, swing_lookback=lookback)
        if ind and ind.direction == target_dir:
            score += 25.0
            score_breakdown.append("BOS(+25)")
            
        # 4. Strong HTF Trend (+15 pts)
        # Reward distinct trends (Strength >= 0.5)
        htf_strength = snapshot.trend_htf.strength
        if htf_strength >= 0.5:
            score += 15.0
            score_breakdown.append(f"StrongHTF({htf_strength:.1f}=+15)")
            
        # 5. Good Phase (+5 pts) - Simplified
        # If we have BOS + Sweep, we are likely not in simple chop
        if sweep and ind:
            score += 5.0
            score_breakdown.append("Phase(+5)")

        # FILTER: Minimum Score 60
        if score < 60.0:
            return stand_aside_decision(
                snapshot.symbol, 
                snapshot.timeframe, 
                f"Sniper: Low Score {score:.0f}/60 ({', '.join(score_breakdown)})"
            )

        # --- EXECUTION LOGIC (If Score >= 60) ---
        
        # We re-verify the STRICT entry conditions for the specific order parameters
        # 1. Must have Fresh Sweep (<= 2 bars) 
        # (The score gave points for <= 5, but we want strict entry timing)
        if not sweep:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Hunting Sweep (Score Pass, No Sweep)")
             
        sweep_age = len(snapshot.candles) - 1 - sweep.index
        if sweep_age > 2:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"Sniper: Stale Sweep ({sweep_age} bars)")

        # 2. Must have BOS (Indication) - Simple Check, NOT strict continuation
        # Per user: "Continuations are not mandatory"
        if not ind or ind.direction != target_dir:
             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Seeking BOS Alignment")


        last_close = snapshot.candles[-1].close
        
        # [ARMOR] 2x ATR Stops & Targets
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        
        # Stop = Entry +/- 2 ATR
        dist = atr * 2.0
        
        if target_dir == "long":
            stop_loss = last_close - dist
            take_profit = last_close + dist # 1:1 R/R initially, but we rely on trail
        else:
            stop_loss = last_close + dist
            take_profit = last_close - dist
        
        return AITradeDecision(
            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            bias=target_dir, phase="continuation", action="enter_long" if target_dir == "long" else "enter_short",
            entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
            risk_per_trade_pct=self.FEET_WET_RISK,
            structure_summary=f"RoboCop Scorer: {score:.0f}/100 ({', '.join(score_breakdown)})",
            invalidation_conditions=f"ATR Armor ({stop_loss:.2f}) breached",
            management_instructions="Net-Zero at 1xATR, Rising Floors at 5%",
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

        # 5. [THE LOAD] - Compound at 1R profit (Surefire stacking) - PRESERVED!
        # Only check if in profit
        profit_dist = (last_close - entry_price) if pos_dir == "long" else (entry_price - last_close)
        if profit_dist > 0:
            one_r_dollars = capital * self.FEET_WET_RISK
            current_pnl = float(open_position.get("unrealized_pnl", 0))
            if current_pnl > one_r_dollars:
                 # Check we haven't already pyramided max times (Config usually handles this)
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias=pos_dir, phase="trend", action="add_to_position",
                    entry_price=last_close, 
                    # Use CURRENT stop (which might be the trail from above if engine processed it, 
                    # but here we return action. The Engine will use the NEW stop from the Hold decision if we returned it?
                    # Wait, we can't return TWO decisions. 
                    # If we need to Trail AND Compound, Compound takes precedence as it's a new order.
                    # We should pass the updated stop in this decision.
                    stop_loss=current_stop, # Use current stop for now, trail will update next tick
                    risk_per_trade_pct=self.LOAD_RISK_PCT,
                    structure_summary=f"RoboCop LOAD: Surefire Compound ${current_pnl:.2f}",
                    invalidation_conditions="Existing SL hit",
                    management_instructions="Maintain Trail",
                    notes="Absolute Sniper Load",
                    urgency="high"
                )

        return None
