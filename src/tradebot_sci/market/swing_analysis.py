"""Shared swing point detection utilities for market structure analysis.

This module provides centralized swing detection logic to avoid duplication
across trend.py and icc_signals.py.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

from tradebot_sci.market.models import Candle

PriceGetter = Callable[[Candle], float]


def swing_points(candles: list[Candle], *, lookback: int = 2) -> tuple[list[int], list[int]]:
    """Return swing highs/lows using candle highs/lows (traditional fractal)."""
    return _adaptive_swing_points(
        candles,
        lookback=lookback,
        get_high=lambda c: c.high,
        get_low=lambda c: c.low,
        label="swing_points",
    )


def swing_points_close(candles: list[Candle], *, lookback: int = 2) -> tuple[list[int], list[int]]:
    """Return swing highs/lows using candle closes (body levels)."""
    return _adaptive_swing_points(
        candles,
        lookback=lookback,
        get_high=lambda c: c.close,
        get_low=lambda c: c.close,
        label="swing_points_close",
    )


def _adaptive_swing_points(
    candles: list[Candle],
    *,
    lookback: int,
    get_high: PriceGetter,
    get_low: PriceGetter,
    label: str,
) -> tuple[list[int], list[int]]:
    """Try progressively smaller lookbacks when strict detection fails."""
    if len(candles) < 3 or lookback < 1:
        _debug_log(label, len(candles), lookback, 0, 0, used_lookback=lookback)
        return [], []

    max_lookback = max(1, (len(candles) - 1) // 2)
    lookback = min(lookback, max_lookback)

    highest: list[int] = []
    lowest: list[int] = []
    used_lookback = 0

    for attempt in range(lookback, 0, -1):
        highs, lows = _find_swing_points(candles, attempt, get_high=get_high, get_low=get_low)
        if highs or lows:
            highest = highs
            lowest = lows
            used_lookback = attempt
            break

    _debug_log(label, len(candles), lookback, len(highest), len(lowest), used_lookback=used_lookback)
    return highest, lowest


def _find_swing_points(
    candles: list[Candle],
    lookback: int,
    *,
    get_high: PriceGetter,
    get_low: PriceGetter,
) -> tuple[list[int], list[int]]:
    highs: list[int] = []
    lows: list[int] = []

    span = len(candles) - lookback
    for i in range(lookback, span):
        left = candles[i - lookback : i]
        right = candles[i + 1 : i + 1 + lookback]

        current_high = get_high(candles[i])
        current_low = get_low(candles[i])

        neighbor_highs = [get_high(x) for x in left + right]
        if neighbor_highs:
            highest_neighbor = max(neighbor_highs)
            if current_high >= highest_neighbor and any(current_high > neighbor for neighbor in neighbor_highs):
                highs.append(i)

        neighbor_lows = [get_low(x) for x in left + right]
        if neighbor_lows:
            lowest_neighbor = min(neighbor_lows)
            if current_low <= lowest_neighbor and any(current_low < neighbor for neighbor in neighbor_lows):
                lows.append(i)

    return highs, lows


def _debug_log(label: str, length: int, requested: int, highs: int, lows: int, *, used_lookback: int) -> None:
    if os.getenv("DEBUG_TRENDS") == "1":
        print(
            f"[SWING] {label}: len={length}, requested={requested}, used={used_lookback}, highs={highs}, lows={lows}",
            file=sys.stderr,
            flush=True,
        )
