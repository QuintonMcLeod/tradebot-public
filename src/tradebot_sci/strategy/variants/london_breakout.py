from __future__ import annotations
import logging
from datetime import time
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
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

    def _to_utc(self, dt):
        """Convert timestamp to UTC for London session time comparison."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    def _get_london_range(self, snapshot: MarketSnapshot) -> Optional[Tuple[float, float]]:
        # Find the candles within the range_start and range_end today
        candles_today = []
        if not snapshot.candles:
            return None
            
        latest_utc = self._to_utc(snapshot.candles[-1].timestamp)
        today_date = latest_utc.date()
        
        for c in snapshot.candles:
            c_utc = self._to_utc(c.timestamp)
            if c_utc.date() == today_date:
                t = c_utc.time()
                if self.range_start <= t < self.range_end:
                    candles_today.append(c)
        
        if not candles_today:
            return None
            
        high = max(c.high for c in candles_today)
        low = min(c.low for c in candles_today)
        return low, high

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        current_utc = self._to_utc(snapshot.candles[-1].timestamp).time()
        # Only trade after the range is established
        if current_utc <= self.range_end:
            return None
            
        # Don't trade too late (e.g., after 12:00 UTC)
        if current_utc > time(12, 0):
            return None

        london_range = self._get_london_range(snapshot)
        if not london_range:
            return None
            
        low, high = london_range
        last_close = snapshot.candles[-1].close
        prev_close = snapshot.candles[-2].close
        
        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # Bullish Breakout (only when trend allows)
        if htf_dir in ("long", "neutral") and prev_close <= high and last_close > high:
            stop_loss = low
            risk = high - low
            target = high + (risk * 2.0)  # 2:1 R:R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"London Breakout High (@{high:.4f})",
                invalidation_conditions="Close back inside range",
                management_instructions="Target 2R",
                notes="Standard London Breakout strategy",
                urgency="high"
            )

        # Bearish Breakout (only when trend allows)
        if htf_dir in ("short", "neutral") and prev_close >= low and last_close < low:
            stop_loss = high
            risk = high - low
            target = low - (risk * 2.0)  # 2:1 R:R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"London Breakout Low (@{low:.4f})",
                invalidation_conditions="Close back inside range",
                management_instructions="Target 2R",
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
            
        # [DYNAMIC RISK] Breakeven & Trailing
        entry_price = float(open_position["entry_price"])
        current_price = snapshot.candles[-1].close
        current_stop = float(open_position.get("stop_price") or 0.0)
        
        initial_risk = abs(entry_price - current_stop)
        if initial_risk > 0:
            profit_dist = (current_price - entry_price) if direction == "long" else (entry_price - current_price)
            r_multiple = profit_dist / initial_risk
            
            # 1. Breakeven
            if direction == "long" and current_stop < entry_price and r_multiple >= 1.0:
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="management", action="hold", stop_loss=entry_price,
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R)"
                )
            if direction == "short" and current_stop > entry_price and r_multiple >= 1.0:
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="management", action="hold", stop_loss=entry_price,
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R)"
                )

        # [SAFETY] Managed by StrategyEngine via SafetyGuard
        return None
