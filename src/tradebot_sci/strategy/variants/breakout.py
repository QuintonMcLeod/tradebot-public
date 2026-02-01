from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class VolatilityBreakoutStrategy(BaseStrategy):
    """
    High-frequency breakout strategy.
    Captures explosive moves when price breaks the recent range with high ATR/RSI momentum.
    """
    
    def __init__(self, range_period=20, atr_mult=1.5):
        super().__init__("Volatility Breakout")
        self.range_period = range_period
        self.atr_mult = atr_mult

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.range_period + 1:
            return None
            
        recent_high = max(c.high for c in snapshot.candles[-self.range_period:-1])
        recent_low = min(c.low for c in snapshot.candles[-self.range_period:-1])
        
        last_candle = snapshot.candles[-1]
        last_close = last_candle.close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        rsi = calculate_rsi(closes, 14)
        
        # Long Entry: Breakout of range high + RSI > 60
        if last_close > recent_high and rsi > 60:
            # [ARMOR] 2x ATR Stops
            stop_dist = atr * 2.0
            stop_loss = last_close - stop_dist
            target = last_close + (stop_dist * 2.0)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Volatility Breakout (High={recent_high:.4f}, RSI={rsi:.1f})",
                invalidation_conditions="Close below breakout bar",
                management_instructions="Net-Zero at 1xATR",
                notes="Armor Entry (2x ATR)",
                urgency="high",
                risk_per_trade_pct=0.10
            )

        # Short Entry: Breakout of range low + RSI < 40
        if last_close < recent_low and rsi < 40:
            # [ARMOR] 2x ATR Stops
            stop_dist = atr * 2.0
            stop_loss = last_close + stop_dist
            target = last_close - (stop_dist * 2.0)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Volatility Breakout (Low={recent_low:.4f}, RSI={rsi:.1f})",
                invalidation_conditions="Close above breakout bar",
                management_instructions="Net-Zero at 1xATR",
                notes="Armor Entry (2x ATR)",
                urgency="high",
                risk_per_trade_pct=0.10
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        # Fast exit if RSI reverses significantly
        rsi = calculate_rsi([c.close for c in snapshot.candles], 14)
        pos_dir = open_position.get("direction")
        
        if pos_dir == "long" and rsi < 45:
             return close_position_decision(snapshot.symbol, snapshot.timeframe, "Volatility Breakout: Momentum Reversal (RSI < 45)")
        if pos_dir == "short" and rsi > 55:
             return close_position_decision(snapshot.symbol, snapshot.timeframe, "Volatility Breakout: Momentum Reversal (RSI > 55)")

        # [SAFETY] Managed by StrategyEngine via SafetyGuard
        return None
