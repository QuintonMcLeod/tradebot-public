from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma

logger = logging.getLogger(__name__)

class QS_GoldenCrossStrategy(BaseStrategy):
    """
    2. The Golden Cross
    Core Idea: Capitalizes on the market's long-term tendency to trend upwards. A 'Golden Cross' 
    signals a bullish trend (50 SMA > 200 SMA).
    """
    
    def __init__(self, fast_sma: int = 50, slow_sma: int = 200):
        super().__init__("QS Golden Cross")
        self.fast_sma = fast_sma
        self.slow_sma = slow_sma

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.slow_sma:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        sma_fast_current = calculate_sma(htf_closes, self.fast_sma)
        sma_slow_current = calculate_sma(htf_closes, self.slow_sma)
        
        # Check previous candle to exact crossover timing
        # We need at least one past candle for the "cross" check
        if len(htf_closes) > self.slow_sma:
            sma_fast_prev = calculate_sma(htf_closes[:-1], self.fast_sma)
            sma_slow_prev = calculate_sma(htf_closes[:-1], self.slow_sma)
            
            last_close = snapshot.candles[-1].close
            
            # GOLDEN CROSS: Fast crosses OVER Slow
            if sma_fast_prev <= sma_slow_prev and sma_fast_current > sma_slow_current:
                stop_loss = last_close * 0.98  # 2% generic stop
                take_profit = last_close + (last_close - stop_loss) * 2.0
                return AITradeDecision(
                    symbol=snapshot.symbol,
                    take_profit=take_profit, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss,
                    structure_summary=f"Golden Cross (50 SMA {sma_fast_current:.4f} > 200 SMA {sma_slow_current:.4f})",
                    invalidation_conditions="Death Cross (50 < 200)",
                    urgency="medium",
                    risk_per_trade_pct=self.get_risk_pct()
                )
                
            # DEATH CROSS: Fast crosses UNDER Slow (Optional symmetry)
            elif sma_fast_prev >= sma_slow_prev and sma_fast_current < sma_slow_current:
                stop_loss = last_close * 1.02
                take_profit = last_close - (stop_loss - last_close) * 2.0
                return AITradeDecision(
                    symbol=snapshot.symbol,
                    take_profit=take_profit, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss,
                    structure_summary=f"Death Cross (50 SMA {sma_fast_current:.4f} < 200 SMA {sma_slow_current:.4f})",
                    invalidation_conditions="Golden Cross (50 > 200)",
                    urgency="medium",
                    risk_per_trade_pct=self.get_risk_pct()
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Exit on opposite cross."""
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.slow_sma:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        sma_fast = calculate_sma(htf_closes, self.fast_sma)
        sma_slow = calculate_sma(htf_closes, self.slow_sma)
        
        pos_dir = open_position.get("direction", "long")
        
        if pos_dir == "long" and sma_fast < sma_slow:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Death Cross Exit")
            
        if pos_dir == "short" and sma_fast > sma_slow:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Golden Cross Exit")
            
        return None
