"""Trend Detection: Indicator Direction Consensus + Structure Confidence

This module is the SOLE AUTHORITY on trend direction. It replaces the
legacy `infer_trend_from_swings()` swing-based method with a modern
indicator-consensus + structure-validation system.

Architecture:
    1. Indicator Consensus: Enabled indicators VOTE on direction.
    2. Structure Confidence: ADX chop gate, EMA55 price structure,
       and Bollinger squeeze validate the vote against real market state.
    3. Multi-Timeframe: HTF and LTF are computed INDEPENDENTLY on separate
       candle sets, producing genuinely different signals.

Usage:
    from tradebot_sci.market.trend_consensus import detect_trend_direction

    result = detect_trend_direction(
        candles, profile,
        htf_candles=snapshot.htf_candles,
        ltf_candles=snapshot.ltf_candles,
    )
    # result.htf_dir / result.ltf_dir can DISAGREE (real multi-timeframe)
    # result.htf_align = True only when both agree
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from tradebot_sci.market.models import Candle, TrendState
from tradebot_sci.market.trend import (
    compute_adx_with_direction,
    compute_rsi,
    compute_macd,
    compute_bollinger,
    compute_supertrend,
    compute_ema_ribbon,
    compute_ichimoku,
    compute_parabolic_sar,
    compute_vwap,
    compute_hull_ma,
)

logger = logging.getLogger(__name__)

# ── Strength floor ────────────────────────────────────────────────────
# After structure penalties stack, strength is floored here to prevent
# the direction from being completely neutered.  If indicators agree on
# a direction and structure confirms it's not chop, the strength should
# never go below this.
_STRENGTH_FLOOR = 0.25

# ── Trend computation cache ──────────────────────────────────────────
# Keyed on (last_candle_ts, candle_count, label) to avoid recomputing
# 10+ expensive indicators when the same candle set is seen again.
_TF_CACHE: dict[tuple, "_TimeframeResult"] = {}
_TF_CACHE_MAX = 64  # Increased to prevent thrashing with multi-symbol + multi-timeframe computations


def clear_cache():
    """Clear the trend computation cache for a fresh replay day.

    Called by loop.py when day-chaining to prevent stale indicator results
    from the previous day being returned for the new day's candle data.
    """
    global _TF_CACHE
    _TF_CACHE.clear()
    logger.info("[TREND-DETECT] Indicator cache cleared for new replay day")


# ─────────────────────────────────────────────────────────────────────
# Per-timeframe result (internal)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class _TimeframeResult:
    """Indicators + structure validation for a single timeframe."""
    direction: str      # "long", "short", "neutral"
    strength: float     # 0.0 - 1.0  (after structure penalties)
    adx: float
    rsi: float
    macd: dict
    supertrend: dict
    ema_ribbon: dict
    bollinger: dict
    adx_data: dict
    ichimoku: dict
    parabolic_sar: dict
    vwap: dict
    hull_ma: dict
    votes: list         # Human-readable vote trail


# ─────────────────────────────────────────────────────────────────────
# Public result
# ─────────────────────────────────────────────────────────────────────
@dataclass
class TrendConsensus:
    """Result of the multi-timeframe indicator direction consensus."""
    htf_dir: str           # HTF direction ("long", "short", "neutral")
    mtf_dir: str           # MTF direction ("long", "short", "neutral")
    ltf_dir: str           # LTF direction ("long", "short", "neutral")
    exec_dir: str          # Execution chart direction ("long", "short", "neutral")
    htf_strength: float    # 0.0 - 1.0
    mtf_strength: float    # 0.0 - 1.0
    ltf_strength: float    # 0.0 - 1.0
    exec_strength: float   # 0.0 - 1.0
    htf_align: bool        # HTF and LTF agree on direction
    indicator_dir: str     # Combined consensus ("long", "short", "neutral")
    indicator_strength: float  # Combined vote ratio
    htf_adx: float         # HTF ADX strength value
    # Raw indicator data (from HTF, for GUI broadcast)
    rsi: float
    macd: dict
    supertrend: dict
    ema_ribbon: dict
    bollinger: dict
    adx_data: dict         # Full ADX+DI data
    vote_sources: list     # Merged vote trail from both timeframes
    # Regime classification for Conductor routing
    market_regime: str = "unknown"  # "trending", "ranging", "transitional", "choppy"


# ─────────────────────────────────────────────────────────────────────
# Core: per-timeframe indicator computation
# ─────────────────────────────────────────────────────────────────────
def _compute_timeframe(
    candles: list[Candle],
    profile: object,
    *,
    label: str = "TF",
) -> _TimeframeResult:
    """Compute indicators, vote on direction, and validate against
    price structure for a SINGLE timeframe.

    Args:
        candles: Candle data for this timeframe.
        profile: Trading profile with indicator toggle flags.
        label: Human-readable label for logging ("HTF" or "LTF").

    Returns:
        _TimeframeResult with direction, strength, and raw indicator data.
    """
    # ── Cache check ──────────────────────────────────────────────────
    global _TF_CACHE
    _cache_key = None
    if candles:
        _cache_key = (candles[-1].timestamp, len(candles), label, candles[0].close, candles[-1].close)
        cached = _TF_CACHE.get(_cache_key)
        if cached is not None:
            return cached

    # ── Thresholds ────────────────────────────────────────────────────
    adx_threshold = float(getattr(profile, 'adx_gate_threshold', 20))
    chop_threshold = float(getattr(profile, 'trend_chop_threshold', 15))

    # ── Compute all indicators ────────────────────────────────────────
    adx_data = compute_adx_with_direction(candles) if len(candles) >= 15 else {
        "adx": 0.0, "direction": "neutral", "plus_di": 0.0, "minus_di": 0.0
    }
    adx_val = round(adx_data["adx"], 1)

    rsi_val = compute_rsi(candles) if len(candles) >= 15 else 50.0
    macd_data = compute_macd(candles) if len(candles) >= 35 else {
        "macd": 0, "signal": 0, "histogram": 0
    }
    boll_data = compute_bollinger(candles) if len(candles) >= 20 else {
        "upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "squeeze": False
    }
    st_data = compute_supertrend(candles) if len(candles) >= 11 else {
        "direction": "neutral", "value": 0
    }
    ema_data = compute_ema_ribbon(candles) if len(candles) >= 55 else {
        "ema8": 0, "ema21": 0, "ema55": 0, "aligned": False, "direction": "neutral"
    }
    ichi_data = compute_ichimoku(candles) if len(candles) >= 52 else {
        "tenkan": 0, "kijun": 0, "senkou_a": 0, "senkou_b": 0,
        "cloud_top": 0, "cloud_bot": 0, "direction": "neutral",
    }
    psar_data = compute_parabolic_sar(candles) if len(candles) >= 5 else {
        "value": 0, "direction": "neutral"
    }
    vwap_data = compute_vwap(candles) if len(candles) >= 10 else {
        "vwap": 0, "direction": "neutral"
    }
    hma_data = compute_hull_ma(candles) if len(candles) >= 27 else {
        "hma": 0, "prev_hma": 0, "direction": "neutral"
    }

    # ── Indicator Direction Votes ─────────────────────────────────────
    direction_votes: list[str] = []
    vote_trail: list[str] = []

    # ADX + DI: direction from DI+/DI- crossover, only if ADX ≥ threshold
    if getattr(profile, 'trend_adx_enabled', True):
        adx_dir = adx_data.get("direction", "neutral")
        if adx_val >= adx_threshold and adx_dir in ("long", "short"):
            direction_votes.append(adx_dir)
            vote_trail.append(
                f"{label}:ADX={adx_val:.0f} DI+={adx_data['plus_di']:.1f} "
                f"DI-={adx_data['minus_di']:.1f}→{adx_dir}"
            )

    # EMA Ribbon: aligned ribbon is a strong structural signal
    if getattr(profile, 'trend_ema_ribbon_enabled', False):
        ema_dir = ema_data.get("direction", "neutral")
        if ema_data.get("aligned", False) and ema_dir in ("long", "short"):
            direction_votes.append(ema_dir)
            vote_trail.append(f"{label}:EMA={ema_dir}")

    # Supertrend: direct direction signal
    if getattr(profile, 'trend_supertrend_enabled', False):
        st_dir = st_data.get("direction", "neutral")
        if st_dir in ("long", "short"):
            direction_votes.append(st_dir)
            vote_trail.append(f"{label}:ST={st_dir}")

    # MACD: histogram direction
    if getattr(profile, 'trend_macd_enabled', False):
        hist = macd_data.get("histogram", 0)
        if hist > 0:
            direction_votes.append("long")
            vote_trail.append(f"{label}:MACD=long(h={hist:.4f})")
        elif hist < 0:
            direction_votes.append("short")
            vote_trail.append(f"{label}:MACD=short(h={hist:.4f})")

    # RSI: above 55 = bullish lean, below 45 = bearish lean
    if getattr(profile, 'trend_rsi_enabled', False):
        if rsi_val > 55:
            direction_votes.append("long")
            vote_trail.append(f"{label}:RSI={rsi_val:.0f}→long")
        elif rsi_val < 45:
            direction_votes.append("short")
            vote_trail.append(f"{label}:RSI={rsi_val:.0f}→short")

    # Ichimoku Cloud: price vs cloud position
    if getattr(profile, 'trend_ichimoku_enabled', False):
        ichi_dir = ichi_data.get("direction", "neutral")
        if ichi_dir in ("long", "short"):
            direction_votes.append(ichi_dir)
            vote_trail.append(f"{label}:ICHI={ichi_dir}")

    # Parabolic SAR: dot position = direction
    if getattr(profile, 'trend_parabolic_sar_enabled', False):
        psar_dir = psar_data.get("direction", "neutral")
        if psar_dir in ("long", "short"):
            direction_votes.append(psar_dir)
            vote_trail.append(f"{label}:PSAR={psar_dir}")

    # VWAP: price above/below volume-weighted average
    if getattr(profile, 'trend_vwap_enabled', False):
        vwap_dir = vwap_data.get("direction", "neutral")
        if vwap_dir in ("long", "short"):
            direction_votes.append(vwap_dir)
            vote_trail.append(f"{label}:VWAP={vwap_dir}")

    # Hull MA: slope direction
    if getattr(profile, 'trend_hull_ma_enabled', False):
        hma_dir = hma_data.get("direction", "neutral")
        if hma_dir in ("long", "short"):
            direction_votes.append(hma_dir)
            vote_trail.append(f"{label}:HMA={hma_dir}")

    # ── Count ENABLED directional indicators ────────────────────────
    # Used as the denominator for strength: prevents inflation when
    # indicators can't vote due to insufficient candle data.
    # EMA Ribbon is treated as an optional enhancement that can confirm a trend
    # but does NOT add to the baseline enabled_count, so it won't penalize 
    # the signal strength if it's misaligned/absent.
    _enabled_flags = [
        getattr(profile, 'trend_adx_enabled', True),
        getattr(profile, 'trend_supertrend_enabled', False),
        getattr(profile, 'trend_macd_enabled', False),
        getattr(profile, 'trend_rsi_enabled', False),
        getattr(profile, 'trend_ichimoku_enabled', False),
        getattr(profile, 'trend_parabolic_sar_enabled', False),
        getattr(profile, 'trend_vwap_enabled', False),
        getattr(profile, 'trend_hull_ma_enabled', False),
    ]
    enabled_count = sum(1 for f in _enabled_flags if f)
    any_directional_enabled = enabled_count > 0

    if not any_directional_enabled:
        logger.error(
            "[TREND-DETECT] NO directional indicators enabled! "
            "Defaulting to ADX."
        )
        enabled_count = 1  # ADX fallback counts as 1
        adx_dir = adx_data.get("direction", "neutral")
        if adx_val >= adx_threshold and adx_dir in ("long", "short"):
            direction_votes.append(adx_dir)
            vote_trail.append(f"{label}:ADX(fallback)={adx_dir}")

    # ── Build Raw Consensus ──────────────────────────────────────────
    # Strength = majority_votes / max(actual_voters, enabled_count)
    # This prevents strength inflation when indicators can't vote
    # due to insufficient candle data. E.g., 2 agreeing votes out
    # of 4 enabled indicators = 0.50, not 2/2 = 1.00.
    direction = "neutral"
    strength = 0.0

    if direction_votes:
        long_votes = direction_votes.count("long")
        short_votes = direction_votes.count("short")
        total_votes = len(direction_votes)
        # Use the larger of actual voters or enabled count as denominator
        denominator = max(total_votes, enabled_count)

        if long_votes > short_votes:
            direction = "long"
            strength = round(long_votes / denominator, 2)
        elif short_votes > long_votes:
            direction = "short"
            strength = round(short_votes / denominator, 2)
        # Tie = neutral

        if total_votes < enabled_count:
            vote_trail.append(
                f"{label}:PARTIAL {total_votes}/{enabled_count} indicators voted"
            )

    # ── Structure Confidence Layer ────────────────────────────────────
    # Validates indicator consensus against price structure.

    # Check 1: ADX Chop Gate with Dead-Zone Hysteresis
    #   ADX <  chop_threshold (15) → definite chop → neutral
    #   ADX >= chop but < adx_threshold (20) → gray zone → allow but halve
    #   ADX >= adx_threshold → trending → full strength
    if direction in ("long", "short"):
        if adx_val < chop_threshold:
            vote_trail.append(
                f"{label}:CHOP ADX={adx_val:.0f}<{chop_threshold:.0f}→neutral"
            )
            direction = "neutral"
            strength = 0.0
        elif adx_val < adx_threshold:
            # Gray zone: trend is weak but present — halve confidence
            strength = round(strength * 0.5, 2)
            vote_trail.append(
                f"{label}:WEAK ADX={adx_val:.0f} ({chop_threshold:.0f}-{adx_threshold:.0f})→str×0.5"
            )

    # Check 2: Price vs EMA55 Structure Confirmation
    if direction in ("long", "short") and candles:
        ema55 = ema_data.get("ema55", 0)
        current_close = candles[-1].close
        if ema55 > 0:
            if direction == "long" and current_close < ema55:
                strength = round(strength * 0.5, 2)
                vote_trail.append(
                    f"{label}:STRUCT↓ long but close<EMA55"
                )
            elif direction == "short" and current_close > ema55:
                strength = round(strength * 0.5, 2)
                vote_trail.append(
                    f"{label}:STRUCT↓ short but close>EMA55"
                )

    # Check 3: Bollinger Squeeze (only if Bollinger is enabled)
    if (
        direction in ("long", "short")
        and getattr(profile, 'trend_bollinger_enabled', False)
        and boll_data.get("squeeze", False)
    ):
        strength = round(strength * 0.75, 2)
        vote_trail.append(
            f"{label}:SQUEEZE bw={boll_data.get('bandwidth', 0):.2f}→str×0.75"
        )

    # Floor: prevent direction from being completely neutered
    if direction in ("long", "short") and strength < _STRENGTH_FLOOR:
        strength = _STRENGTH_FLOOR

    result = _TimeframeResult(
        direction=direction,
        strength=strength,
        adx=adx_val,
        rsi=rsi_val,
        macd=macd_data,
        supertrend=st_data,
        ema_ribbon=ema_data,
        bollinger=boll_data,
        adx_data=adx_data,
        ichimoku=ichi_data,
        parabolic_sar=psar_data,
        vwap=vwap_data,
        hull_ma=hma_data,
        votes=vote_trail,
    )

    # ── Cache store ──────────────────────────────────────────────────
    if _cache_key is not None:
        if len(_TF_CACHE) >= _TF_CACHE_MAX:
            # Evict oldest entries
            for k in list(_TF_CACHE.keys())[:_TF_CACHE_MAX // 2]:
                del _TF_CACHE[k]
        _TF_CACHE[_cache_key] = result

    return result


# ─────────────────────────────────────────────────────────────────────
# Regime Classifier (Conductor-aware)
# ─────────────────────────────────────────────────────────────────────
def _classify_regime(htf: _TimeframeResult, ltf: _TimeframeResult) -> str:
    """Classify market regime using multi-factor analysis.

    Combines ADX, Bollinger bandwidth, EMA ribbon alignment, and
    vote consensus to produce a single regime classification:

    - 'trending':      Strong directional move (ADX>30, EMA aligned, BB expanding)
    - 'ranging':       Sideways consolidation  (ADX<18, narrow BBs)
    - 'transitional':  Regime shift in progress (ADX 20-30, squeeze breakout)
    - 'choppy':        No clear regime          (conflicting signals)
    """
    adx = htf.adx
    bb = htf.bollinger
    ema = htf.ema_ribbon
    strength = htf.strength

    bb_bandwidth = bb.get("bandwidth", 0) if bb else 0
    bb_squeeze = bb.get("squeeze", False) if bb else False
    ema_aligned = ema.get("aligned", False) if ema else False

    # ── Early exit: HTF vs LTF directional conflict ─────────────────────
    # If HTF and LTF point in OPPOSITE directions, it's usually whipsaw.
    # However, if HTF ADX is strong (>= 25), this is likely just a healthy LTF
    # pullback within a macro trend (exactly what Golden Pocket hunts).
    htf_dir = htf.direction
    ltf_dir = ltf.direction
    if (htf_dir == "long" and ltf_dir == "short") or \
       (htf_dir == "short" and ltf_dir == "long"):
        if htf.adx < 25:
            logger.debug(
                f"[REGIME] CHOPPY — HTF/LTF disagree ({htf_dir} vs {ltf_dir}), "
                f"blocking entries (was incorrectly returning 'ranging' → MeanReversion)"
            )
            return "choppy"
        else:
            logger.debug(
                f"[REGIME] TREND-CORRECTION — HTF/LTF disagree ({htf_dir} vs {ltf_dir}) "
                f"but HTF ADX is strong ({htf.adx:.1f}). Preserving trend status for pullback strata."
            )


    # ── TRENDING: Strong, confirmed directional move ───────────────
    # Requires ALL of: ADX>30, EMA ribbon aligned, AND at least
    # one confirmation (BB expanding or strong consensus).
    # This is deliberately strict — false trending calls are expensive.
    # FALLBACK: If EMA data is unavailable (ema8==0, e.g. during replay warmup
    # or sparse HTF data), allow trending on ADX>20 when consensus is strong
    # (≥75%) or ADX>30 with any strength. This prevents false choppy blocks.
    ema_unavailable = (ema.get("ema8", 0) == 0) if ema else True
    high_consensus = strength >= 0.75
    
    # A pullback often breaks perfect EMA alignment on the HTF.
    # If the timeframes agree (trend resumption) and we have decent ADX, allow it as trending.
    has_trend_momentum = ema_aligned or (htf_dir == ltf_dir and strength >= 0.5)
    _ema_adx_threshold = 20 if (ema_unavailable and high_consensus) else 30
    
    if adx > 20 and (has_trend_momentum or (ema_unavailable and adx > _ema_adx_threshold)):
        confirmations = 0
        if bb_bandwidth > 0.01:  # Bands expanding
            confirmations += 1
        if strength >= 0.6:  # Strong indicator consensus
            confirmations += 1
        if htf_dir == ltf_dir:  # Timeframes agree
            confirmations += 1

        if confirmations >= 1:
            logger.debug(
                f"[REGIME] TRENDING (adx={adx:.0f}, bw={bb_bandwidth:.4f}, "
                f"ema_aligned={ema_aligned}, ema_unavailable={ema_unavailable}, "
                f"str={strength:.2f}, conf={confirmations})"
            )
            return "trending"

    # ── RANGING vs CHOPPY: Sideways consolidation vs Noise ─────────
    # ADX <= 20 = no meaningful trend.
    # If ADX is extremely low (<15), it is usually pure chop, NOT a tradable range,
    # UNLESS Bollinger Bands are visibly squeezing (which implies accumulation).
    adx_chop_threshold = 15.0
    
    if adx < adx_chop_threshold and not bb_squeeze:
        logger.debug(
            f"[REGIME] CHOPPY (adx={adx:.0f} < {adx_chop_threshold}, no squeeze) "
            f"→ Explicitly blocking directionless noise"
        )
        return "choppy"

    ranging_signals = 0
    if adx <= adx_chop_threshold:
        ranging_signals += 2  # ADX is double-weighted
    if bb_squeeze:
        ranging_signals += 1
    if bb_bandwidth < 0.006:  # Very narrow bands
        ranging_signals += 1
    if strength < 0.35:  # Weak directional consensus
        ranging_signals += 1

    if ranging_signals >= 3:
        logger.debug(
            f"[REGIME] RANGING (adx={adx:.0f}, bw={bb_bandwidth:.4f}, "
            f"squeeze={bb_squeeze}, str={strength:.2f})"
        )
        return "ranging"

    # ── TRANSITIONAL: Regime shift in progress ───────────────────
    # ADX 20-30 with BB starting to expand from squeeze or BBs
    # moderately wide. This is where breakout strategies thrive.
    # Must also have directional agreement between timeframes.
    if 10 < adx <= 20:  # Extended from 12: captures ADX 10-12 that was leaking into ranging
        has_breakout_signal = (
            (bb_squeeze and bb_bandwidth > 0.003)  # Squeeze breaking out
            or (bb_bandwidth > 0.008 and strength >= 0.4)  # Clear expansion + direction
        )
        if has_breakout_signal and htf_dir in ("long", "short"):
            logger.debug(
                f"[REGIME] TRANSITIONAL (adx={adx:.0f}, bw={bb_bandwidth:.4f}, "
                f"squeeze={bb_squeeze}, str={strength:.2f})"
            )
            return "transitional"

        # No breakout signal at ADX 20-30 = moderate, directionless
        # market.  This is ranging, not choppy.  Choppy implies
        # genuinely conflicting signals (long vs short whipsaw).
        logger.debug(
            f"[REGIME] RANGING (adx={adx:.0f} in 20-30 band, no breakout, "
            f"bw={bb_bandwidth:.4f}, str={strength:.2f})"
        )
        return "ranging"

    # ── CHOPPY: Genuinely conflicting signals ─────────────────────
    # Only fires for ADX > 30 that didn't qualify as trending
    # (contradictory indicators at high ADX = real whipsaw).
    logger.debug(
        f"[REGIME] CHOPPY (adx={adx:.0f}, bw={bb_bandwidth:.4f}, "
        f"str={strength:.2f})"
    )
    return "choppy"


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────
def detect_trend_direction(
    candles: list[Candle],
    profile: object,
    *,
    htf_candles: list[Candle] | None = None,
    mtf_candles: list[Candle] | None = None,
    ltf_candles: list[Candle] | None = None,
) -> TrendConsensus:
    """Compute multi-timeframe indicator consensus + structure validation.

    This is the SOLE AUTHORITY on trend direction.  Market providers
    initialise snapshots with neutral trends; this function enriches
    them using enabled indicators.

    When *htf_candles* and *ltf_candles* are provided (recommended), each
    timeframe is computed INDEPENDENTLY — they can genuinely disagree.
    If omitted, *candles* is used for both (backward-compatible).

    Args:
        candles: Default / base candle set.
        profile: Trading profile with indicator toggle flags.
        htf_candles: Higher-timeframe candles (e.g. resampled 1h from 5m).
        ltf_candles: Lower-timeframe candles (e.g. raw 5m candles).

    Returns:
        TrendConsensus with per-timeframe directions + merged vote trail.
    """
    htf = _compute_timeframe(htf_candles or candles, profile, label="HTF")
    mtf = _compute_timeframe(mtf_candles or candles, profile, label="MTF")
    ltf = _compute_timeframe(ltf_candles or candles, profile, label="LTF")
    exec_tf = _compute_timeframe(candles, profile, label="EXEC")

    # ── Regime Classification ──────────────────────────────────────────
    regime = _classify_regime(htf, ltf)

    # ── Multi-timeframe alignment ─────────────────────────────────────
    htf_align = (
        htf.direction == ltf.direction
        and htf.direction in ("long", "short")
    )

    # ── Combined consensus ────────────────────────────────────────────
    if htf_align:
        combined_dir = htf.direction
        combined_str = round((htf.strength + ltf.strength) / 2, 2)
    elif htf.direction in ("long", "short"):
        combined_dir = htf.direction
        combined_str = round(htf.strength * 0.75, 2)
    elif ltf.direction in ("long", "short"):
        combined_dir = ltf.direction
        combined_str = round(ltf.strength * 0.5, 2)
    else:
        combined_dir = "neutral"
        combined_str = 0.0

    # Merge vote trails
    merged_votes = htf.votes + mtf.votes + ltf.votes + exec_tf.votes

    return TrendConsensus(
        htf_dir=htf.direction,
        mtf_dir=mtf.direction,
        ltf_dir=ltf.direction,
        exec_dir=exec_tf.direction,
        htf_strength=htf.strength,
        mtf_strength=mtf.strength,
        ltf_strength=ltf.strength,
        exec_strength=exec_tf.strength,
        htf_align=htf_align,
        indicator_dir=combined_dir,
        indicator_strength=combined_str,
        htf_adx=htf.adx,
        rsi=htf.rsi,
        macd=htf.macd,
        supertrend=htf.supertrend,
        ema_ribbon=htf.ema_ribbon,
        bollinger=htf.bollinger,
        adx_data=htf.adx_data,
        vote_sources=merged_votes,
        market_regime=regime,
    )
