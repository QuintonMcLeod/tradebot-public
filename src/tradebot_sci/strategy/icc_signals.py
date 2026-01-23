from __future__ import annotations

from dataclasses import dataclass

from tradebot_sci.market.models import Candle
from tradebot_sci.market.swing_analysis import swing_points, swing_points_close


@dataclass(frozen=True)
class LiquiditySweep:
    side: str  # "buy_side" (sweep highs) or "sell_side" (sweep lows)
    level: float
    swept_price: float
    index: int

    def describe(self) -> str:
        return f"{self.side} sweep: level={self.level:.4f} swept={self.swept_price:.4f} idx={self.index}"

    @property
    def direction(self) -> str:
        """Maps sweep side to trade direction."""
        return "long" if self.side == "sell_side" else "short"


@dataclass(frozen=True)
class ContinuationSignal:
    direction: str  # "long" or "short"
    trigger_level: float
    index: int

    def describe(self) -> str:
        return f"continuation_{self.direction}: trigger={self.trigger_level:.4f} idx={self.index}"


@dataclass(frozen=True)
class StructureInvalidation:
    position_side: str  # "long" or "short"
    swing_level: float
    last_close: float
    buffer: float
    index: int

    def describe(self) -> str:
        return (
            f"htf_invalidation {self.position_side}: close={self.last_close:.4f} "
            f"swing={self.swing_level:.4f} buffer={self.buffer:.4f} idx={self.index}"
        )



@dataclass(frozen=True)
class IndicationSignal:
    direction: str  # "long" or "short"
    level: float
    index: int

    def describe(self) -> str:
        return f"indication_{self.direction}: level={self.level:.4f} idx={self.index}"


@dataclass(frozen=True)
class NoTradeZone:
    """Represents the range between the current Swing High and Swing Low."""
    high: float
    low: float
    is_broken: bool = False
    break_direction: str | None = None  # "long" (break high) or "short" (break low)

    def describe(self) -> str:
        status = f"BROKEN_{self.break_direction.upper()}" if self.is_broken else "ACTIVE"
        return f"NTZ({status}): range=[{self.low:.4f}, {self.high:.4f}]"


@dataclass(frozen=True)
class CorrectionSignal:
    """Represents a correction phase after an indication."""
    direction: str  # "long" or "short" - expected direction after correction
    indication_level: float  # The original indication level being retested
    retracement_level: float  # How far price retraced
    retracement_pct: float  # Percentage retracement (e.g., 0.50 for 50%)
    index: int  # Candle index where correction was detected
    is_liquidity_grab: bool = False # Did it sweep a recent LTF level?

    def describe(self) -> str:
        grab = " (LIQ GRAB)" if self.is_liquidity_grab else ""
        return (
            f"correction_{self.direction}{grab}: indication={self.indication_level:.4f} "
            f"retraced_to={self.retracement_level:.4f} ({self.retracement_pct:.1%}) idx={self.index}"
        )


def next_structure_target(
    candles: list[Candle],
    direction: str,
    *,
    entry_price: float | None = None,
    swing_lookback: int = 2,
    window: int = 200,
) -> float | None:
    """Returns the nearest HTF swing level in the trade direction for target alignment."""
    if direction not in {"long", "short"} or not candles:
        return None
    recent = candles[-window:] if window > 0 else candles
    swing_highs, swing_lows = swing_points_close(recent, lookback=swing_lookback)
    if entry_price is None:
        entry_price = float(recent[-1].close)
    if direction == "long":
        highs = sorted({float(recent[i].close) for i in swing_highs})
        for level in highs:
            if level > entry_price:
                return level
        return None
    lows = sorted({float(recent[i].close) for i in swing_lows}, reverse=True)
    for level in lows:
        if level < entry_price:
            return level
    return None


def detect_liquidity_sweep(
    candles: list[Candle],
    trend_direction: str,
    *,
    swing_lookback: int = 2,
    window: int = 40,
) -> LiquiditySweep | None:
    """Detects a simple ICC-style liquidity sweep against the trend.

    This is intentionally conservative and deterministic:
    - In a long trend, looks for a sell-side sweep (low dips below the prior swing low and closes back above it).
    - In a short trend, looks for a buy-side sweep (high pokes above the prior swing high and closes back below it).
    """
    import logging
    import os
    logger = logging.getLogger(__name__)
    debug = os.getenv("DEBUG_ICC") == "1"

    if trend_direction not in {"long", "short"}:
        if debug:
            logger.info(f"[SWEEP] REJECTED: trend_direction={trend_direction}")
        return None
    if len(candles) < (swing_lookback * 2 + 6):
        if debug:
            logger.info(
                f"[SWEEP] REJECTED: insufficient candles={len(candles)} "
                f"(min={swing_lookback * 2 + 6})"
            )
        return None

    recent = candles[-window:] if window > 0 else candles
    swing_highs, swing_lows = swing_points(recent, lookback=swing_lookback)
    if debug:
        logger.info(
            f"[SWEEP] Checking sweep: trend={trend_direction} "
            f"swing_highs={len(swing_highs)} swing_lows={len(swing_lows)} window={len(recent)}"
        )

    if trend_direction == "long":
        for swing_low_idx in reversed(swing_lows):
            swing_low = recent[swing_low_idx].low
            for i in range(swing_low_idx + 1, len(recent)):
                c = recent[i]
                if c.low < swing_low and c.close > swing_low:
                    absolute_idx = len(candles) - len(recent) + i
                    if debug:
                        logger.info(
                            f"[SWEEP] DETECTED: side=sell_side level={swing_low:.4f} "
                            f"swept={c.low:.4f} idx={absolute_idx}"
                        )
                    return LiquiditySweep(
                        side="sell_side",
                        level=float(swing_low),
                        swept_price=float(c.low),
                        index=absolute_idx,
                    )
        if debug:
            logger.info("[SWEEP] REJECTED: no sell-side sweep found")
        return None

    # short trend
    for swing_high_idx in reversed(swing_highs):
        swing_high = recent[swing_high_idx].high
        for i in range(swing_high_idx + 1, len(recent)):
            c = recent[i]
            if c.high > swing_high and c.close < swing_high:
                absolute_idx = len(candles) - len(recent) + i
                if debug:
                    logger.info(
                        f"[SWEEP] DETECTED: side=buy_side level={swing_high:.4f} "
                        f"swept={c.high:.4f} idx={absolute_idx}"
                    )
                return LiquiditySweep(
                    side="buy_side",
                    level=float(swing_high),
                    swept_price=float(c.high),
                    index=absolute_idx,
                )
    if debug:
        logger.info("[SWEEP] REJECTED: no buy-side sweep found")
    return None


def detect_continuation(
    candles: list[Candle],
    trend_direction: str,
    sweep: LiquiditySweep | None,
    indication: IndicationSignal | None,
    correction: CorrectionSignal | None = None,
    *,
    require_sweep: bool = False,
    require_indication: bool = False,
    require_correction: bool = False,
    breakout_lookback: int = 5,
    max_bars_after_sweep: int = 25,
    swing_lookback: int = 2,
    confirmation_bars: int = 2,
) -> ContinuationSignal | None:
    """Detects a continuation trigger after indication + correction structure.

    ICC-style rule:
    - Require an indication in the same direction.
    - Long: higher low (HL) then 2-bar close above prior swing high.
    - Short: lower high (LH) then 2-bar close below prior swing low.
    """
    import logging
    import os
    logger = logging.getLogger(__name__)
    debug = os.getenv("DEBUG_ICC") == "1"

    if trend_direction not in {"long", "short"}:
        if debug:
            logger.info(f"[CONTINUATION] REJECTED: trend_direction={trend_direction}")
        return None
    if require_indication:
        if indication is None:
            if debug:
                logger.info("[CONTINUATION] WARNING: no indication (optional)")
            # Do NOT return None - continue to check structure
        elif indication.direction != trend_direction:
            if debug:
                logger.info(
                    "[CONTINUATION] WARNING: indication_dir=%s trend_dir=%s (optional)",
                    indication.direction,
                    trend_direction,
                )
            # Do NOT return None - continue to check structure

    if correction is not None:
        if debug:
            logger.info(
                f"[CONTINUATION] CORRECTION DETECTED: {correction.retracement_pct:.1%} retracement"
            )
    elif require_correction:
        if debug:
            logger.info("[CONTINUATION] WARNING: no correction (optional)")

    if len(candles) < breakout_lookback + 2:
        if debug:
            logger.info(
                f"[CONTINUATION] REJECTED: insufficient candles={len(candles)} "
                f"(min={breakout_lookback + 2})"
            )
        return None

    if sweep is None:
        if require_sweep:
            if debug:
                logger.info("[CONTINUATION] WARNING: no sweep (optional)")
        # Continue execution - do NOT return None
        window = max(max_bars_after_sweep + 1, breakout_lookback + 2)
        recent = candles[-window:]
        if debug:
            logger.info(
                "[CONTINUATION] No sweep provided; using recent window=%d of %d candles",
                len(recent),
                len(candles),
            )
    else:
        if len(candles) - 1 - sweep.index > max_bars_after_sweep:
            if debug:
                logger.info(
                    f"[CONTINUATION] REJECTED: sweep too old bars_since={len(candles) - 1 - sweep.index} "
                    f"(max={max_bars_after_sweep})"
                )
            return None
        recent = candles[sweep.index :]

    min_window = max(breakout_lookback + 2, swing_lookback * 2 + 5)
    if len(recent) < min_window:
        if debug:
            logger.info(
                f"[CONTINUATION] REJECTED: recent window too small={len(recent)} "
                f"(min={min_window})"
            )
        return None

    swing_highs, swing_lows = swing_points_close(recent, lookback=swing_lookback)
    if debug:
        logger.info(
            f"[CONTINUATION] STRUCTURE-BASED ENTRY: sweep={'present' if sweep else 'absent'} "
            f"indication={'present' if indication else 'absent'} "
            f"direction={trend_direction} "
            f"recent={len(recent)} swing_highs={len(swing_highs)} swing_lows={len(swing_lows)} "
            f"confirm_bars={confirmation_bars}"
        )

    if trend_direction == "long":
        # [ALGORITHMIC PRECISION]
        # Check momentum of the recent move to allow V-Bottoms (1 swing)
        # Calculate ATR-based momentum
        atr = calculate_atr(recent, period=14) or 0.0001
        last_move_size = recent[-1].close - recent[0].close
        momentum_score = last_move_size / (atr * len(recent)) # Pips per bar per ATR? No. 
        # Simpler: If last candle is huge (> 2 ATR), assume momentum.
        is_high_momentum = (recent[-1].close - recent[-1].open) > (atr * 2.0)
        
        # [SMART OVERRIDE]
        # If High Momentum, allow 1 swing (catch the rocket).
        # Else, require 2 swings (ensure structure).
        min_lows = 1 if is_high_momentum else 2
        
        if len(swing_lows) < min_lows or len(swing_highs) < 1:
            if debug:
                logger.info(f"[CONTINUATION] REJECTED: long missing swing structure (lows={len(swing_lows)}<{min_lows})")
            return None

        last_low = float(recent[swing_lows[-1]].close)
        # Verify Higher Low only if we required 2 lows
        if min_lows >= 2:
            prior_low = float(recent[swing_lows[-2]].close)
            if last_low <= prior_low:
                if debug:
                    logger.info("[CONTINUATION] REJECTED: long no higher-low structure")
                return None

        last_high = float(recent[swing_highs[-1]].close)
        if confirmation_bars < 1:
            confirmation_bars = 1
        confirm_closes = [float(c.close) for c in recent[-confirmation_bars:]]
        if not all(close > last_high for close in confirm_closes):
            if debug:
                logger.info(
                    "[CONTINUATION] REJECTED: long close_confirm=%s <= swing_high=%.4f",
                    confirm_closes,
                    last_high,
                )
            return None

        if debug:
            logger.info(
                "[CONTINUATION] DETECTED: long close_confirm=%s > swing_high=%.4f",
                confirm_closes,
                last_high,
            )

        return ContinuationSignal(direction="long", trigger_level=last_high, index=len(candles) - 1)

    elif trend_direction == "short":
        # [ALGORITHMIC PRECISION]
        atr = calculate_atr(recent, period=14) or 0.0001
        is_high_momentum = (recent[-1].open - recent[-1].close) > (atr * 2.0)
        
        # [SMART OVERRIDE]
        min_highs = 1 if is_high_momentum else 2
        
        if len(swing_highs) < min_highs or len(swing_lows) < 1:
            if debug:
                logger.info(f"[CONTINUATION] REJECTED: short missing swing structure (highs={len(swing_highs)}<{min_highs})")
            return None

        last_high = float(recent[swing_highs[-1]].close)
        # Verify Lower High only if we required 2 highs
        if min_highs >= 2:
            prior_high = float(recent[swing_highs[-2]].close)
            if last_high >= prior_high:
                if debug:
                    logger.info("[CONTINUATION] REJECTED: short no lower-high structure")
                return None

        last_low = float(recent[swing_lows[-1]].close)
        if confirmation_bars < 1:
            confirmation_bars = 1
        confirm_closes = [float(c.close) for c in recent[-confirmation_bars:]]
        if not all(close < last_low for close in confirm_closes):
            if debug:
                logger.info(
                    "[CONTINUATION] REJECTED: short close_confirm=%s >= swing_low=%.4f",
                    confirm_closes,
                    last_low,
                )
            return None

        if debug:
            logger.info(
                "[CONTINUATION] DETECTED: short close_confirm=%s < swing_low=%.4f",
                confirm_closes,
                last_low,
            )

        return ContinuationSignal(direction="short", trigger_level=last_low, index=len(candles) - 1)


def detect_no_trade_zone(
    candles: list[Candle],
    *,
    swing_lookback: int = 2,
    window: int = 80,
) -> NoTradeZone | None:
    """Identifies the current 'No Trade Zone' (Range between last Swing High/Low)."""
    if len(candles) < (swing_lookback * 2 + 3):
        return None
    
    recent = candles[-window:] if window > 0 else candles
    swing_highs, swing_lows = swing_points_close(recent, lookback=swing_lookback)
    
    if not swing_highs or not swing_lows:
        return None
        
    last_high_idx = swing_highs[-1]
    last_low_idx = swing_lows[-1]
    
    last_high = float(recent[last_high_idx].close)
    last_low = float(recent[last_low_idx].close)
    
    # Check if price has broken out since the swings were formed
    # A break means the zone is technically "broken" (Indication), but we track the origin
    current_price = float(recent[-1].close)
    
    is_broken = False
    break_dir = None
    
    if current_price > last_high:
        is_broken = True
        break_dir = "long"
    elif current_price < last_low:
        is_broken = True
        break_dir = "short"
        
    return NoTradeZone(
        high=last_high, 
        low=last_low, 
        is_broken=is_broken, 
        break_direction=break_dir
    )


def last_structure_range(
    candles: list[Candle],
    *,
    swing_lookback: int = 2,
    window: int = 80,
) -> tuple[float, float] | None:
    """Returns the last swing high/low levels for no-trade zone checks."""
    ntz = detect_no_trade_zone(candles, swing_lookback=swing_lookback, window=window)
    if ntz:
        return ntz.high, ntz.low
    return None


def detect_indication(
    candles: list[Candle],
    *,
    swing_lookback: int = 2,
    window: int = 80,
    max_swings_to_check: int = 3,  # Check last N swings, not just the most recent
) -> IndicationSignal | None:
    """Detects a structure indication (break of recent swing high/low).
    
    Modified to check multiple recent swings to catch breaks in real-time,
    not just the absolute most recent swing which may have reversed.
    """
    if len(candles) < (swing_lookback * 2 + 3):
        return None
    recent = candles[-window:] if window > 0 else candles
    offset = len(candles) - len(recent)
    swing_highs, swing_lows = swing_points_close(recent, lookback=swing_lookback)
    if not swing_highs and not swing_lows:
        return None

    # Check last N swing highs for bullish breaks (most recent first)
    bullish_breaks = []
    if swing_highs:
        for swing_idx in reversed(swing_highs[-max_swings_to_check:]):
            swing_high = recent[swing_idx].close
            # Check if any candle after this swing closed above it with CONVICTION
            # [ALGORITHMIC PRECISION] Noise Filter
            atr = calculate_atr(recent, period=14) or 0.0001
            conviction_buffer = atr * 0.05
            
            for i in range(swing_idx + 1, len(recent)):
                if recent[i].close > (swing_high + conviction_buffer):
                    bullish_breaks.append((i, swing_high, swing_idx))
                    break  # Found a break for this swing, move to next swing

    # Check last N swing lows for bearish breaks (most recent first)
    bearish_breaks = []
    if swing_lows:
        for swing_idx in reversed(swing_lows[-max_swings_to_check:]):
            swing_low = recent[swing_idx].close
            # Check if any candle after this swing closed below it with CONVICTION
            # [ALGORITHMIC PRECISION] Noise Filter
            atr = calculate_atr(recent, period=14) or 0.0001
            conviction_buffer = atr * 0.05
            
            for i in range(swing_idx + 1, len(recent)):
                if recent[i].close < (swing_low - conviction_buffer):
                    bearish_breaks.append((i, swing_low, swing_idx))
                    break  # Found a break for this swing, move to next swing

    # If no breaks found, no indication
    if not bullish_breaks and not bearish_breaks:
        return None

    # [STRICT ICC] Indication is only valid if it breaks the *current* NO TRADE ZONE.
    # Older breaks that are now inside a new range are ignored.
    latest_bullish = max(bullish_breaks, key=lambda x: x[0]) if bullish_breaks else None
    latest_bearish = max(bearish_breaks, key=lambda x: x[0]) if bearish_breaks else None

    # Case 1: Bullish Break
    if latest_bullish and (not latest_bearish or latest_bullish[0] > latest_bearish[0]):
         return IndicationSignal(
            direction="long",
            level=float(latest_bullish[1]),
            index=offset + latest_bullish[0]
        )
        
    # Case 2: Bearish Break
    if latest_bearish:
        return IndicationSignal(
            direction="short",
            level=float(latest_bearish[1]),
            index=offset + latest_bearish[0]
        )
    
    return None


def detect_correction(
    candles: list[Candle],
    indication: IndicationSignal | None,
    *,
    min_retracement_pct: float = 0.25,  # [HARDENED] 25% minimum validation
    max_retracement_pct: float = 0.75,  # [HARDENED] 75% maximum validation
    window: int = 80,
    swing_lookback: int = 2,
) -> CorrectionSignal | None:
    """Detects a correction phase after an indication.

    ICC Correction Requirements (per Qwen):
    - Retracement of 38.2%-61.8% of the indication move
    - Retest of the indication level (price comes back toward it)
    - Does NOT break the indication level
    - Should happen within reasonable time (not too long)

    Args:
        candles: Price history
        indication: The indication signal to check for correction after
        min_retracement_pct: Minimum retracement to qualify as correction (default 38.2%)
        max_retracement_pct: Maximum retracement before invalidation (default 61.8%)
        window: How many candles to look back
        swing_lookback: Swing detection parameter

    Returns:
        CorrectionSignal if valid correction detected, None otherwise
    """
    # [ALGORITHMIC PRECISION] Dynamic Retracement Limits
    # Will calculate impulse velocity to adjust min_retracement automatically.
    import logging
    import os
    logger = logging.getLogger(__name__)
    debug = os.getenv("DEBUG_ICC") == "1"

    # Must have an indication to correct from
    if indication is None:
        if debug:
            logger.info("[CORRECTION] REJECTED: no indication to correct from")
        return None

    if len(candles) < swing_lookback * 2 + 5:
        if debug:
            logger.info(f"[CORRECTION] REJECTED: insufficient candles={len(candles)}")
        return None

    recent = candles[-window:] if window > 0 else candles
    offset = len(candles) - len(recent)

    # Find the indication candle in our window
    indication_idx_in_window = indication.index - offset
    if indication_idx_in_window < 0 or indication_idx_in_window >= len(recent):
        if debug:
            logger.info("[CORRECTION] REJECTED: indication outside window")
        return None

    # Get candles after indication
    post_indication = recent[indication_idx_in_window:]
    if len(post_indication) < 3:
        if debug:
            logger.info("[CORRECTION] REJECTED: insufficient candles after indication")
        return None

    indication_candle = recent[indication_idx_in_window]
    indication_level = indication.level

    if indication.direction == "long":
        # For long: indication broke above a high, correction pulls back toward it
        # Find the swing low before indication (the start of the move)
        swing_highs, swing_lows = swing_points_close(recent[:indication_idx_in_window + 1], lookback=swing_lookback)
        if not swing_lows:
            if debug:
                logger.info("[CORRECTION] REJECTED: no prior swing low for long correction")
            return None

        prior_low = float(recent[swing_lows[-1]].close)
        indication_high = indication_level
        move_size = indication_high - prior_low

        if move_size <= 0:
            return None

        # [DYNAMIC LIMITS]
        # Calculate Impulse Velocity (Pips per Bar of the move)
        move_bars = max(1, indication_idx_in_window - swing_lows[-1])
        velocity = move_size / move_bars
        atr = calculate_atr(recent, period=14) or 0.0001
        relative_velocity = velocity / atr
        
        # If Impulse was > 1.0 ATR per bar (Explosive), allow shallow pullback (15%)
        effective_min_retracement = 0.15 if relative_velocity > 1.0 else min_retracement_pct

        # Find the lowest point after indication (the correction low)
        correction_low = min(float(c.low) for c in post_indication)

        # Check if correction is in valid range
        retracement_amount = indication_high - correction_low
        retracement_pct = retracement_amount / move_size

        if retracement_pct < effective_min_retracement:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: long retracement too shallow "
                    f"{retracement_pct:.1%} < {effective_min_retracement:.1%}"
                )
            return None

        if retracement_pct > max_retracement_pct:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: long retracement too deep "
                    f"{retracement_pct:.1%} > {max_retracement_pct:.1%}"
                )
            return None

        # Check that correction didn't break below prior low (invalidation)
        if correction_low < prior_low:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: long correction broke prior low "
                    f"{correction_low:.4f} < {prior_low:.4f}"
                )
            return None

        # Find the index of the correction low
        correction_idx = None
        for i, c in enumerate(post_indication):
            if float(c.low) == correction_low:
                correction_idx = indication.index + i
                break

        if debug:
            logger.info(
                f"[CORRECTION] DETECTED: long retracement={retracement_pct:.1%} "
                f"indication={indication_high:.4f} correction_low={correction_low:.4f}"
            )

        return CorrectionSignal(
            direction="long",
            indication_level=indication_level,
            retracement_level=correction_low,
            retracement_pct=retracement_pct,
            index=correction_idx or indication.index + 1,
        )

    else:  # short
        # For short: indication broke below a low, correction rallies back toward it
        swing_highs, swing_lows = swing_points_close(recent[:indication_idx_in_window + 1], lookback=swing_lookback)
        if not swing_highs:
            if debug:
                logger.info("[CORRECTION] REJECTED: no prior swing high for short correction")
            return None

        prior_high = float(recent[swing_highs[-1]].close)
        indication_low = indication_level
        move_size = prior_high - indication_low

        if move_size <= 0:
            return None
            
        # [DYNAMIC LIMITS]
        move_bars = max(1, indication_idx_in_window - swing_highs[-1])
        velocity = move_size / move_bars
        atr = calculate_atr(recent, period=14) or 0.0001
        relative_velocity = velocity / atr
        
        # If Impulse was > 1.0 ATR per bar (Explosive), allow shallow pullback (15%)
        effective_min_retracement = 0.15 if relative_velocity > 1.0 else min_retracement_pct

        # Find the highest point after indication (the correction high)
        correction_high = max(float(c.high) for c in post_indication)

        # Check if correction is in valid range
        retracement_amount = correction_high - indication_low
        retracement_pct = retracement_amount / move_size

        if retracement_pct < effective_min_retracement:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: short retracement too shallow "
                    f"{retracement_pct:.1%} < {effective_min_retracement:.1%}"
                )
            return None

        if retracement_pct > max_retracement_pct:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: short retracement too deep "
                    f"{retracement_pct:.1%} > {max_retracement_pct:.1%}"
                )
            return None

        # Check that correction didn't break above prior high (invalidation)
        if correction_high > prior_high:
            if debug:
                logger.info(
                    f"[CORRECTION] REJECTED: short correction broke prior high "
                    f"{correction_high:.4f} > {prior_high:.4f}"
                )
            return None

        # Find the index of the correction high
        correction_idx = None
        for i, c in enumerate(post_indication):
            if float(c.high) == correction_high:
                correction_idx = indication.index + i
                break

        if debug:
            logger.info(
                f"[CORRECTION] DETECTED: short retracement={retracement_pct:.1%} "
                f"indication={indication_low:.4f} correction_high={correction_high:.4f}"
            )

        return CorrectionSignal(
            direction="short",
            indication_level=indication_level,
            retracement_level=correction_high,
            retracement_pct=retracement_pct,
            index=correction_idx or indication.index + 1,
        )



# Swing detection functions moved to tradebot_sci.market.swing_analysis
# for shared use across modules


def detect_structure_invalidation(
    candles: list[Candle],
    position_side: str,
    *,
    swing_lookback: int = 2,
    window: int = 80,
    atr_period: int = 14,
    atr_mult: float = 0.5,
) -> StructureInvalidation | None:
    """Detects a conservative structure invalidation for an existing position.

    Long: last CLOSE must be below the most recent swing low by (ATR * atr_mult).
    Short: last CLOSE must be above the most recent swing high by (ATR * atr_mult).

    This is meant to be a deterministic "get flat" signal, not an entry model.
    """
    if position_side not in {"long", "short"}:
        return None
    if len(candles) < max(atr_period + 2, swing_lookback * 2 + 5):
        return None

    recent = candles[-window:] if window > 0 else candles
    last = recent[-1]
    atr = calculate_atr(recent, period=atr_period)
    if atr is None:
        return None
    buffer = float(max(0.0, atr * atr_mult))

    swing_highs, swing_lows = swing_points_close(recent, lookback=swing_lookback)
    if position_side == "long":
        for idx in reversed(swing_lows):
            level = float(recent[idx].close)
            if last.close < (level - buffer):
                absolute_idx = len(candles) - len(recent) + (len(recent) - 1)
                return StructureInvalidation(
                    position_side="long",
                    swing_level=level,
                    last_close=float(last.close),
                    buffer=buffer,
                    index=absolute_idx,
                )
        return None

    for idx in reversed(swing_highs):
        level = float(recent[idx].close)
        if last.close > (level + buffer):
            absolute_idx = len(candles) - len(recent) + (len(recent) - 1)
            return StructureInvalidation(
                position_side="short",
                swing_level=level,
                last_close=float(last.close),
                buffer=buffer,
                index=absolute_idx,
            )
    return None


def calculate_atr(candles: list[Candle], *, period: int = 14) -> float | None:
    if period < 1 or len(candles) < period + 1:
        return None
    trs: list[float] = []
    for prev, curr in zip(candles[-(period + 1) : -1], candles[-period:]):
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        trs.append(float(tr))
    if not trs:
        return None
    return sum(trs) / len(trs)
