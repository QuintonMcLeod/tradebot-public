from datetime import datetime

import pytest
from zoneinfo import ZoneInfo

from helpers import make_test_profile
from tradebot_sci.runtime.loop import _is_sabbath_now


def _make_profile(**overrides):
    defaults = {
        "candle_timeframe": "5m",
        "market_poll_interval_seconds": 10,
        "ai_decision_interval_seconds": 30,
        "sabbath_enabled": True,
        "sabbath_timezone": "America/New_York",
    }
    defaults.update(overrides)
    return make_test_profile(**defaults)


def test_sabbath_fixed_times_boundaries():
    profile = _make_profile(
        sabbath_start_local="18:00",
        sabbath_end_local="18:00",
    )
    tz = ZoneInfo(profile.sabbath_timezone)
    before = datetime(2025, 12, 12, 17, 59, tzinfo=tz)
    active, _ = _is_sabbath_now(before, profile, True)
    assert not active
    at_start = datetime(2025, 12, 12, 18, 0, tzinfo=tz)
    active, end = _is_sabbath_now(at_start, profile, True)
    assert active
    assert end.date() == datetime(2025, 12, 12, tzinfo=tz).date()
    just_before_end = datetime(2025, 12, 13, 17, 59, tzinfo=tz)
    active, _ = _is_sabbath_now(just_before_end, profile, True)
    assert active
    after_end = datetime(2025, 12, 13, 18, 0, tzinfo=tz)
    active, _ = _is_sabbath_now(after_end, profile, True)
    assert not active


def test_sabbath_timezone_round_trip():
    profile = _make_profile(sabbath_timezone="Europe/London")
    tz = ZoneInfo("Europe/London")
    dt = datetime(2025, 12, 12, 18, 1, tzinfo=tz)
    active, end = _is_sabbath_now(dt, profile, True)
    assert active
    assert end.tzinfo == tz


def test_astronomical_fallback_without_astral():
    profile = _make_profile(
        sabbath_astronomical=True,
        sabbath_lat=40.0,
        sabbath_lon=-73.0,
    )
    tz = ZoneInfo(profile.sabbath_timezone)
    dt = datetime(2025, 12, 12, 19, 0, tzinfo=tz)
    active, _ = _is_sabbath_now(dt, profile, True)
    assert isinstance(active, bool)
