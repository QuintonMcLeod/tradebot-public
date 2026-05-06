from __future__ import annotations

import logging
import statistics
from typing import Any, List, Tuple
from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.market.trend import swing_progress
from tradebot_sci.strategy.constants import (
    GRADE_A_PLUS_THRESHOLD,
    GRADE_A_THRESHOLD,
    GRADE_A_MINUS_THRESHOLD,
    GRADE_B_PLUS_THRESHOLD,
    GRADE_B_THRESHOLD,
    GRADE_B_MINUS_THRESHOLD,
    GRADE_C_PLUS_THRESHOLD,
    GRADE_C_THRESHOLD,
    GRADE_C_MINUS_THRESHOLD,
    GRADE_D_THRESHOLD,
    GRADE_F_PLUS_THRESHOLD,
    GRADE_F_THRESHOLD,
)

logger = logging.getLogger(__name__)

class ActionScorer:
    """Handles ICC setup scoring and grading."""

    @staticmethod
    def calc_volatility(candles: List[Candle]) -> float:
        returns = []
        for prev, curr in zip(candles, candles[1:]):
            if prev.close <= 0:
                continue
            returns.append((curr.close - prev.close) / prev.close)
        if not returns:
            return 0.0
        if len(returns) < 2:
            return abs(returns[0])
        return abs(statistics.stdev(returns))

    @staticmethod
    def calc_volatility_percentile(candles: List[Candle], *, window: int, history: int) -> float:
        if len(candles) < max(window + 1, history):
            return 0.5
        recent = candles[-window:]
        recent_vol = ActionScorer.calc_volatility(recent)
        vols: list[float] = []
        start = max(0, len(candles) - history)
        slice_candles = candles[start:]
        for i in range(window, len(slice_candles)):
            sub = slice_candles[i - window : i]
            vols.append(ActionScorer.calc_volatility(sub))
        if not vols:
            return 0.5
        below = sum(1 for v in vols if v <= recent_vol)
        return min(1.0, max(0.0, below / float(len(vols))))

    @staticmethod
    def grade_from_score(score: float) -> str:
        if score >= GRADE_A_PLUS_THRESHOLD: return "A+"
        if score >= GRADE_A_THRESHOLD: return "A"
        if score >= GRADE_A_MINUS_THRESHOLD: return "A-"
        if score >= GRADE_B_PLUS_THRESHOLD: return "B+"
        if score >= GRADE_B_THRESHOLD: return "B"
        if score >= GRADE_B_MINUS_THRESHOLD: return "B-"
        if score >= GRADE_C_PLUS_THRESHOLD: return "C+"
        if score >= GRADE_C_THRESHOLD: return "C"
        if score >= GRADE_C_MINUS_THRESHOLD: return "C-"
        if score >= GRADE_D_THRESHOLD: return "D"
        if score >= GRADE_F_PLUS_THRESHOLD: return "F+"
        if score >= GRADE_F_THRESHOLD: return "F"
        return "F-"

    @staticmethod
    def confluence_stack_score(snapshot: MarketSnapshot, sweep: Any, continuation: Any) -> Tuple[float, str]:
        htf_dir = snapshot.trend_htf.direction
        ltf_dir = snapshot.trend_ltf.direction
        htf_str = float(snapshot.trend_htf.strength or 0.0)
        ltf_str = float(snapshot.trend_ltf.strength or 0.0)

        align = (htf_dir != "neutral" and ltf_dir != "neutral" and htf_dir == ltf_dir)
        
        score = 0.0
        score += 0.3 * htf_str
        score += 0.2 * ltf_str
        if align: score += 0.2
        if sweep: score += 0.15
        if continuation: score += 0.15
        
        score = min(1.0, max(0.0, score))
        return score, ActionScorer.grade_from_score(score)

    @staticmethod
    def score_icc_grade(htf_dir: str, ltf_dir: str, htf_strength: float, ltf_strength: float, sweep: Any, continuation: Any, indication: Any, correction: Any, session_ok: bool) -> Tuple[float, str]:
        align = (htf_dir != "neutral" and ltf_dir != "neutral" and htf_dir == ltf_dir)
        
        score = 0.0
        score += 0.35 * htf_strength
        score += 0.25 * ltf_strength
        if align: score += 0.25
        if sweep: score += 0.15
        if continuation: score += 0.12
        if indication: score += 0.08
        if session_ok: score += 0.05
        
        if not align:
            # Sliding Penalty: If HTF is strong (>0.6), reduce penalty to 10% (0.9x). 
            # Otherwise, keep standard 30% penalty (0.7x).
            penalty = 0.9 if htf_strength > 0.6 else 0.7
            score *= penalty

        score = min(1.0, max(0.0, score))
        return score, ActionScorer.grade_from_score(score)
