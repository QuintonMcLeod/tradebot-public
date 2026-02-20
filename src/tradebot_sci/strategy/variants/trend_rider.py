from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class TrendRiderStrategy(BaseStrategy):
    """
    Trend Rider: EMA Pullback in Strong Trend.

    Proven institutional method. Waits for price to pull back to the
    21 EMA during a confirmed strong trend, then enters on the bounce.

    Entry criteria:
    - HTF trend strength >= 0.5 (strong, not choppy)
    - Price pulls back TO the 21 EMA (within 0.3 ATR)
    - Bounce candle closes back in trend direction
    - RSI between 40-60 (confirms pullback, not full reversal)

    R:R: Always 2:1 minimum.
    """

    def __init__(self, ema_period=21, rsi_period=14):
        super().__init__("Trend Rider")
        self.ema_period = ema_period
        self.rsi_period = rsi_period

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        if open_position:
            return None

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.ema_period + 5:
            return None

        ema_21 = calculate_ema(closes, self.ema_period)
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)

        last_close = closes[-1]
        prev_close = closes[-2]

        # Must have a strong HTF trend
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_strength = float(gates.get("htf_strength", 0))

        if htf_dir == "neutral" or htf_strength < 0.5:
            return None

        # RSI must be between 40-60 (confirms pullback, not reversal)
        if rsi < 40 or rsi > 60:
            return None

        # Distance from EMA
        ema_dist = abs(last_close - ema_21)
        proximity_threshold = atr * 0.3  # Within 0.3 ATR of the EMA

        # --- BULLISH PULLBACK ---
        if htf_dir in ("long",):
            # Price was above EMA, pulled back to it, and bounced
            touched_ema = ema_dist < proximity_threshold or last_close <= ema_21
            bounced = last_close > prev_close  # Closing higher = bounce

            if touched_ema and bounced and last_close > ema_21:
                # Find swing low for stop
                recent_lows = [c.low for c in snapshot.candles[-10:]]
                swing_low = min(recent_lows)
                stop_dist = max(last_close - swing_low, atr * 1.5)
                stop_loss = last_close - stop_dist
                take_profit = last_close + (stop_dist * 2.0)  # 2:1 R:R

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="long",
                    phase="trend",
                    action="enter_long",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Trend Rider: EMA21 Pullback Long (RSI={rsi:.1f}, HTF={htf_strength:.2f})",
                    invalidation_conditions=f"Close below swing low {swing_low:.4f}",
                    management_instructions="Target 2R. Trail stop to EMA once 1R in profit.",
                    notes="EMA Pullback — proven trend continuation method",
                    urgency="medium",
                )

        # --- BEARISH PULLBACK ---
        if htf_dir in ("short",):
            touched_ema = ema_dist < proximity_threshold or last_close >= ema_21
            bounced = last_close < prev_close  # Closing lower = bearish bounce

            if touched_ema and bounced and last_close < ema_21:
                recent_highs = [c.high for c in snapshot.candles[-10:]]
                swing_high = max(recent_highs)
                stop_dist = max(swing_high - last_close, atr * 1.5)
                stop_loss = last_close + stop_dist
                take_profit = last_close - (stop_dist * 2.0)  # 2:1 R:R

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="short",
                    phase="trend",
                    action="enter_short",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Trend Rider: EMA21 Pullback Short (RSI={rsi:.1f}, HTF={htf_strength:.2f})",
                    invalidation_conditions=f"Close above swing high {swing_high:.4f}",
                    management_instructions="Target 2R. Trail stop to EMA once 1R in profit.",
                    notes="EMA Pullback — proven trend continuation method",
                    urgency="medium",
                )

        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """Exit if trend reverses (HTF flips against position direction)."""
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        pos_dir = open_position.get("direction")

        if pos_dir == "long" and htf_dir in ("short",):
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "Trend Rider: HTF trend reversed to bearish — exiting long",
            )
        if pos_dir == "short" and htf_dir in ("long",):
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "Trend Rider: HTF trend reversed to bullish — exiting short",
            )

        return None
