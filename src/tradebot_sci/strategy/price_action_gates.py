from __future__ import annotations

from typing import List, Optional


def _get_candles(snapshot) -> List:
    """Extract candles from snapshot, handling various formats."""
    candles = getattr(snapshot, 'candles', [])
    if candles is None:
        return []
    return list(candles)


def _level_tolerance(level: float, candles: List) -> float:
    """Return a price distance that defines 'near' a swing level.

    Uses a small percentage of the level (0.02 %), floored by a fraction of
    the recent 14-bar ATR when enough candles are available.  This keeps the
    gate tight for forex (a few pips) instead of the old 0.1 % (10+ pips).
    """
    pct = level * 0.0002  # 0.02 %
    if len(candles) >= 15:
        try:
            from tradebot_sci.strategy.icc_signals import calculate_atr
            atr = calculate_atr(candles, period=14)
            if atr and atr > 0:
                return max(pct, atr * 0.25)
        except Exception:
            pass
    return pct


def _find_swing_lows(candles: List, lookback: int) -> List[float]:
    """Find swing lows (local minima) in the lookback period."""
    if len(candles) < 3:
        return []
    lows = [c.low for c in candles[-lookback:]]
    swing_lows = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            swing_lows.append(lows[i])
    if len(lows) >= 2:
        if lows[-1] < lows[-2]:
            swing_lows.append(lows[-1])
        if lows[0] < lows[1]:
            swing_lows.append(lows[0])
    return swing_lows if swing_lows else [min(lows)]


def _find_swing_highs(candles: List, lookback: int) -> List[float]:
    """Find swing highs (local maxima) in the lookback period."""
    if len(candles) < 3:
        return []
    highs = [c.high for c in candles[-lookback:]]
    swing_highs = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            swing_highs.append(highs[i])
    if len(highs) >= 2:
        if highs[-1] > highs[-2]:
            swing_highs.append(highs[-1])
        if highs[0] > highs[1]:
            swing_highs.append(highs[0])
    return swing_highs if swing_highs else [max(highs)]


def _get_recent_swing_low(candles: List, lookback: int) -> Optional[float]:
    """Get the most recent significant swing low."""
    swing_lows = _find_swing_lows(candles, lookback)
    return min(swing_lows) if swing_lows else None


def _get_recent_swing_high(candles: List, lookback: int) -> Optional[float]:
    """Get the most recent significant swing high."""
    swing_highs = _find_swing_highs(candles, lookback)
    return max(swing_highs) if swing_highs else None


def is_support_bounce(snapshot, lookback: int = 20) -> bool:
    """Price hits a recent swing low and bounces (closes back above it)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    swing_low = _get_recent_swing_low(candles, lookback)
    if swing_low is None:
        return False
    last = candles[-1]
    tol = _level_tolerance(swing_low, candles)
    # Price must actually test the level (wick touch or slight pierce) and
    # the body must close back above it — a close far below is not a bounce.
    return last.low <= swing_low + tol and last.close > swing_low + tol * 0.2


def is_resistance_rejection(snapshot, lookback: int = 20) -> bool:
    """Price hits a recent swing high and rejects (closes back below it)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    swing_high = _get_recent_swing_high(candles, lookback)
    if swing_high is None:
        return False
    last = candles[-1]
    tol = _level_tolerance(swing_high, candles)
    return last.high >= swing_high - tol and last.close < swing_high - tol * 0.2


def break_above_structure(snapshot, lookback: int = 20) -> bool:
    """Price closed above the recent swing high (breakout)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    prior_candles = candles[-lookback:-1]
    if not prior_candles:
        return False
    swing_high = max(c.high for c in prior_candles)
    return candles[-1].close > swing_high


def break_below_structure(snapshot, lookback: int = 20) -> bool:
    """Price closed below the recent swing low (breakdown)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    prior_candles = candles[-lookback:-1]
    if not prior_candles:
        return False
    swing_low = min(c.low for c in prior_candles)
    return candles[-1].close < swing_low


def pullback_to_broken_level(snapshot, lookback: int = 20, recent: int = 5) -> bool:
    """Price pulled back to a level that was recently broken."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + recent:
        return False
    prior_candles = candles[-lookback:-recent]
    if not prior_candles:
        return False
    swing_high = max(c.high for c in prior_candles)
    swing_low = min(c.low for c in prior_candles)
    
    # Check if price broke the level recently
    recent_candles = candles[-recent:-1]
    broken_high = any(c.close > swing_high for c in recent_candles)
    broken_low = any(c.close < swing_low for c in recent_candles)
    
    if not (broken_high or broken_low):
        return False
    
    last = candles[-1]
    # Price pulled back near the broken level
    tol = _level_tolerance(swing_high, candles)
    near_high = abs(last.close - swing_high) < tol
    near_low = abs(last.close - swing_low) < tol

    return near_high or near_low


def higher_highs_and_lows(snapshot, lookback: int = 20) -> bool:
    """Recent swing structure shows higher highs and higher lows (uptrend)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    window = candles[-lookback:]
    mid = len(window) // 2
    first_half = window[:mid]
    second_half = window[mid:]

    if not first_half or not second_half:
        return False

    first_highs = [c.high for c in first_half]
    first_lows = [c.low for c in first_half]
    second_highs = [c.high for c in second_half]
    second_lows = [c.low for c in second_half]

    return max(second_highs) > max(first_highs) and min(second_lows) > min(first_lows)


def lower_highs_and_lows(snapshot, lookback: int = 20) -> bool:
    """Recent swing structure shows lower highs and lower lows (downtrend)."""
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 1:
        return False
    window = candles[-lookback:]
    mid = len(window) // 2
    first_half = window[:mid]
    second_half = window[mid:]

    if not first_half or not second_half:
        return False

    first_highs = [c.high for c in first_half]
    first_lows = [c.low for c in first_half]
    second_highs = [c.high for c in second_half]
    second_lows = [c.low for c in second_half]

    return max(second_highs) < max(first_highs) and min(second_lows) < min(first_lows)


def engulfing_at_level(snapshot, lookback: int = 10) -> tuple[bool, bool]:
    """
    Bullish or bearish engulfing candle at a recent swing level.
    Returns (bullish_engulfing, bearish_engulfing).
    """
    candles = _get_candles(snapshot)
    if len(candles) < lookback + 2:
        return False, False
    
    swing_low = _get_recent_swing_low(candles, lookback)
    swing_high = _get_recent_swing_high(candles, lookback)
    
    prev = candles[-2]
    curr = candles[-1]
    
    # Bullish engulfing: current candle completely engulfs previous
    bullish = (curr.close > curr.open and prev.close < prev.open and
               curr.close > prev.open and curr.open < prev.close)
    
    # Bearish engulfing
    bearish = (curr.close < curr.open and prev.close > prev.open and
               curr.close < prev.open and curr.open > prev.close)
    
    if not (bullish or bearish):
        return False, False
    
    # Check if it's at a key level
    tol = _level_tolerance(swing_high, candles) if swing_high else 0.0
    at_support = swing_low is not None and abs(curr.low - swing_low) <= tol
    at_resistance = swing_high is not None and abs(curr.high - swing_high) <= tol

    return (bullish and at_support), (bearish and at_resistance)


# Aliases for drop-in compatibility with indicator-based naming
is_oversold = is_support_bounce
is_overbought = is_resistance_rejection
bollinger_lower_band_touch = break_below_structure
bollinger_upper_band_touch = break_above_structure
pullback_to_ema = pullback_to_broken_level
ema_slope_up = higher_highs_and_lows
ema_slope_down = lower_highs_and_lows
hook_confirmation = engulfing_at_level
