from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_bollinger_bands, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class MeanReversionStrategy(BaseStrategy):
    """
    Standard Bollinger Band + RSI Mean Reversion strategy.
    Entries occur when price is overextended outside bands and RSI shows exhaustion.
    """
    
    def __init__(self, bb_period=15, bb_std=2.5, rsi_period=14, rsi_overbought=75, rsi_oversold=25, base_risk_pct=0.10):
        super().__init__("Mean Reversion")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.base_risk_pct = base_risk_pct

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period:
            return None
            
        lower, middle, upper = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # 1. Handle Pyramiding (Scale-in)
        if open_position:
            # Only pyramid if we haven't hit the limit (unless infinite)
            max_entries = UserConfig.MAX_PYRAMID_ENTRIES
            is_infinite = getattr(UserConfig, "INFINITE_PYRAMIDING", False)
            if not is_infinite and open_position.get("pyramid_count", 0) >= max_entries:
                return None
                
            # [COOLDOWN] Prevent back-to-back bar scaling (Wait 6 bars / 30 mins)
            if open_position.get("bars_since_scale", 0) < 6:
                return None
            
            pos_dir = open_position.get("direction")
            entry_price = open_position.get("entry_price", last_close)
            
            # [SINGULARITY] Check for Scale-in on even deeper exhaustion
            # If LONG: price must be even lower than lower band and entry_price
            # SUPER-EXTREME: Only pyramid on RSI < 15 (not 25)
            if pos_dir == "long" and last_close < lower and last_close < entry_price:
                 if rsi < 15:  # Super-Extreme Oversold
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="correction", action="scale_in",
                        entry_price=last_close, stop_loss=open_position.get("stop_loss"), take_profit=upper,
                        risk_per_trade_pct=self.base_risk_pct * 2.0,  # Always 2x on super-extreme
                        structure_summary=f"Mean Reversal SUPER-SCALE (RSI={rsi:.1f})",
                        invalidation_conditions=f"Close below stop {open_position.get('stop_loss')}",
                        management_instructions="Target Opposite Bollinger Band (Scaled).",
                        urgency="high",
                        notes="Pyramiding into SUPER-EXTREME exhaustion."
                    )
            # If SHORT: price must be even higher than upper band and entry_price
            # SUPER-EXTREME: Only pyramid on RSI > 85 (not 75)
            if pos_dir == "short" and last_close > upper and last_close > entry_price:
                 if rsi > 85:  # Super-Extreme Overbought
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="correction", action="scale_in",
                        entry_price=last_close, stop_loss=open_position.get("stop_loss"), take_profit=lower,
                        risk_per_trade_pct=self.base_risk_pct * 2.0,  # Always 2x on super-extreme
                        structure_summary=f"Mean Reversal SUPER-SCALE (RSI={rsi:.1f})",
                        invalidation_conditions=f"Close above stop {open_position.get('stop_loss')}",
                        management_instructions="Target Opposite Bollinger Band (Scaled).",
                        urgency="high",
                        notes="Pyramiding into SUPER-EXTREME exhaustion."
                    )
            return None

        # 2. Handle Initial Entry
        # Long Entry: Close below lower band + oversold RSI
        if last_close < lower and rsi < self.rsi_oversold:
            stop_dist = atr * 2.0
            stop_loss = last_close - stop_dist
            target = upper # TARGET OPPOSITE BAND
            
            # [EXTREME SCALE] Double risk if RSI is super-oversold (<20)
            risk_mult = 2.0 if rsi < 20 else 1.0
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Mean Reversal (RSI={rsi:.1f}, Scaling={risk_mult}x)",
                invalidation_conditions=f"Close below stop {stop_loss:.4f}",
                management_instructions="Target Opposite Bollinger Band.",
                risk_per_trade_pct=self.base_risk_pct * risk_mult,
                notes="Extreme Mean Reversion variant",
                urgency="high" if rsi < 20 else "medium"
            )

        # Short Entry: Close above upper band + overbought RSI
        if last_close > upper and rsi > self.rsi_overbought:
            stop_dist = atr * 2.0
            stop_loss = last_close + stop_dist
            target = lower # TARGET OPPOSITE BAND
            
            # [EXTREME SCALE] Double risk if RSI is super-overbought (>80)
            risk_mult = 2.0 if rsi > 80 else 1.0
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Mean Reversal (RSI={rsi:.1f}, Scaling={risk_mult}x)",
                invalidation_conditions=f"Close above stop {stop_loss:.4f}",
                management_instructions="Target Opposite Bollinger Band.",
                risk_per_trade_pct=self.base_risk_pct * risk_mult,
                notes="Extreme Mean Reversion variant",
                urgency="high" if rsi > 80 else "medium"
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict) -> Optional[AITradeDecision]:
        # Most exits are handled by TP/SL, but we could exit if RSI reverses
        return None
