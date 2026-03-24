from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi

logger = logging.getLogger(__name__)

class QS_RSIMeanReversionStrategy(BaseStrategy):
    """
    3. RSI-2 Mean Reversion (with "QS Exit")
    Core Idea: Asset prices revert to a long-term average. 
    Rules: Buy when 2-period RSI crosses below 10. QS Exit: Sell when close > yesterday's high.
    We apply this to HTF for daily equivalence, or LTF for intraday swings.
    """
    
    def __init__(self, rsi_period: int = 2, rsi_threshold_long: int = 10, rsi_threshold_short: int = 90):
        super().__init__("QS RSI-2 Mean Reversion")
        self.rsi_period = rsi_period
        self.rsi_threshold_long = rsi_threshold_long
        self.rsi_threshold_short = rsi_threshold_short

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < self.rsi_period + 1:
            return None
            
        htf_closes = [c.close for c in htf_candles]
        
        # Calculate RSI on HTF closes
        rsi_current = calculate_rsi(htf_closes, self.rsi_period)
        
        last_close = snapshot.candles[-1].close
        
        if rsi_current < self.rsi_threshold_long:
            # Oversold - Buy
            stop_loss = last_close * 0.98  # 2% generic stop
            take_profit = last_close + (last_close - stop_loss) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="long", phase="reversion", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"RSI({self.rsi_period}) = {rsi_current:.1f} < {self.rsi_threshold_long}",
                invalidation_conditions="Further breakdown beyond SL",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )
            
        elif rsi_current > self.rsi_threshold_short:
            # Overbought - Short
            stop_loss = last_close * 1.02
            take_profit = last_close - (stop_loss - last_close) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="short", phase="reversion", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss,
                structure_summary=f"RSI({self.rsi_period}) = {rsi_current:.1f} > {self.rsi_threshold_short}",
                invalidation_conditions="Further squeeze beyond SL",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """QS Exit: Sell when close > yesterday's high."""
        htf_candles = snapshot.htf_candles
        if not htf_candles or len(htf_candles) < 2:
            return None
            
        pos_dir = open_position.get("direction", "long")
        last_close = snapshot.candles[-1].close
        
        # "Yesterday's high" is approximately the high of the previous HTF candle (if daily), 
        # or we just use the previous HTF candle's high.
        prev_htf_candle = htf_candles[-2]
        
        if pos_dir == "long" and last_close > prev_htf_candle.high:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "QS Exit: Close > Prev High")
            
        if pos_dir == "short" and last_close < prev_htf_candle.low:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "QS Exit: Close < Prev Low")
            
        return None
