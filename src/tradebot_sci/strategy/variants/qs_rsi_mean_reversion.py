from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi, calculate_sma
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class QS_RSIMeanReversionStrategy(BaseStrategy):
    """
    QS RSI Trend-Pullback (Authentic Larry Connors RSI-2)
    Core Idea: Buy deep pullbacks WITHIN established trends.
    Rules: 
      - LONG: Price > 200 SMA and RSI(2) < 10
      - SHORT: Price < 200 SMA and RSI(2) > 90
    QS Exit: Sell when price closes above the 5-period SMA (short-term mean).
    Executes on the active timeframe (LTF) to prevent cross-timescale churning.
    """
    
    def __init__(self, rsi_period: int = 2, rsi_threshold_long: int = 15, rsi_threshold_short: int = 85, trend_sma: int = 200, exit_sma: int = 5, **kwargs):
        super().__init__("QS RSI Trend-Pullback")
        self.rsi_period = rsi_period
        self.rsi_threshold_long = rsi_threshold_long
        self.rsi_threshold_short = rsi_threshold_short
        self.trend_sma = trend_sma
        self.exit_sma = exit_sma

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        # Need enough candles for the 200 SMA
        if not candles or len(candles) <= self.trend_sma:
            return None
            
        closes = [c.close for c in candles]
        last_close = closes[-1]
        
        # 1. Trend Filter (The Safety Net to prevent catching falling knives)
        current_sma = calculate_sma(closes, self.trend_sma)
        if not current_sma:
            return None

        # 2. Timing (RSI-2)
        rsi_current = calculate_rsi(closes, self.rsi_period)
        if rsi_current is None:
            return None
            
        # 3. Dynamic Stop Loss (ATR based)
        atr_14 = calculate_atr(candles, period=14)
        atr_buffer = atr_14 * 1.5 if atr_14 else (last_close * 0.015)

        # Probabilistic Score Calculation
        score = 0.0
        
        # LONG CONDITION: Macro trend is UP, micro trend is severely OVER SOLD
        if last_close > current_sma and rsi_current < self.rsi_threshold_long:
            # Base score depends on how deep the pullback is
            score = 60.0 + ((self.rsi_threshold_long - rsi_current) * 2.0)
            score = min(score, 100.0) # Cap at 100
            
            stop_loss = last_close - atr_buffer
            take_profit = last_close + (atr_buffer * 1.5)  # Quick bounce
            
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss,
                score=score,
                structure_summary=f"Authentic Pullback: >{self.trend_sma}SMA | RSI({self.rsi_period})={rsi_current:.1f}",
                invalidation_conditions=f"Closes decisively below {self.trend_sma} SMA",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )
            
        # SHORT CONDITION: Macro trend is DOWN, micro trend is severely OVER BOUGHT
        elif last_close < current_sma and rsi_current > self.rsi_threshold_short:
            score = 60.0 + ((rsi_current - self.rsi_threshold_short) * 2.0)
            score = min(score, 100.0)
            
            stop_loss = last_close + atr_buffer
            take_profit = last_close - (atr_buffer * 1.5)
            
            return AITradeDecision(
                symbol=snapshot.symbol,
                take_profit=take_profit, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss,
                score=score,
                structure_summary=f"Authentic Squeeze: <{self.trend_sma}SMA | RSI({self.rsi_period})={rsi_current:.1f}",
                invalidation_conditions=f"Closes decisively above {self.trend_sma} SMA",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """Larry Connors Exit: Sell when price crosses the fast moving average (short-term mean)."""
        candles = snapshot.candles
        if not candles or len(candles) <= self.exit_sma:
            return None
            
        pos_dir = open_position.get("direction", "long")
        closes = [c.close for c in candles]
        last_close = closes[-1]
        
        fast_sma = calculate_sma(closes, self.exit_sma)
        if not fast_sma:
            return None
        
        # We mean reverted! Take the profit dynamically.
        if pos_dir == "long" and last_close > fast_sma:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, f"Mean Reverted: Close > {self.exit_sma}SMA")
            
        if pos_dir == "short" and last_close < fast_sma:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, f"Mean Reverted: Close < {self.exit_sma}SMA")
            
        return None
