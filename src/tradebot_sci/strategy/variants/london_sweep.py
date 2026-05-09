from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class LondonSweepStrategy(BaseStrategy):
    """
    The Banker's Trap (London Liquidity Sweep)
    Operates during the London Session (07:00 - 12:00 UTC).
    Identifies the Asian Session (00:00 - 07:00 UTC) High/Low.
    If price sweeps these levels but immediately closes back inside,
    we enter a reversal with an ultra-tight stop right above/below the wick. 
    """
    def __init__(self, **kwargs):
        super().__init__("LondonSweep")
        
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 24:
            return None
            
        if open_position:
            return None

        # NOTE: Session timing is handled by the Global Scheduler, not this strategy.
        # This strategy focuses purely on detecting liquidity sweeps of Asian extremes.
        # Configure your preferred trading windows in the scheduler settings.
        
        # Analyze today's Asian Range (historical data for sweep detection)
        current_date_str = snapshot.candles[-1].timestamp.strftime("%Y-%m-%d")
        asian_candles = []
        for c in snapshot.candles:
            cts = c.timestamp
            if cts.tzinfo is None: cts = cts.replace(tzinfo=timezone.utc)
            chour = cts.astimezone(timezone.utc).hour
            cdate = cts.strftime("%Y-%m-%d")
            if cdate == current_date_str and 0 <= chour < 7:
                asian_candles.append(c)
                
        if not asian_candles:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "LondonSweep: No Asian range established")
            
        asian_high = max(c.high for c in asian_candles)
        asian_low = min(c.low for c in asian_candles)
        
        last_candle = snapshot.candles[-1]
        
        atr = calculate_atr(snapshot.candles) or (last_candle.high - last_candle.low)
        buffer = atr * 0.1
        
        # Bearish Sweep Check
        recent_high = max(c.high for c in snapshot.candles[-3:])
        if recent_high > asian_high and last_candle.close < asian_high:
            sl = recent_high + buffer
            risk_dist = abs(last_candle.close - sl)
            # Reversal Short logic
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_candle.close, stop_loss=sl, take_profit=None,
                risk_per_trade_pct=self.get_risk_pct(),
                urgency="medium",
                structure_summary=f"LondonSweep: Bearish sweep of Asian High {asian_high:.5f}",
                notes="Ultra-tight SL placed above sweep peak."
            )
            
        # Bullish Sweep Check
        recent_low = min(c.low for c in snapshot.candles[-3:])
        if recent_low < asian_low and last_candle.close > asian_low:
            sl = recent_low - buffer
            risk_dist = abs(last_candle.close - sl)
            # Reversal Long logic
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_candle.close, stop_loss=sl, take_profit=None,
                risk_per_trade_pct=self.get_risk_pct(),
                urgency="medium",
                structure_summary=f"LondonSweep: Bullish sweep of Asian Low {asian_low:.5f}",
                notes="Ultra-tight SL placed below sweep peak."
            )

        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "LondonSweep: No active sweeps of Asian extremes")

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or not open_position:
            return None

        entry_price = float(open_position.get("entry_price", 0))
        stop_price = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0))
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction", "long")

        if entry_price <= 0 or stop_price <= 0: return None
        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0: return None
        
        profit = current_price - entry_price if direction == "long" else entry_price - current_price
        r_multiple = profit / initial_risk
        
        # Super tight trail due to exact wick-based entry
        if r_multiple >= 1.0:
            atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)
            trail_distance = atr * 0.5
            
            if direction == "long":
                new_stop = current_price - trail_distance
                if new_stop > stop_price:
                    from tradebot_sci.strategy.decisions import hold_decision
                    return hold_decision(snapshot.symbol, snapshot.timeframe, f"LondonSweep: Trailing stop ({r_multiple:.1f}R)", stop_loss=new_stop)
            else:
                new_stop = current_price + trail_distance
                if new_stop < stop_price:
                    from tradebot_sci.strategy.decisions import hold_decision
                    return hold_decision(snapshot.symbol, snapshot.timeframe, f"LondonSweep: Trailing stop ({r_multiple:.1f}R)", stop_loss=new_stop)

        return None
