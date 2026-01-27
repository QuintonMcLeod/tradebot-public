from __future__ import annotations

import logging
from typing import Optional, List, Any
from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.market.trend import swing_progress
from tradebot_sci.market.trend_enums import TrendDirection
from tradebot_sci.strategy.icc_signals import (
    detect_correction,
    detect_continuation,
    detect_indication,
    detect_liquidity_sweep,
    detect_no_trade_zone,
)

logger = logging.getLogger(__name__)

class SignalDetector:
    """Encapsulates ICC signal detection logic isolated from the engine."""

    @staticmethod
    def detect_sweep(snapshot: MarketSnapshot):
        ltf_dir = snapshot.trend_ltf.direction
        htf_dir = snapshot.trend_htf.direction

        if htf_dir not in {"long", "short", "neutral"}:
            return None

        trend_dir = ltf_dir if ltf_dir in {"long", "short"} else (
            htf_dir if htf_dir in {"long", "short"} else None
        )
        if trend_dir is None:
            return None

        if ltf_dir in {"long", "short"} and htf_dir in {"long", "short"} and htf_dir != ltf_dir:
            return None

        ltf_candles = snapshot.ltf_candles or snapshot.candles
        return detect_liquidity_sweep(ltf_candles, trend_dir, swing_lookback=2)

    @staticmethod
    def detect_continuation(snapshot: MarketSnapshot, sweep: Any, indication: Any, correction: Any = None, profile: Any = None):
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        ltf_dir = snapshot.trend_ltf.direction
        
        if ltf_dir not in {"long", "short"}:
            ltf_dir = snapshot.trend_htf.direction
            if ltf_dir not in {"long", "short"}:
                return None

        confirmation_bars = int(getattr(profile, "icc_confirmation_bars", 2))
        max_bars_after_sweep = int(getattr(profile, "icc_max_bars_after_sweep", 30))

        return detect_continuation(
            ltf_candles,
            ltf_dir,
            sweep,
            indication,
            correction=correction,
            require_sweep=False,
            require_indication=False,
            require_correction=False,
            max_bars_after_sweep=max_bars_after_sweep,
            swing_lookback=2,
            confirmation_bars=confirmation_bars,
        )

    @staticmethod
    def detect_indication(snapshot: MarketSnapshot):
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        return detect_indication(ltf_candles, swing_lookback=2)

    @staticmethod
    def detect_correction(snapshot: MarketSnapshot, indication: Any):
        if indication is None:
            return None
        ltf_candles = snapshot.ltf_candles or snapshot.candles
        return detect_correction(ltf_candles, indication, swing_lookback=2)

    @staticmethod
    def determine_phase(
        snapshot: MarketSnapshot,
        *,
        sweep: object | None = None,
        continuation: object | None = None,
        indication: object | None = None,
        correction: object | None = None,
    ) -> str:
        htf_candles = snapshot.htf_candles or snapshot.candles
        ntz = detect_no_trade_zone(htf_candles, swing_lookback=2)
        
        if ntz and not ntz.is_broken:
            return "chop"
            
        if continuation:
            return "continuation"
            
        if correction:
            return "correction"
            
        if indication or (ntz and ntz.is_broken):
            return "indication"
            
        return "chop"
