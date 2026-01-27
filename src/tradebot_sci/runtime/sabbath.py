from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradebot_sci.config.models import TradingProfileSettings

logger = logging.getLogger(__name__)

try:
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_AVAILABLE = True
except ImportError:
    LocationInfo = None
    sun = None
    ASTRAL_AVAILABLE = False


def _parse_local_time(value: str) -> tuple[int, int]:
    hour, minute = map(int, value.split(":"))
    return hour, minute


def _compute_sabbath_window(
    reference: datetime,
    profile: TradingProfileSettings,
    allow_astronomical: bool,
) -> tuple[datetime, datetime, bool, bool]:
    tz = ZoneInfo(profile.sabbath_timezone)
    local_ref = reference.astimezone(tz)
    days_since_friday = (local_ref.weekday() - 4) % 7
    friday_date = (local_ref - timedelta(days=days_since_friday)).date()
    start_hour, start_minute = _parse_local_time(profile.sabbath_start_local)
    end_hour, end_minute = _parse_local_time(profile.sabbath_end_local)
    start = datetime(
        friday_date.year,
        friday_date.month,
        friday_date.day,
        start_hour,
        start_minute,
        tzinfo=tz,
    )
    saturday_date = friday_date + timedelta(days=1)
    end_fixed = datetime(
        saturday_date.year,
        saturday_date.month,
        saturday_date.day,
        end_hour,
        end_minute,
        tzinfo=tz,
    )
    if (
        allow_astronomical
        and profile.sabbath_astronomical
        and profile.sabbath_lat is not None
        and profile.sabbath_lon is not None
        and ASTRAL_AVAILABLE
        and LocationInfo is not None
        and sun is not None
    ):
        try:
            location = LocationInfo(
                name="sabbath",
                region="",
                timezone=profile.sabbath_timezone,
                latitude=profile.sabbath_lat,
                longitude=profile.sabbath_lon,
            )
            friday_sun = sun(location.observer, date=friday_date, tzinfo=tz)
            saturday_sun = sun(location.observer, date=saturday_date, tzinfo=tz)
            return friday_sun["sunset"], saturday_sun["sunset"], True, False
        except Exception as e:
            logger.warning(f"Failed to compute astronomical sabbath window: {e}")
            return start, end_fixed, False, True
    return start, end_fixed, False, False


class SabbathContext:
    """Manages Sabbath checking logic and state logging mapping to UI."""
    def __init__(self, profile: TradingProfileSettings, override: bool | None = None) -> None:
        self.profile = profile
        self.override = override
        self.timezone = ZoneInfo(profile.sabbath_timezone)
        self._log_counter = 0
        self._last_active: bool | None = None
        self._log_rate = 10
        self._astral_fallback_logged = False

    @property
    def enabled(self) -> bool:
        if self.override is not None:
            return self.override
        return bool(self.profile.sabbath_enabled)

    def log_startup(self) -> None:
        now = datetime.now(self.timezone)
        start, end, _, astral_failed = _compute_sabbath_window(
            now, self.profile, allow_astronomical=self.profile.sabbath_astronomical
        )
        logger.info(
            "[SABBATH] enabled=%s override=%s timezone=%s now=%s window_start=%s window_end=%s astral=%s lat=%s lon=%s",
            self.enabled,
            self.override,
            self.profile.sabbath_timezone,
            now.isoformat(),
            start.isoformat(),
            end.isoformat(),
            self.profile.sabbath_astronomical and ASTRAL_AVAILABLE,
            self.profile.sabbath_lat,
            self.profile.sabbath_lon,
        )
        if astral_failed and not self._astral_fallback_logged:
            logger.warning("[SABBATH] astral_unavailable=true; falling back to fixed window")
            self._astral_fallback_logged = True

    def evaluate(self, reference: datetime) -> tuple[bool, datetime, datetime]:
        if not self.enabled:
            return False, reference, reference
        local_ref = reference.astimezone(self.timezone)
        start, end, _, astral_failed = _compute_sabbath_window(
            local_ref, self.profile, allow_astronomical=self.profile.sabbath_astronomical
        )
        active = start <= local_ref < end
        remaining = max(0.0, (end - local_ref).total_seconds()) if active else 0.0
        if astral_failed and not self._astral_fallback_logged:
            logger.warning("[SABBATH] astral_unavailable=true; falling back to fixed window")
            self._astral_fallback_logged = True
        self._log_counter += 1
        if self._last_active is None or self._last_active != active or self._log_counter >= self._log_rate:
            logger.info(
                "[SABBATH] sabbath_active=%s time_now_local=%s window_start_local=%s window_end_local=%s remaining_block_duration=%.1f",
                active,
                local_ref.isoformat(),
                start.isoformat(),
                end.isoformat(),
                remaining,
            )
            self._log_counter = 0
            self._last_active = active
        return active, start, end
