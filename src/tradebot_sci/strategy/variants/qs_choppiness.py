from __future__ import annotations
import logging
import math
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

def compute_choppiness_index(candles: list, n: int = 14) -> float:
    """
    Calculates the Choppiness Index.
    Math: 100 * LOG10( SUM(TrueRange, n) / (MaxHigh(n) - MinLow(n)) ) / LOG10(n)
    Higher values (>61.8) = Ranging/Choppy. Lower values (<38.2) = Trending.
    """
    if len(candles) < n + 1:
        return 50.0

    sum_tr = 0.0
    for i in range(len(candles) - n, len(candles)):
        prev_close = candles[i-1].close
        high = candles[i].high
        low = candles[i].low
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        sum_tr += tr

    window = candles[-n:]
    max_high = max(c.high for c in window)
    min_low = min(c.low for c in window)
    denom = max_high - min_low

    if denom == 0:
        return 50.0

    val = sum_tr / denom
    if val <= 0:
        return 50.0

    chop = 100 * (math.log10(val) / math.log10(n))
    return chop

class QS_ChoppinessStrategy(BaseStrategy):
    """
    6. Choppiness Index Filter
    Core Idea: Distinguishes between trending and range-bound markets. 
    Avoids entering when Choppiness > 61.8 (ranging). Enters trends when Choppiness < 38.2.
    """
    def __init__(self, chop_period: int = 14, trend_threshold: float = 38.2, **kwargs):
        super().__init__("QS Choppiness Filter")
        self.chop_period = chop_period
        self.trend_threshold = trend_threshold

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        chop = compute_choppiness_index(snapshot.candles, self.chop_period)
        
        # We only look for strong directional trends (Chop < 38.2)
        if chop > self.trend_threshold:
            return None
            
        htf_dir = gates.get("htf_dir", "neutral")
        last_close = snapshot.candles[-1].close
        
        if htf_dir == "long":
            stop_loss = last_close * 0.98
            take_profit = last_close + (last_close - stop_loss) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                structure_summary=f"Chop ({chop:.1f}) < {self.trend_threshold} (Trending Long)",
                invalidation_conditions="Chop > 61.8",
                urgency="medium",
                risk_per_trade_pct=self.get_risk_pct()
            )
            
        if htf_dir == "short":
            stop_loss = last_close * 1.02
            take_profit = last_close - (stop_loss - last_close) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                structure_summary=f"Chop ({chop:.1f}) < {self.trend_threshold} (Trending Short)",
                invalidation_conditions="Chop > 61.8",
                urgency="medium",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        chop = compute_choppiness_index(snapshot.candles, self.chop_period)
        if chop > 61.8:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe, "buy" if open_position.get("direction") == "short" else "sell", 1.0, 
                "Choppiness Index exceeded 61.8 (Market flat)"
            )
        return None
