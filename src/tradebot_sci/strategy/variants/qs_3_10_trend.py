from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma

logger = logging.getLogger(__name__)

class QS_3_10_TrendStrategy(BaseStrategy):
    """
    4. 3-Month / 10-Month Moving Average Trend Following
    Core Idea: Standardized macro trend following. Translates to ~60-Day and ~200-Day moving averages.
    Rules: Buy when 3-Month MA (60 Daily) > 10-Month MA (200 Daily).
    """
    
    def __init__(self, fast_ma: int = 60, slow_ma: int = 200):
        super().__init__("QS 3/10 Trend Following")
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.slow_ma:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        
        # Calculate moving averages
        fast_sma = calculate_sma(htf_closes, self.fast_ma)
        slow_sma = calculate_sma(htf_closes, self.slow_ma)
        
        last_close = snapshot.candles[-1].close
        
        if fast_sma > slow_sma:
            stop_loss = last_close * 0.96  # 4% generic stop for macro trades
            take_profit = last_close + (last_close - stop_loss) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="long", phase="macro_trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"3-Month SMA ({fast_sma:.4f}) > 10-Month SMA ({slow_sma:.4f})",
                invalidation_conditions="3-Month drops below 10-Month",
                urgency="low",
                risk_per_trade_pct=self.get_risk_pct()
            )
            
        elif fast_sma < slow_sma:
            stop_loss = last_close * 1.04
            take_profit = last_close - (stop_loss - last_close) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="short", phase="macro_trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"3-Month SMA ({fast_sma:.4f}) < 10-Month SMA ({slow_sma:.4f})",
                invalidation_conditions="3-Month rallies above 10-Month",
                urgency="low",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Exit when MAs cross back over."""
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.slow_ma:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        fast_sma = calculate_sma(htf_closes, self.fast_ma)
        slow_sma = calculate_sma(htf_closes, self.slow_ma)
        
        pos_dir = open_position.get("direction", "long")
        
        if pos_dir == "long" and fast_sma < slow_sma:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Macro Trend Reversal Exit (3M < 10M)")
            
        if pos_dir == "short" and fast_sma > slow_sma:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Macro Trend Reversal Exit (3M > 10M)")
            
        return None
