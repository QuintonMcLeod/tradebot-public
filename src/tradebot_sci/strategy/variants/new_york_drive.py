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

class NewYorkDriveStrategy(BaseStrategy):
    """
    New York Momentum Continuation (NY Drive)
    Operates during the highest volume hours of the day (13:00 - 16:00 UTC).
    If price violently breaches the highest/lowest price established 
    during the London session, we enter with a dynamic momentum stop.
    """
    def __init__(self, **kwargs):
        super().__init__("NewYorkDrive")
        
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 24:
            return None
            
        if open_position:
            return None

        # Restrict execution to the NY/London Overlap Session (13:00 to 16:00 UTC)
        _ts = snapshot.candles[-1].timestamp
        if _ts.tzinfo is None:
            _ts = _ts.replace(tzinfo=timezone.utc)
        utc_hour = _ts.astimezone(timezone.utc).hour
        
        if not (13 <= utc_hour < 16):
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "NewYorkDrive: Outside NY overlapping hours")
            
        # Analyze today's London Range
        current_date_str = _ts.strftime("%Y-%m-%d")
        london_candles = []
        for c in snapshot.candles:
            cts = c.timestamp
            if cts.tzinfo is None: cts = cts.replace(tzinfo=timezone.utc)
            chour = cts.astimezone(timezone.utc).hour
            cdate = cts.strftime("%Y-%m-%d")
            if cdate == current_date_str and 7 <= chour < 13:
                london_candles.append(c)
                
        if not london_candles:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "NewYorkDrive: No London range established")
            
        london_high = max(c.high for c in london_candles)
        london_low = min(c.low for c in london_candles)
        
        last_candle = snapshot.candles[-1]
        
        atr = calculate_atr(snapshot.candles) or (last_candle.high - last_candle.low)
        
        # Bullish NY Drive (Breaking London High)
        if last_candle.close > london_high and last_candle.open <= london_high:
            # NY just smashed past the London high
            sl = last_candle.close - (atr * 1.5) # Wider logical stop to let momentum breathe
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="impulse", action="enter_long",
                entry_price=last_candle.close, stop_loss=sl, take_profit=None,
                risk_per_trade_pct=self.get_risk_pct(),
                urgency="high",
                structure_summary=f"NYDrive: Bullish breach of London High {london_high:.5f}",
                notes="NY Momentum breakout with 1.5 ATR breather."
            )
            
        # Bearish NY Drive (Breaking London Low)
        if last_candle.close < london_low and last_candle.open >= london_low:
            # NY just smashed through the London low
            sl = last_candle.close + (atr * 1.5)
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="impulse", action="enter_short",
                entry_price=last_candle.close, stop_loss=sl, take_profit=None,
                risk_per_trade_pct=self.get_risk_pct(),
                urgency="high",
                structure_summary=f"NYDrive: Bearish breach of London Low {london_low:.5f}",
                notes="NY Momentum breakout with 1.5 ATR breather."
            )

        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "NYDrive: Inside London Range")

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
        
        # NY momentum fades quickly after 16:00 UTC. Shift to aggressive 1 ATR trail once above 1R
        if r_multiple >= 1.0:
            atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)
            trail_distance = atr * 1.0
            
            if direction == "long":
                new_stop = current_price - trail_distance
                if new_stop > stop_price:
                    from tradebot_sci.strategy.decisions import hold_decision
                    return hold_decision(snapshot.symbol, snapshot.timeframe, f"NYDrive: Trailing stop ({r_multiple:.1f}R)", stop_loss=new_stop)
            else:
                new_stop = current_price + trail_distance
                if new_stop < stop_price:
                    from tradebot_sci.strategy.decisions import hold_decision
                    return hold_decision(snapshot.symbol, snapshot.timeframe, f"NYDrive: Trailing stop ({r_multiple:.1f}R)", stop_loss=new_stop)

        return None
