from __future__ import annotations
import logging
from datetime import time
from typing import Optional, Tuple
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class LondonBreakoutStrategy(BaseStrategy):
    """
    Classic Forex strategy: Trade the breakout of the first hour of the London session.
    """
    
    def __init__(self, range_start="08:00", range_end="09:00"):
        super().__init__("London Breakout")
        self.range_start = time.fromisoformat(range_start)
        self.range_end = time.fromisoformat(range_end)

    def _get_london_range(self, snapshot: MarketSnapshot) -> Optional[Tuple[float, float]]:
        # Find the candles within the range_start and range_end today
        candles_today = []
        if not snapshot.candles:
            return None
            
        latest_date = snapshot.candles[-1].timestamp.date()
        for c in snapshot.candles:
            if c.timestamp.date() == latest_date:
                t = c.timestamp.time()
                if self.range_start <= t < self.range_end:
                    candles_today.append(c)
        
        if not candles_today:
            return None
            
        high = max(c.high for c in candles_today)
        low = min(c.low for c in candles_today)
        return low, high

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        current_time = snapshot.candles[-1].timestamp.time()
        # Only trade after the range is established
        if current_time <= self.range_end:
            return None
            
        # Don't trade too late (e.g., after 12:00)
        if current_time > time(12, 0):
            return None

        london_range = self._get_london_range(snapshot)
        if not london_range:
            return None
            
        low, high = london_range
        last_close = snapshot.candles[-1].close
        prev_close = snapshot.candles[-2].close
        
        # Bullish Breakout
        if prev_close <= high and last_close > high:
            stop_loss = low
            risk = high - low
            target = high + (risk * 1.5)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"London Breakout High (@{high:.4f})",
                invalidation_conditions="Close back inside range",
                management_instructions="Target 1.5R",
                notes="Standard London Breakout strategy",
                urgency="high"
            )

        # Bearish Breakout
        if prev_close >= low and last_close < low:
            stop_loss = high
            risk = high - low
            target = low - (risk * 1.5)
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"London Breakout Low (@{low:.4f})",
                invalidation_conditions="Close back inside range",
                management_instructions="Target 1.5R",
                notes="Standard London Breakout strategy",
                urgency="high"
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        # Exit if price returns into the range (failed breakout)
        london_range = self._get_london_range(snapshot)
        if not london_range:
            return None
            
        low, high = london_range
        last_close = snapshot.candles[-1].close
        direction = open_position.get("direction")
        
        if direction == "long" and last_close < high:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Failed London Breakout (Price returned inside range)")
        if direction == "short" and last_close > low:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Failed London Breakout (Price returned inside range)")
            
        return None
