from __future__ import annotations
import logging
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class GoldenPocketStrategy(BaseStrategy):
    """
    Dynamic Value Pullback (The Golden Pocket)
    Requires structured Macro Trend (EMA 21 > EMA 55 for Longs).
    Waits for price to pull back deep into the 55 EMA "pocket".
    Enter on the first rejection print out of the pocket.
    """
    def __init__(self, **kwargs):
        super().__init__("GoldenPocket")
        
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 60:
            return None
            
        if open_position:
            return None

        # Verify trending regime
        if gates.get("market_regime") != "trending":
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "GoldenPocket: Market not trending")

        # Demand strong ADX > 25
        htf_adx = gates.get("htf_adx", 0)
        ltf_adx = gates.get("ltf_adx", 0)
        if htf_adx < 25 and ltf_adx < 25:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "GoldenPocket: ADX too low for deep pullback")

        # Natively compute EMA21 and EMA55 from the raw candles to ensure precision
        closes = [c.close for c in snapshot.candles]
        
        def _ema(period):
            k = 2 / (period + 1)
            emas = [closes[0]]
            for p in closes[1:]:
                emas.append((p * k) + (emas[-1] * (1 - k)))
            return emas

        ema21 = _ema(21)
        ema55 = _ema(55)
        
        c0 = snapshot.candles[-1]
        c1 = snapshot.candles[-2]
        
        e21_0, e21_1 = ema21[-1], ema21[-2]
        e55_0, e55_1 = ema55[-1], ema55[-2]
        
        # Bullish Golden Pocket
        if e21_0 > e55_0 and e21_1 > e55_1:
            # Did price dip deeply towards the 55 EMA recently?
            recent_low = min(c.low for c in snapshot.candles[-6:-1])
            # Tolerance: low should breach 21 EMA and approach 55 EMA within ~0.2%
            dist_to_55 = abs(recent_low - e55_1) / e55_1
            
            if recent_low < e21_1 and dist_to_55 < 0.002:
                # Rejection closed above the 21 EMA, confirming bounce momentum
                if c0.close > e21_0 and c0.close > c0.open:
                    atr = calculate_atr(snapshot.candles) or (c0.high - c0.low)
                    sl = c0.low - (atr * 1.5)  # Structural breather
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="correction", action="enter_long",
                        entry_price=c0.close, stop_loss=sl, take_profit=None,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="high",
                        structure_summary=f"GoldenPocket: Bullish pullback near 55 EMA ({e55_0:.5f}) confirmed",
                        notes="Deep pullback entry with momentum resuming above 21 EMA."
                    )
                    
        # Bearish Golden Pocket
        if e21_0 < e55_0 and e21_1 < e55_1:
            recent_high = max(c.high for c in snapshot.candles[-6:-1])
            dist_to_55 = abs(recent_high - e55_1) / e55_1
            
            if recent_high > e21_1 and dist_to_55 < 0.002:
                if c0.close < e21_0 and c0.close < c0.open:
                    atr = calculate_atr(snapshot.candles) or (c0.high - c0.low)
                    sl = c0.high + (atr * 1.5)  # Structural breather
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="correction", action="enter_short",
                        entry_price=c0.close, stop_loss=sl, take_profit=None,
                        risk_per_trade_pct=self.get_risk_pct(),
                        urgency="high",
                        structure_summary=f"GoldenPocket: Bearish pullback near 55 EMA ({e55_0:.5f}) confirmed",
                        notes="Deep pullback entry with momentum resuming below 21 EMA."
                    )

        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "GoldenPocket: No EMA-55 deep rejection detected")

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        # Handled by global Conductor logic (static R-target & trailing structural stops)
        return None
