from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import detect_no_trade_zone, detect_indication, calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class RobotEvolutionStrategy(BaseStrategy):
    """
    Optimized scalp strategy focusing on 2.0R targets and safe 1.5 ATR stops.
    Designed for account growth in ranging or choppy markets.
    """
    
    def __init__(self):
        super().__init__("Robot Evolution")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 20:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Insufficient candle history (<20)")
            
        htf_candles = snapshot.htf_candles or snapshot.candles
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        
        ntz = detect_no_trade_zone(htf_candles, swing_lookback=2)
        if not ntz or ntz.is_broken:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "No valid No-Trade-Zone (NTZ) detected or NTZ broken")
            
        current_price = snapshot.candles[-1].close
        last_bar = snapshot.candles[-1]
        ntz_range = ntz.high - ntz.low
        if ntz_range <= 0:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "Invalid NTZ range (<=0)")

        indication = detect_indication(ltf_candles, swing_lookback=1)
        if not indication:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "No Directional Indication detected")
            
        atr = calculate_atr(snapshot.candles, period=14) or (ntz_range * 0.1)
        
        # [VERIFIED-MATH] 1.5 ATR Safety / 2.0R Target Alignment
        atr_floor = current_price * 0.002
        effective_atr = max(atr, atr_floor)
        stop_dist = effective_atr * 1.5
        
        rejection_reasons = []

        # Long: Sweep of NTZ Low + Bullish Indication
        lowest_recent = min(c.low for c in snapshot.candles[-5:])
        if indication.direction == "long":
            if lowest_recent < ntz.low and current_price > ntz.low:
                if last_bar.close > last_bar.open:
                    stop_loss = lowest_recent - stop_dist
                    target = current_price + (stop_dist * 2.0)
                    
                    notes = f"Robot Evolution Long: 1.5ATR Stop / 2.0R Target (Effective ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="long", phase="chop", action="enter_long",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=UserConfig.BASE_RISK_PCT,
                        urgency="high", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close below sweep low.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
                else:
                    rejection_reasons.append("Long setup found but last candle not bullish")
            else:
                rejection_reasons.append(f"Price not sweeping NTZ Low ({ntz.low:.2f}) correctly")

        # Short: Sweep of NTZ High + Bearish Indication
        highest_recent = max(c.high for c in snapshot.candles[-5:])
        if indication.direction == "short":
            if highest_recent > ntz.high and current_price < ntz.high:
                if last_bar.close < last_bar.open:
                    stop_loss = highest_recent + stop_dist
                    target = current_price - (stop_dist * 2.0)
                    
                    notes = f"Robot Evolution Short: 1.5ATR Stop / 2.0R Target (Effective ATR: {effective_atr:.4f})"
                    return AITradeDecision(
                        symbol=snapshot.symbol,
                        timeframe=snapshot.timeframe,
                        bias="short", phase="chop", action="enter_short",
                        entry_price=current_price, stop_loss=stop_loss, take_profit=target,
                        risk_per_trade_pct=UserConfig.BASE_RISK_PCT,
                        urgency="high", structure_summary=notes, notes=notes, gates=gates,
                        invalidation_conditions="Close above sweep high.",
                        management_instructions="Target 2R. Managed by Robot Engine.",
                    )
                else:
                    rejection_reasons.append("Short setup found but last candle not bearish")
            else:
                 rejection_reasons.append(f"Price not sweeping NTZ High ({ntz.high:.2f}) correctly")
        
        final_reason = f"Monitoring NTZ ({ntz.low:.2f}-{ntz.high:.2f}). " + "; ".join(rejection_reasons)
        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, final_reason)

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        # [AGGRESIVE VALIDATION] Disable ALL engine exits for chop scalps
        # Let Target or Stop handle it (configured in models/backtest)
        return None
