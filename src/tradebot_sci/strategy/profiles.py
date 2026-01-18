from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BaseProfile:
    """Defines how hyper or chilled the bot should be."""

    name: str
    candle_timeframe: str
    market_poll_interval_seconds: int
    ai_decision_interval_seconds: int


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


def build_profile(profile_name: str) -> BaseProfile:
    """Returns a profile so the bot knows how frantic to be."""
    if profile_name == "scalp":
        return ScalpProfile()
    if profile_name == "swing":
        return SwingProfile()
    return IntradayProfile()
