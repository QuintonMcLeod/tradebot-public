"""
Momentum Rider helpers — pure, stateless utilities for trend and structure.

These functions are intentionally simple and have no config/UI surface. They are
imported by ForexMomentumRiderStrategy to keep the strategy file focused on
entry/exit logic.
"""
from __future__ import annotations
from typing import List, Tuple, Optional

from tradebot_sci.market.models import Candle
from tradebot_sci.market.indicators import calculate_ema


def _closes(candles: List[Candle]) -> List[float]:
    return [c.close for c in candles]


def ema_series(closes: List[float], period: int) -> List[float]:
    """Return an EMA series aligned with the input closes.

    The first `period` values are SMAs; subsequent values are EMAs.
    """
    if not closes or period <= 0:
        return []
    if len(closes) < period:
        # Not enough data; use a simple SMA for whatever we have
        sma = sum(closes) / len(closes) if closes else 0.0
        return [sma] * len(closes)

    alpha = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    result = []
    for i, price in enumerate(closes):
        if i < period:
            # Use SMA up to the seed window for stable early values
            ema = sum(closes[: i + 1]) / (i + 1)
        else:
            ema = price * alpha + ema * (1 - alpha)
        result.append(ema)
    return result


def fast_trend_state(
    candles: List[Candle],
    fast_period: int = 8,
    slow_period: int = 21,
    slope_lookback: int = 2,
) -> str:
    """Return 'long', 'short', or 'neutral' based on EMA ribbon alignment and slope.

    Trend requires:
      - price on the correct side of the slow EMA
      - fast EMA aligned above/below slow EMA
      - slow EMA has risen/fallen over the last `slope_lookback` bars
    """
    if len(candles) < slow_period + slope_lookback + 1:
        return "neutral"

    closes = _closes(candles)
    fast_ema = ema_series(closes, fast_period)
    slow_ema = ema_series(closes, slow_period)

    if not fast_ema or not slow_ema:
        return "neutral"

    last_idx = len(closes) - 1
    price = closes[last_idx]
    fast_now = fast_ema[last_idx]
    slow_now = slow_ema[last_idx]
    slow_prev = slow_ema[last_idx - slope_lookback]

    if price > slow_now and fast_now > slow_now and slow_now > slow_prev:
        return "long"
    if price < slow_now and fast_now < slow_now and slow_now < slow_prev:
        return "short"
    return "neutral"


def recent_swing_levels(
    candles: List[Candle],
    lookback: int = 5,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (swing_high, swing_low) over the most recent `lookback` completed candles.

    Excludes the current/rightmost candle so the swing is already established.
    """
    if len(candles) < lookback + 1:
        return None, None

    recent = candles[-(lookback + 1) : -1]
    swing_high = max(c.high for c in recent)
    swing_low = min(c.low for c in recent)
    return swing_high, swing_low


def is_bounce_candle(
    candle: Candle,
    direction: str,
    threshold: float = 0.5,
) -> bool:
    """True if `candle` closes in the outer `threshold` fraction of its range
    in the direction of the trend.

    For a long setup, close must be in the upper `threshold` of the bar.
    For a short setup, close must be in the lower `threshold` of the bar.
    """
    rng = candle.high - candle.low
    if rng <= 0:
        return False

    if direction == "long":
        upper_zone = candle.high - threshold * rng
        return candle.close >= upper_zone
    if direction == "short":
        lower_zone = candle.low + threshold * rng
        return candle.close <= lower_zone
    return False


def price_touched_ema(
    candles: List[Candle],
    period: int,
    direction: str,
    tolerance_atr_mult: float = 0.0,
    atr: Optional[float] = None,
) -> bool:
    """True if price in the most recent candle touched or crossed the EMA.

    For longs: low <= EMA (price pulled back to or below the EMA).
    For shorts: high >= EMA (price pulled back to or above the EMA).
    A positive tolerance_atr_mult allows a near-miss to count.
    """
    if len(candles) < period:
        return False

    ema = calculate_ema(_closes(candles), period)
    if ema is None:
        return False

    last = candles[-1]
    tolerance = (atr or 0.0) * tolerance_atr_mult

    if direction == "long":
        return last.low <= ema + tolerance
    if direction == "short":
        return last.high >= ema - tolerance
    return False
