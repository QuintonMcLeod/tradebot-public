from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Tuple

from tradebot_sci.market.models import Candle, TrendState
from tradebot_sci.market.swing_analysis import swing_points, swing_points_close
from tradebot_sci.market.trend_enums import TrendDirection

logger = logging.getLogger(__name__)


@dataclass
class MultiResolutionTrend:
    """Result of multi-resolution trend analysis."""
    direction: TrendDirection
    strength: float
    consistency_score: float  # 0.0 to 1.0 - how many lookbacks agree
    is_choppy: bool  # True if consistency < 0.5 (majority rule)
    lookback_results: dict  # {lookback: direction} for debugging
    trend_state: TrendState  # The underlying TrendState for compatibility


def infer_trend_multi_resolution(
    candles: list[Candle],
    *,
    lookback_range: Tuple[int, int] = (2, 5),  # Test lookbacks 2, 3, 4, 5
    window: int = 120,
    min_swings: int = 2,
    strength_floor: float = 0.3,
) -> MultiResolutionTrend:
    """Analyze trend across multiple swing lookback values to detect chop.

    This function checks trend direction at multiple
    resolutions (lookback 2-5). If the trend flips depending on which lookback
    you use, the market is choppy and we should NOT trade.

    Majority Rule:
    - If >50% of lookbacks agree on direction → that's the trend
    - If 50/50 split → NEUTRAL (bearish bias, stay out)
    - Consistency score = (agreeing lookbacks) / (total lookbacks)

    Args:
        candles: Price candles to analyze
        lookback_range: (min_lookback, max_lookback) range to test
        window: How many candles to analyze
        min_swings: Minimum swings required for trend detection
        strength_floor: Minimum strength to confirm trend

    Returns:
        MultiResolutionTrend with consensus direction and chop detection
    """
    if not candles:
        return MultiResolutionTrend(
            direction=TrendDirection.NEUTRAL,
            strength=0.0,
            consistency_score=0.0,
            is_choppy=True,
            lookback_results={},
            trend_state=TrendState(direction=TrendDirection.NEUTRAL, strength=0.0),
        )

    lookback_min, lookback_max = lookback_range
    lookback_results = {}
    directions = []
    strengths = []

    # Test each lookback value
    for lookback in range(lookback_min, lookback_max + 1):
        trend = infer_trend_from_swings(
            candles,
            swing_lookback=lookback,
            window=window,
            min_swings=min_swings,
            strength_floor=strength_floor,
        )
        lookback_results[lookback] = trend.direction
        directions.append(trend.direction)
        strengths.append(trend.strength)

    # Count votes for each direction
    long_votes = sum(1 for d in directions if d == TrendDirection.LONG)
    short_votes = sum(1 for d in directions if d == TrendDirection.SHORT)
    neutral_votes = sum(1 for d in directions if d == TrendDirection.NEUTRAL)
    total_votes = len(directions)

    # Debug logging
    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[MULTI-RES] Lookback results: {lookback_results}", file=sys.stderr, flush=True)
        print(f"[MULTI-RES] Votes: LONG={long_votes}, SHORT={short_votes}, NEUTRAL={neutral_votes}", file=sys.stderr, flush=True)

    # Majority rule with 50/50 = bearish (stay out)
    # We need STRICT majority (>50%) to confirm a trend
    majority_threshold = total_votes / 2.0

    if long_votes > majority_threshold:
        consensus_direction = TrendDirection.LONG
        consistency_score = long_votes / total_votes
    elif short_votes > majority_threshold:
        consensus_direction = TrendDirection.SHORT
        consistency_score = short_votes / total_votes
    else:
        # No clear majority - market is choppy, stay NEUTRAL
        consensus_direction = TrendDirection.NEUTRAL
        # Consistency is how close we are to agreement (max of any direction)
        consistency_score = max(long_votes, short_votes, neutral_votes) / total_votes

    # Average strength from all lookbacks
    avg_strength = sum(strengths) / len(strengths) if strengths else 0.0

    # Choppy if no majority (consistency <= 0.5)
    is_choppy = consistency_score <= 0.5

    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[MULTI-RES] Consensus: {consensus_direction}, Consistency: {consistency_score:.2f}, Choppy: {is_choppy}", file=sys.stderr, flush=True)

    # Build a TrendState for compatibility with existing code
    # Use the middle lookback (3) as the "canonical" result for swing data
    middle_lookback = (lookback_min + lookback_max) // 2
    canonical_trend = infer_trend_from_swings(
        candles,
        swing_lookback=middle_lookback,
        window=window,
        min_swings=min_swings,
        strength_floor=strength_floor,
    )

    # Override direction with consensus
    trend_state = TrendState(
        direction=consensus_direction,
        strength=avg_strength if not is_choppy else 0.0,
        last_confirmed_swings=canonical_trend.last_confirmed_swings,
        key_levels=canonical_trend.key_levels,
    )

    return MultiResolutionTrend(
        direction=consensus_direction,
        strength=avg_strength,
        consistency_score=consistency_score,
        is_choppy=is_choppy,
        lookback_results=lookback_results,
        trend_state=trend_state,
    )


def infer_trend_from_swings(
    candles: list[Candle],
    *,
    swing_lookback: int = 2,
    window: int = 120,
    min_swings: int = 2,  # Lowered from 3 to 2 for realistic trend detection
    strength_floor: float = 0.3,  # Lowered from 0.5 to 0.3 to detect real trends
) -> TrendState:
    """Classify trend using HH/HL vs LH/LL swing structure."""
    if not candles:
        return TrendState(direction=TrendDirection.NEUTRAL, strength=0.0)
    recent = candles[-window:] if window > 0 else candles
    offset = len(candles) - len(recent)
    swing_highs, swing_lows = swing_points(recent, lookback=swing_lookback)

    # DEBUG: Log swing detection (uses module-level imports)
    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[TREND-DEBUG] Called infer_trend_from_swings: {len(swing_highs)} highs, {len(swing_lows)} lows, min={min_swings}", file=sys.stderr, flush=True)
        msg = f"[TREND] Detected {len(swing_highs)} highs, {len(swing_lows)} lows (need {min_swings} each)"
        logger.info(msg)
        print(msg, file=sys.stderr, flush=True)

    # Allow asymmetric swing detection for strong trends
    # During strong rally: many higher highs, few/no lower lows (still bullish!)
    # During strong dump: many lower lows, few/no higher highs (still bearish!)
    has_enough_highs = len(swing_highs) >= min_swings
    has_enough_lows = len(swing_lows) >= min_swings

    if not has_enough_highs and not has_enough_lows:
        # Need at least ONE type of swing
        return TrendState(
            direction=TrendDirection.NEUTRAL,
            strength=0.0,
            last_confirmed_swings=_collect_swings(recent, swing_highs, swing_lows, offset, min_swings),
            key_levels=_key_levels(recent, swing_highs, swing_lows),
        )

    highs = [recent[i].high for i in swing_highs]
    lows = [recent[i].low for i in swing_lows]

    # DEBUG: Check if swings are in chronological order
    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[TREND-DEBUG] Swing high indices: {swing_highs}", file=sys.stderr, flush=True)
        print(f"[TREND-DEBUG] Swing low indices: {swing_lows}", file=sys.stderr, flush=True)
        print(f"[TREND-DEBUG] All highs (chronological): {highs}", file=sys.stderr, flush=True)
        print(f"[TREND-DEBUG] All lows (chronological): {lows}", file=sys.stderr, flush=True)

    # Get available swings (might be asymmetric during strong trends)
    last_highs = highs[-min_swings:] if len(highs) >= min_swings else highs
    last_lows = lows[-min_swings:] if len(lows) >= min_swings else lows

    # Allow trends with minor pullbacks (realistic market conditions)
    # 75% threshold = allows 1 pullback in 4 swings
    # For asymmetric swings (strong trend), allow trend detection with just one type

    # DEBUG: Print actual swing values
    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[TREND-DEBUG] Swing highs: {last_highs}", file=sys.stderr, flush=True)
        print(f"[TREND-DEBUG] Swing lows: {last_lows}", file=sys.stderr, flush=True)

    if has_enough_highs and has_enough_lows:
        # Both types available - weight the more numerous swing type more heavily
        highs_rising = _mostly_monotonic(last_highs, rising=True, threshold=0.75)
        lows_rising = _mostly_monotonic(last_lows, rising=True, threshold=0.75)
        highs_falling = _mostly_monotonic(last_highs, rising=False, threshold=0.75)
        lows_falling = _mostly_monotonic(last_lows, rising=False, threshold=0.75)

        if os.getenv("DEBUG_TRENDS") == "1":
            print(f"[TREND-DEBUG] highs_rising={highs_rising}, lows_rising={lows_rising}", file=sys.stderr, flush=True)
            print(f"[TREND-DEBUG] highs_falling={highs_falling}, lows_falling={lows_falling}", file=sys.stderr, flush=True)

        # During strong trends, one swing type dominates (more swing highs in uptrend, more lows in downtrend)
        # If asymmetric (e.g., 3 highs vs 2 lows), prioritize the dominant swing type
        swing_count_ratio = len(swing_highs) / max(1, len(swing_lows))

        if os.getenv("DEBUG_TRENDS") == "1":
            print(f"[TREND-DEBUG] swing_count_ratio={swing_count_ratio:.2f} ({len(swing_highs)}:{len(swing_lows)})", file=sys.stderr, flush=True)

        if swing_count_ratio > 1.3:  # Significantly more highs (e.g., 3:2 = 1.5)
            # Strong rally: many swing highs, fewer lows → prioritize highs
            if os.getenv("DEBUG_TRENDS") == "1":
                print(f"[TREND-DEBUG] Using RALLY logic (more highs)", file=sys.stderr, flush=True)
            bullish = highs_rising  # Highs must be rising
            bearish = highs_falling and lows_falling  # Both must fall for bearish
        elif swing_count_ratio < 0.77:  # Significantly more lows (e.g., 2:3 = 0.67)
            # Strong selloff: many swing lows, fewer highs → prioritize lows
            if os.getenv("DEBUG_TRENDS") == "1":
                print(f"[TREND-DEBUG] Using SELLOFF logic (more lows)", file=sys.stderr, flush=True)
            bullish = highs_rising and lows_rising  # Both must rise for bullish
            bearish = lows_falling  # Lows must be falling
        else:
            # Balanced swings: require both to align
            if os.getenv("DEBUG_TRENDS") == "1":
                print(f"[TREND-DEBUG] Using BALANCED logic (similar counts)", file=sys.stderr, flush=True)
            bullish = highs_rising and lows_rising
            bearish = highs_falling and lows_falling
    elif has_enough_highs:
        # Only highs available - strong trending market (few pullbacks)
        bullish = _mostly_monotonic(last_highs, rising=True, threshold=0.75)
        bearish = _mostly_monotonic(last_highs, rising=False, threshold=0.75)
    elif has_enough_lows:
        # Only lows available - use lows for trend
        bullish = _mostly_monotonic(last_lows, rising=True, threshold=0.75)
        bearish = _mostly_monotonic(last_lows, rising=False, threshold=0.75)
    else:
        # Should not reach here (handled above)
        bullish = False
        bearish = False

    if os.getenv("DEBUG_TRENDS") == "1":
        print(f"[TREND-DEBUG] Final: bullish={bullish}, bearish={bearish}", file=sys.stderr, flush=True)

    if not bullish and not bearish:
        return TrendState(
            direction=TrendDirection.NEUTRAL,
            strength=0.0,
            last_confirmed_swings=_collect_swings(recent, swing_highs, swing_lows, offset, min_swings),
            key_levels=_key_levels(recent, swing_highs, swing_lows),
        )

    strength = _structure_strength(last_highs, last_lows)
    if strength < strength_floor:
        return TrendState(
            direction=TrendDirection.NEUTRAL,
            strength=strength,
            last_confirmed_swings=_collect_swings(recent, swing_highs, swing_lows, offset, min_swings),
            key_levels=_key_levels(recent, swing_highs, swing_lows),
        )

    direction = TrendDirection.LONG if bullish else TrendDirection.SHORT

    # Live Structure Break Check:
    # If the trend is Short, but price has ALREADY recovered above the last Swing High,
    # the Short trend is effectively broken (Live BOS). Do not wait for a new Swing High to form.
    # We downgrade to NEUTRAL to unblock gates (e.g. Venue Gate or Alignment Gate).
    if direction == TrendDirection.SHORT and last_highs:
        current_close = float(candles[-1].close)
        last_swing_high = float(last_highs[-1])
        if current_close > last_swing_high:
            if os.getenv("DEBUG_TRENDS") == "1":
                print(
                    f"[TREND-DEBUG] Live BOS Detected! Price {current_close} > Last High {last_swing_high}. "
                    "Downgrading SHORT -> NEUTRAL.",
                    file=sys.stderr,
                    flush=True,
                )
            direction = TrendDirection.NEUTRAL
            strength = 0.1

            # BULLISH UPGRADE: Check if we have a valid Higher Low (Continuation)
            # If so, this isn't just a break, it's a trend change to LONG.
            if len(last_lows) >= 2:
                recent_low = last_lows[-1]
                prior_low = last_lows[-2]
                if recent_low > prior_low:
                    if os.getenv("DEBUG_TRENDS") == "1":
                        print(
                            f"[TREND-DEBUG] Bullish Upgrade! Higher Low {recent_low} > {prior_low}. "
                            "Upgrading NEUTRAL -> LONG.",
                            file=sys.stderr,
                            flush=True,
                        )
                    direction = TrendDirection.LONG
                    strength = 1.0  # Strong momentum

    if direction == TrendDirection.LONG and last_lows:
        current_close = float(candles[-1].close)
        last_swing_low = float(last_lows[-1])
        if current_close < last_swing_low:
            if os.getenv("DEBUG_TRENDS") == "1":
                print(f"[TREND-DEBUG] Live BOS Detected! Price {current_close} < Last Low {last_swing_low}. Downgrading LONG -> NEUTRAL.", file=sys.stderr, flush=True)
            direction = TrendDirection.NEUTRAL
            strength = 0.1

    return TrendState(
        direction=direction,
        strength=strength,
        last_confirmed_swings=_collect_swings(recent, swing_highs, swing_lows, offset, min_swings),
        key_levels=_key_levels(recent, swing_highs, swing_lows),
    )


def swing_progress(
    candles: list[Candle],
    *,
    swing_lookback: int = 2,
    min_swings: int = 3,
) -> float:
    """Returns a 0-1 progress score for swing structure even when trend is neutral."""
    if not candles:
        return 0.0
    swing_highs, swing_lows = swing_points(candles, lookback=swing_lookback)
    swing_count = min(len(swing_highs), len(swing_lows))
    if swing_count <= 0 or min_swings <= 0:
        return 0.0
    ratio = min(1.0, swing_count / float(min_swings))
    if swing_count >= 2:
        highs = [candles[i].high for i in swing_highs[-min(min_swings, len(swing_highs)) :]]
        lows = [candles[i].low for i in swing_lows[-min(min_swings, len(swing_lows)) :]]
        strength = _structure_strength(highs, lows)
    else:
        strength = 0.0
    return min(1.0, 0.6 * ratio + 0.4 * strength)


def _monotonic(values: list[float], *, rising: bool) -> bool:
    if len(values) < 2:
        return False
    cmp = (lambda a, b: a > b) if rising else (lambda a, b: a < b)
    return all(cmp(values[i], values[i - 1]) for i in range(1, len(values)))


def _mostly_monotonic(values: list[float], *, rising: bool, threshold: float = 0.75) -> bool:
    """Return True if at least {threshold}% of transitions are in the correct direction.

    This allows minor pullbacks in trends (realistic market conditions) while still
    detecting clear directional bias.

    Example: [100, 105, 103, 110, 115] with threshold=0.75
    - Transitions: 100→105 (up), 105→103 (down), 103→110 (up), 110→115 (up)
    - Correct: 3 out of 4 = 75% → True (allows the one pullback)
    """
    if len(values) < 2:
        return False
    cmp = (lambda a, b: a > b) if rising else (lambda a, b: a < b)
    correct = sum(1 for i in range(1, len(values)) if cmp(values[i], values[i - 1]))
    total = len(values) - 1
    return (correct / total) >= threshold


def _structure_strength(highs: list[float], lows: list[float]) -> float:
    transitions = max(1, (len(highs) - 1) + (len(lows) - 1))
    up_highs = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    down_highs = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    up_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
    down_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])
    consistent = max(up_highs + up_lows, down_highs + down_lows)
    return min(1.0, consistent / transitions)


def _collect_swings(
    candles: list[Candle],
    swing_highs: list[int],
    swing_lows: list[int],
    offset: int,
    limit: int,
) -> list[dict]:
    swings: list[dict] = []
    for idx in swing_highs[-limit:]:
        swings.append({"type": "high", "index": idx + offset, "price": float(candles[idx].high)})
    for idx in swing_lows[-limit:]:
        swings.append({"type": "low", "index": idx + offset, "price": float(candles[idx].low)})
    return swings


def _key_levels(
    candles: list[Candle],
    swing_highs: list[int],
    swing_lows: list[int],
) -> dict | None:
    if not swing_highs or not swing_lows:
        return None
    last_high = float(candles[swing_highs[-1]].high)
    last_low = float(candles[swing_lows[-1]].low)
    prior_high = float(candles[swing_highs[-2]].high) if len(swing_highs) > 1 else last_high
    prior_low = float(candles[swing_lows[-2]].low) if len(swing_lows) > 1 else last_low
    return {
        "last_swing_high": last_high,
        "last_swing_low": last_low,
        "prior_swing_high": prior_high,
        "prior_swing_low": prior_low,
    }


# Swing detection functions moved to tradebot_sci.market.swing_analysis
# for shared use across modules
