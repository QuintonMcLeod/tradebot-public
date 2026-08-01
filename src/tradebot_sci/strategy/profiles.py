from __future__ import annotations

from dataclasses import dataclass
from typing import Optional




@dataclass
class RegimeConfig:
    """Regime-aware trading parameters."""
    adx_flat_threshold: float = 15.0
    adx_trend_threshold: float = 20.0
    trend_target_r: float = 1.8
    range_target_r: float = 1.0
    trend_time_decay_bars: int = 36
    range_time_decay_bars: int = 12
    probe_size_pct: float = 0.25

@dataclass
class BaseProfile:
    """Defines how hyper or chilled the bot should be."""

    name: str
    candle_timeframe: str
    market_poll_interval_seconds: int
    ai_decision_interval_seconds: int
    target_r: float = 1.0
    regime_config: Optional[RegimeConfig] = None
    allowed_pairs: Optional[list] = None


@dataclass
class ScalpProfile(BaseProfile):
    """For the caffeine-powered scalper who thinks in seconds."""

    name: str = "scalp"
    candle_timeframe: str = "1m"
    market_poll_interval_seconds: int = 1
    ai_decision_interval_seconds: int = 60


@dataclass
class IntradayProfile(BaseProfile):
    """For the focused day-trader who still likes lunch breaks."""

    name: str = "intraday"
    candle_timeframe: str = "5m"
    market_poll_interval_seconds: int = 5
    ai_decision_interval_seconds: int = 300


@dataclass
class SwingProfile(BaseProfile):
    """For the patient swing-trader who checks charts between hobbies."""

    name: str = "swing"
    candle_timeframe: str = "1h"
    market_poll_interval_seconds: int = 60
    ai_decision_interval_seconds: int = 3600




@dataclass
class GBPUSDRegimeProfile(BaseProfile):
    """Regime-aware profile for GBPUSD on 5m timeframe."""
    name: str = "gbpusd_regime_v1"
    candle_timeframe: str = "5m"
    market_poll_interval_seconds: int = 5
    ai_decision_interval_seconds: int = 300
    target_r: float = 1.8
    regime_config: Optional[RegimeConfig] = None
    allowed_pairs: Optional[list] = None

def build_profile(profile_name: str) -> BaseProfile:
    """Returns a profile so the bot knows how frantic to be."""
    if profile_name == "scalp":
        return ScalpProfile()
    if profile_name == "swing":
        return SwingProfile()
    if profile_name == "gbpusd_regime_v1":
        return GBPUSDRegimeProfile()
    return IntradayProfile()
