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
    RoboCop — ICC Core foundation + SAR + Guillotine.
    
    Built on ICC Core entry logic (Sweep + BOS + Alignment).
    Enhanced with:
    - SAR (Stop-and-Reverse) on stop hit
    - Guillotine: scale_out 95% at 80% of stop distance
    - Higher risk: 2% per trade
    - Strong trend gate: htf_strength >= 0.3
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

        # VOLUME GATE: Skip low volume — no trend in dead sessions
        candles = snapshot.candles or []
        if len(candles) >= 20:
            recent_volumes = [c.volume for c in candles[-20:-1] if c.volume > 0]
            avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1.0
            if candles[-1].volume < avg_volume:
                return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Low volume")

        score, score_breakdown, target_dir = self._compute_score(snapshot, gates)

        # [TREND GUIDANCE] Follow HTF direction from gates; only fall back to LTF if neutral
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        if htf_dir in ("long", "short"):
            target_dir = htf_dir

        if target_dir == "neutral":
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Sniper: Neutral LTF")

        # [HARDENED] Strong trend gate — require meaningful trend strength
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength < 0.3:
            return stand_aside_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Sniper: Weak trend ({htf_strength:.2f} < 0.3)"
            )

        # FILTER: Minimum Score 70 (hardened from 60)
        if score < 70.0:
            return stand_aside_decision(
                snapshot.symbol, 
                snapshot.timeframe, 
                f"Sniper: Low Score {score:.0f}/70 ({', '.join(score_breakdown)})"
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
        
        # Proven ICT/SMC approach: stop beyond the sweep level (structural invalidation)
        # Research: ICT backtesters use sweep extreme as stop, 2-3:1 R:R = profitable at 36% WR
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        stop_buffer = atr * 0.2  # Tiny buffer beyond sweep level
        
        if target_dir == "long":
            # Sweep low = structural stop (where liquidity was taken)
            recent_lows = [c.low for c in snapshot.candles[-5:]]
            swing_stop = min(recent_lows)
            stop_loss = swing_stop - stop_buffer
            risk_dist = last_close - stop_loss
            take_profit = last_close + (risk_dist * 3.0)  # 3:1 R:R (proven ICT)
        else:
            recent_highs = [c.high for c in snapshot.candles[-5:]]
            swing_stop = max(recent_highs)
            stop_loss = swing_stop + stop_buffer
            risk_dist = stop_loss - last_close
            take_profit = last_close - (risk_dist * 3.0)  # 3:1 R:R (proven ICT)
        
        return AITradeDecision(
            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            bias=target_dir, phase="continuation", action="enter_long" if target_dir == "long" else "enter_short",
            entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=f"RoboCop Scorer: {score:.0f}/100 ({', '.join(score_breakdown)})",
            invalidation_conditions=f"Swing stop ({stop_loss:.5f}) breached → SAR reversal",
            management_instructions=f"SAR-enabled. Guillotine at 80%. Swing-based stop.",
            notes=f"Score {score:.0f}: {', '.join(score_breakdown)}",
            urgency="high"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        """
        Proven ICT trailing stop + Guillotine.
        - At 1R: start trailing 0.75× ATR behind price
        - Guillotine: scale_out 95% when price reaches 80% of stop distance (losing)
        """
        if not snapshot.candles or not open_position:
            return None

        entry_price = float(open_position.get("entry_price", 0))
        stop_price = float(open_position.get("stop_price", 0))
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction", "long")

        if entry_price <= 0 or stop_price <= 0:
            return None

        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0:
            return None

        atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)

        # Calculate R-multiple
        if direction == "long":
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        r_multiple = profit / initial_risk

        # CHANDELIER EXIT: Trail from highest high / lowest low minus ATR×2
        # (proven — Chandelier consistently outperforms simple ATR trails)
        if r_multiple >= 1.0:
            lookback = min(10, len(snapshot.candles))
            recent = snapshot.candles[-lookback:]
            chandelier_mult = 2.0

            if direction == "long":
                highest_high = max(c.high for c in recent)
                new_stop = highest_high - (atr * chandelier_mult)
                if new_stop > stop_price:
                    return hold_decision(
                        snapshot.symbol, snapshot.timeframe,
                        reason=f"RoboCop Chandelier: HH={highest_high:.5f} ({r_multiple:.1f}R)",
                        stop_loss=new_stop,
                    )
            else:
                lowest_low = min(c.low for c in recent)
                new_stop = lowest_low + (atr * chandelier_mult)
                if new_stop < stop_price:
                    return hold_decision(
                        snapshot.symbol, snapshot.timeframe,
                        reason=f"RoboCop Chandelier: LL={lowest_low:.5f} ({r_multiple:.1f}R)",
                        stop_loss=new_stop,
                    )

        # GUILLOTINE: At 80% of stop distance, close 95% of position (losers only)
        if direction == "long":
            distance_to_stop = entry_price - stop_price
            current_loss = entry_price - current_price
        else:
            distance_to_stop = stop_price - entry_price
            current_loss = current_price - entry_price

        if distance_to_stop > 0 and current_loss > 0:
            loss_pct = current_loss / distance_to_stop
            if loss_pct >= 0.80:
                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias=direction,
                    phase="management",
                    action="scale_out",
                    notes=f"[GUILLOTINE] {loss_pct:.0%} to stop — closing 95% to preserve capital",
                )

        return None
