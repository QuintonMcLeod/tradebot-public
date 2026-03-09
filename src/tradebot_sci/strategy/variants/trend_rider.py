from __future__ import annotations
import logging
from typing import Optional, Tuple
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class TrendRiderStrategy(BaseStrategy):
    """
    EMA Trend Rider — Pullback Entry on Confirmed Trend.

    Production forex bot strategy (classic EMA pullback + crossover).
    Waits for EMA(8)/EMA(21) crossover to establish trend direction,
    then enters on pullback to the 21 EMA.

    Filters:
    - ADX > 20 (from trend detection gates) — confirms trending market
    - HTF trend strength >= 0.25 — confirms institutional flow
    - RSI 40-60 — confirms pullback (not reversal)

    Entry: Price pulls back to EMA(21) and bounces in trend direction
    Exit:  Trailing stop at 2× ATR OR reverse EMA crossover
    Stop:  Swing low/high + 1.5× ATR minimum
    Target: 2.5R (let winners run)
    """

    def __init__(self, fast_ema=8, slow_ema=21, rsi_period=14):
        super().__init__("Trend Rider")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> Tuple[float, str, str]:
        """Score how close the TrendRider entry filters are to triggering.

        Each filter contributes points to a 0-100 score:
          HTF direction (not neutral)    = 20 pts
          HTF strength ≥ 0.5             = 15 pts
          EMA(8)/EMA(21) aligned         = 20 pts
          RSI in 40-60 (pullback zone)   = 15 pts
          Price near EMA(21) (≤0.3 ATR)  = 15 pts
          Bounce confirmed               = 15 pts
        """
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.slow_ema + 10:
            return 0.0, "F-", "Trend Rider: insufficient data"

        score = 0.0
        details = []

        # 1. HTF direction
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        if htf_dir in ("long", "short"):
            score += 20
            details.append(f"HTF={htf_dir}")
        else:
            details.append("HTF=neutral")

        # 2. HTF strength
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength >= 0.25:
            score += 15
            details.append(f"str={htf_strength:.2f}")
        else:
            details.append(f"str={htf_strength:.2f}<0.25")

        # 3. EMA alignment
        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        aligned = (htf_dir == "long" and ema_fast > ema_slow) or \
                  (htf_dir == "short" and ema_fast < ema_slow)
        if aligned:
            score += 20
            details.append("EMA✓")
        else:
            details.append("EMA✗")

        # 4. RSI in pullback zone (25-75)
        rsi = calculate_rsi(closes, self.rsi_period)
        if 25 <= rsi <= 75:
            score += 15
            details.append(f"RSI={rsi:.0f}")
        else:
            details.append(f"RSI={rsi:.0f}✗")

        # 5. Price near EMA(21)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)
        ema_dist = abs(closes[-1] - ema_slow)
        if ema_dist < atr * 0.3:
            score += 15
            details.append("proximity✓")
        else:
            details.append("proximity✗")

        # 6. Bounce confirmation
        if len(closes) >= 2:
            bounce = (htf_dir == "long" and closes[-1] > closes[-2]) or \
                     (htf_dir == "short" and closes[-1] < closes[-2])
            if bounce:
                score += 15
                details.append("bounce✓")
            else:
                details.append("bounce✗")

        grade = self.grade_from_score_100(score)
        summary = f"Trend Rider: {score:.0f}% — {', '.join(details)}"
        return score, grade, summary

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
        if len(closes) < self.slow_ema + 10:
            return None

        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_fast_prev = calculate_ema(closes[:-1], self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        ema_slow_prev = calculate_ema(closes[:-1], self.slow_ema)
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)

        last_close = closes[-1]
        prev_close = closes[-2]
        prev2_close = closes[-3] if len(closes) >= 3 else prev_close

        # ── TRENDING MARKET FILTER ───────────────────────────────
        # When used standalone (not via Conductor), ADX>20 ensures
        # we only enter in trending markets. When Conductor routes us,
        # market_regime already handles this (this acts as fallback).
        adx = gates.get("adx", 25)
        if gates.get("market_regime") is None:
            # Standalone mode — apply our own regime filter
            if adx is not None and adx < 20:
                return None  # Market not trending — skip

        # Must have a strong HTF trend
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_strength = float(gates.get("htf_strength", 0))

        if htf_dir == "neutral" or htf_strength < 0.25:
            return None

        # ── EMA CROSSOVER CONFIRMATION ───────────────────────────
        # Require that EMA(8) is on the correct side of EMA(21)
        # This confirms the trend is established, not just starting
        ema_aligned_bull = ema_fast > ema_slow
        ema_aligned_bear = ema_fast < ema_slow

        # RSI must be between 25-75 (filters only extreme exhaustion)
        if rsi < 25 or rsi > 75:
            return None

        # Distance from slow EMA
        ema_dist = abs(last_close - ema_slow)
        proximity_threshold = atr * 2.0  # Within 2.0 ATR of slow EMA

        # ── BOUNCE CONFIRMATION ──────────────────────────────────
        # Require EITHER:
        #   A) 2 consecutive candles closing in the trend direction, OR
        #   B) RSI divergence (price makes new extreme but RSI doesn't)
        # This prevents trigger-happy entries on single-candle noise.
        two_bull_candles = last_close > prev_close and prev_close > prev2_close
        two_bear_candles = last_close < prev_close and prev_close < prev2_close

        # RSI divergence: compare last 2 swing extremes
        # Bullish div: price makes lower low but RSI makes higher low
        # Bearish div: price makes higher high but RSI makes lower high
        rsi_prev = calculate_rsi(closes[:-1], self.rsi_period)
        rsi_prev2 = calculate_rsi(closes[:-2], self.rsi_period) if len(closes) > self.rsi_period + 2 else rsi_prev
        bullish_rsi_div = (last_close < closes[-3] and rsi > rsi_prev2) if len(closes) >= 3 else False
        bearish_rsi_div = (last_close > closes[-3] and rsi < rsi_prev2) if len(closes) >= 3 else False

        confirmed_bull_bounce = two_bull_candles or bullish_rsi_div
        confirmed_bear_bounce = two_bear_candles or bearish_rsi_div

        # ── DIAGNOSTIC: log why trend_rider returns None ─────────
        logger.info(
            f"[TREND-RIDER] {snapshot.symbol}: htf_dir={htf_dir} str={htf_strength:.2f} "
            f"ema_bull={ema_aligned_bull} ema_bear={ema_aligned_bear} "
            f"close={last_close:.5f} ema21={ema_slow:.5f} "
            f"dist={ema_dist:.5f} thresh={proximity_threshold:.5f} "
            f"rsi={rsi:.1f} bounce_bull={confirmed_bull_bounce} bounce_bear={confirmed_bear_bounce} "
            f"(2candle_up={two_bull_candles} 2candle_dn={two_bear_candles} "
            f"rsi_div_bull={bullish_rsi_div} rsi_div_bear={bearish_rsi_div})"
        )

        # ── BULLISH PULLBACK ─────────────────────────────────────
        if htf_dir == "long" and ema_aligned_bull:
            # Price pulled back to EMA(21) and bouncing
            touched_ema = ema_dist < proximity_threshold or last_close <= ema_slow

            if touched_ema and confirmed_bull_bounce and last_close > ema_slow:
                # Find swing low for stop
                recent_lows = [c.low for c in snapshot.candles[-10:]]
                swing_low = min(recent_lows)
                is_jpy = "JPY" in snapshot.symbol.upper()
                min_sl_dist = 15 * (0.01 if is_jpy else 0.0001)  # 15 pip floor
                stop_dist = max(last_close - swing_low, atr * 1.5, min_sl_dist)
                stop_loss = last_close - stop_dist
                take_profit = last_close + (stop_dist * 2.5)  # 2.5R target (Conductor trail may exit earlier)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=(
                        f"Trend Rider Long: EMA pullback "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f}, "
                        f"HTF={htf_strength:.2f})"
                    ),
                    invalidation_conditions=(
                        f"Close below swing low {swing_low:.5f}"
                    ),
                    management_instructions=(
                        "Target 2.5R. Trail stop to EMA21 once 1R in profit."
                    ),
                    notes="EMA pullback — confirmed uptrend",
                    urgency="medium",
                )

        # ── BEARISH PULLBACK ─────────────────────────────────────
        if htf_dir == "short" and ema_aligned_bear:
            touched_ema = ema_dist < proximity_threshold or last_close >= ema_slow

            if touched_ema and confirmed_bear_bounce and last_close < ema_slow:
                recent_highs = [c.high for c in snapshot.candles[-10:]]
                swing_high = max(recent_highs)
                is_jpy = "JPY" in snapshot.symbol.upper()
                min_sl_dist = 15 * (0.01 if is_jpy else 0.0001)  # 15 pip floor
                stop_dist = max(swing_high - last_close, atr * 1.5, min_sl_dist)
                stop_loss = last_close + stop_dist
                take_profit = last_close - (stop_dist * 2.5)  # 2.5R target (Conductor trail may exit earlier)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=(
                        f"Trend Rider Short: EMA pullback "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f}, "
                        f"HTF={htf_strength:.2f})"
                    ),
                    invalidation_conditions=(
                        f"Close above swing high {swing_high:.5f}"
                    ),
                    management_instructions=(
                        "Target 2.5R. Trail stop to EMA21 once 1R in profit."
                    ),
                    notes="EMA pullback — confirmed downtrend",
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
        """Exit on reverse EMA crossover or trail stop."""
        if not snapshot.candles or len(snapshot.candles) < self.slow_ema + 2:
            return None

        closes = [c.close for c in snapshot.candles]
        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        direction = open_position.get("direction")

        # Check if the trade is currently in profit
        entry_price = float(open_position.get("entry_price", 0))
        current_price = closes[-1]
        is_winning = (
            (direction == "long" and current_price > entry_price) or
            (direction == "short" and current_price < entry_price)
        )

        # Reverse EMA crossover = trend over
        # Require 2 consecutive candles with EMA crossed to avoid
        # exiting on single-candle noise. This applies to ALL trades —
        # small losses near breakeven often recover on the next candle.
        ema_cross_long_exit = direction == "long" and ema_fast < ema_slow
        ema_cross_short_exit = direction == "short" and ema_fast > ema_slow

        if ema_cross_long_exit or ema_cross_short_exit:
            # USER OVERRIDE: Disabled EMA Cross exits to let Guillotine/SAR
            # run without interference from rapid $65 spread whipsaws.
            pass

        # Breakeven trail management
        entry_price = float(open_position["entry_price"])
        current_price = closes[-1]
        current_stop = float(open_position.get("stop_price") or 0.0)
        initial_risk = abs(entry_price - current_stop)

        if initial_risk > 0:
            profit_dist = (
                (current_price - entry_price)
                if direction == "long"
                else (entry_price - current_price)
            )
            r_multiple = profit_dist / initial_risk

            # Move stop to breakeven at 1R
            if direction == "long" and current_stop < entry_price and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="management", action="hold",
                    stop_loss=entry_price,
                    notes="[MANAGEMENT] Trend Rider: stop → BREAKEVEN (1R)"
                )
            if direction == "short" and current_stop > entry_price and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="management", action="hold",
                    stop_loss=entry_price,
                    notes="[MANAGEMENT] Trend Rider: stop → BREAKEVEN (1R)"
                )

        return None
