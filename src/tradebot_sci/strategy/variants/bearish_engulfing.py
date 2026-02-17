from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class BearishEngulfingStrategy(BaseStrategy):
    """
    Engulfing Candle Reversal at Key Structure.

    Classic price action pattern used across all asset classes.
    Enters when a bearish or bullish engulfing candle forms at
    a key structural level with HTF alignment.

    Works best in:
    - Bearish/reversal environments (Supply & Demand zones)
    - Pullbacks to resistance in downtrends
    - Pushes to support in uptrends

    Entry criteria:
    - Engulfing candle at a key level (recent swing high/low)
    - HTF trend alignment
    - Optional: RSI divergence for higher probability
    - Stop beyond engulfing candle's wick

    R:R: Always 2:1 minimum.
    """

    def __init__(self, swing_lookback=20, rsi_period=14):
        super().__init__("Bearish Engulfing")
        self.swing_lookback = swing_lookback
        self.rsi_period = rsi_period

    def _is_engulfing(self, curr, prev) -> str | None:
        """
        Detect engulfing pattern.
        Returns 'bearish', 'bullish', or None.
        """
        # Bearish Engulfing: current candle opens above prev close, closes below prev open
        # (Current is red, completely engulfs prior green candle)
        if (
            prev.close > prev.open  # Prior is green
            and curr.close < curr.open  # Current is red
            and curr.open >= prev.close  # Opens at or above prior close
            and curr.close <= prev.open  # Closes at or below prior open
        ):
            return "bearish"

        # Bullish Engulfing: current candle opens below prev close, closes above prev open
        # (Current is green, completely engulfs prior red candle)
        if (
            prev.close < prev.open  # Prior is red
            and curr.close > curr.open  # Current is green
            and curr.open <= prev.close  # Opens at or below prior close
            and curr.close >= prev.open  # Closes at or above prior open
        ):
            return "bullish"

        return None

    def _at_key_level(self, snapshot: MarketSnapshot, direction: str) -> bool:
        """Check if we're near a swing high (for bearish) or swing low (for bullish)."""
        if len(snapshot.candles) < self.swing_lookback + 2:
            return False

        lookback = snapshot.candles[-(self.swing_lookback + 1) : -1]
        recent_highs = [c.high for c in lookback]
        recent_lows = [c.low for c in lookback]
        last_candle = snapshot.candles[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_candle.close * 0.001)

        if direction == "bearish":
            # Near a recent swing high?
            swing_high = max(recent_highs)
            return abs(last_candle.high - swing_high) < atr * 1.0
        else:
            # Near a recent swing low?
            swing_low = min(recent_lows)
            return abs(last_candle.low - swing_low) < atr * 1.0

    def _check_rsi_divergence(self, snapshot: MarketSnapshot, direction: str) -> bool:
        """Optional RSI divergence check for higher probability."""
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.rsi_period + 10:
            return False

        rsi = calculate_rsi(closes, self.rsi_period)
        rsi_prev = calculate_rsi(closes[:-5], self.rsi_period)

        if direction == "bearish":
            # Price makes new high, RSI doesn't
            price_higher = closes[-1] > max(closes[-10:-1])
            rsi_lower = rsi < rsi_prev
            return price_higher and rsi_lower
        else:
            # Price makes new low, RSI doesn't
            price_lower = closes[-1] < min(closes[-10:-1])
            rsi_higher = rsi > rsi_prev
            return price_lower and rsi_higher

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        # If we have an open position, check for pyramid opportunity instead of blocking
        is_pyramid = False
        if open_position:
            pos_dir = open_position.get("direction", "")
            pyramid_count = open_position.get("pyramid_count", 1)
            max_pyramid = 3  # Conservative default
            if "profile" in gates:
                max_pyramid = getattr(gates["profile"], "max_pyramid_entries", 3)
            if pyramid_count >= max_pyramid:
                return None  # Max pyramids reached
            is_pyramid = True

        if len(snapshot.candles) < self.swing_lookback + 3:
            return None

        curr = snapshot.candles[-1]
        prev = snapshot.candles[-2]
        atr = calculate_atr(snapshot.candles, period=14) or (curr.close * 0.001)

        engulfing = self._is_engulfing(curr, prev)
        if engulfing is None:
            return None

        # Must be at a key level
        if not self._at_key_level(snapshot, engulfing):
            return None

        # HTF alignment
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        has_divergence = self._check_rsi_divergence(snapshot, engulfing)
        rsi = calculate_rsi([c.close for c in snapshot.candles], self.rsi_period)

        # --- BEARISH ENGULFING at resistance ---
        if engulfing == "bearish":
            # HTF must be bearish or neutral (not fighting bullish trend)
            if htf_dir in ("long", "bullish"):
                return None

            # Pyramid check: only scale into SHORT positions
            if is_pyramid:
                if pos_dir != "short":
                    return None  # Can't pyramid short signal into long position
                # Ensure we're entering at a LOWER price (better for shorts)
                entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0)
                if entry_price > 0 and curr.close >= entry_price:
                    return None  # Not at a better price for shorts

            stop_loss = curr.high + (atr * 1.5)  # 1.5 ATR buffer — safe from spread
            stop_dist = stop_loss - curr.close
            take_profit = curr.close - (stop_dist * 2.0)  # 2:1 R:R

            div_note = " + RSI Divergence" if has_divergence else ""
            action = "scale_in" if is_pyramid else "enter_short"
            pyramid_note = f" (Pyramid #{pyramid_count + 1})" if is_pyramid else ""

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="short",
                phase="correction",
                action=action,
                entry_price=curr.close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Bearish Engulfing at Resistance{pyramid_note} (RSI={rsi:.1f}{div_note})",
                invalidation_conditions=f"Close above engulfing high {curr.high:.4f}",
                management_instructions="Target 2R. Classic reversal pattern.",
                notes=f"Engulfing candle reversal{div_note}{pyramid_note}",
                urgency="high" if has_divergence else "medium",
            )

        # --- BULLISH ENGULFING at support ---
        if engulfing == "bullish":
            # HTF must be bullish or neutral (not fighting bearish trend)
            if htf_dir in ("short", "bearish"):
                return None

            # Pyramid check: only scale into LONG positions
            if is_pyramid:
                if pos_dir != "long":
                    return None  # Can't pyramid long signal into short position
                # Ensure we're entering at a HIGHER price (better for longs — price is moving)
                entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0)
                if entry_price > 0 and curr.close <= entry_price:
                    return None  # Not at a better price for longs

            stop_loss = curr.low - (atr * 1.5)  # 1.5 ATR buffer — safe from spread
            stop_dist = curr.close - stop_loss
            take_profit = curr.close + (stop_dist * 2.0)  # 2:1 R:R

            div_note = " + RSI Divergence" if has_divergence else ""
            action = "scale_in" if is_pyramid else "enter_long"
            pyramid_note = f" (Pyramid #{pyramid_count + 1})" if is_pyramid else ""

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="long",
                phase="correction",
                action=action,
                entry_price=curr.close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Bullish Engulfing at Support{pyramid_note} (RSI={rsi:.1f}{div_note})",
                invalidation_conditions=f"Close below engulfing low {curr.low:.4f}",
                management_instructions="Target 2R. Classic reversal pattern.",
                notes=f"Engulfing candle reversal{div_note}{pyramid_note}",
                urgency="high" if has_divergence else "medium",
            )

        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """Exit if structure invalidates (HTF reverses against us)."""
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        pos_dir = open_position.get("direction")

        # If HTF flips in our favor, hold. If it goes against us, exit.
        if pos_dir == "long" and htf_dir in ("short", "bearish"):
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "Engulfing Reversal: HTF turned bearish — exiting long",
            )
        if pos_dir == "short" and htf_dir in ("long", "bullish"):
            return close_position_decision(
                snapshot.symbol,
                snapshot.timeframe,
                "Engulfing Reversal: HTF turned bullish — exiting short",
            )

        return None
