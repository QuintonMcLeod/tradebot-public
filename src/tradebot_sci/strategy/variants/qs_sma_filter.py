from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma

logger = logging.getLogger(__name__)

class QS_SMAFilterStrategy(BaseStrategy):
    """
    1. The 200-Day Moving Average Regime Filter
    Core Idea: Buy when price is above its 200-period moving average on the Higher Timeframe, 
    and exit when it falls below it. Provides a massive filter against drawdowns.
    """
    
    def __init__(self, sma_period: int = 200):
        super().__init__("QS 200-SMA Filter")
        self.sma_period = sma_period

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        # We rely on the Higher Timeframe (HTF) to represent macro days
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.sma_period:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        sma_200 = calculate_sma(htf_closes, self.sma_period)
        
        last_close = snapshot.candles[-1].close
        
        # Rule: Buy when price is > 200 SMA
        if last_close > sma_200:
            stop_loss = last_close * 0.99  # 1% generic stop
            take_profit = last_close + (last_close - stop_loss) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"Price ({last_close:.4f}) > {self.sma_period} SMA ({sma_200:.4f})",
                invalidation_conditions="Close below SMA",
                urgency="medium",
                risk_per_trade_pct=self.get_risk_pct()
            )
            
        # Optional symmetry: Short when price < 200 SMA
        elif last_close < sma_200:
            stop_loss = last_close * 1.01
            take_profit = last_close - (stop_loss - last_close) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"Price ({last_close:.4f}) < {self.sma_period} SMA ({sma_200:.4f})",
                invalidation_conditions="Close above SMA",
                urgency="medium",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Exit when price crosses the opposite side of the SMA."""
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.sma_period:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        sma_200 = calculate_sma(htf_closes, self.sma_period)
        last_close = snapshot.candles[-1].close
        
        pos_dir = open_position.get("direction", "long")
        
        if pos_dir == "long" and last_close < sma_200:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Price fell below 200 SMA")
            
        if pos_dir == "short" and last_close > sma_200:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Price rose above 200 SMA")
            
        return None
