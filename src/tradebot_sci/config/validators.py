"""Configuration validation utilities.

This module provides validation functions for profile settings and configuration
to catch errors early and provide helpful error messages.
"""
from __future__ import annotations

from typing import Any


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""

    pass


def validate_profile_settings(profile_settings: Any) -> None:
    """Validate profile settings for common errors.

    Args:
        profile_settings: Profile settings object to validate

    Raises:
        ConfigValidationError: If validation fails
    """
    # Validate session range multiplier
    range_mult = getattr(profile_settings, "session_range_multiplier", None)
    if range_mult is not None and range_mult < 1.0:
        raise ConfigValidationError(
            f"session_range_multiplier must be >= 1.0, got {range_mult}. "
            f"Values < 1.0 would require range compression, not expansion."
        )

    # Validate session volume multiplier
    vol_mult = getattr(profile_settings, "session_volume_multiplier", None)
    if vol_mult is not None and vol_mult < 1.0:
        raise ConfigValidationError(
            f"session_volume_multiplier must be >= 1.0, got {vol_mult}. "
            f"Values < 1.0 would require volume decline, not expansion."
        )

    # Validate trend strength floor
    strength_floor = getattr(profile_settings, "trend_strength_floor", None)
    if strength_floor is not None:
        if not (0.0 <= strength_floor <= 1.0):
            raise ConfigValidationError(
                f"trend_strength_floor must be between 0.0 and 1.0, got {strength_floor}."
            )

    # Validate trend window
    trend_window = getattr(profile_settings, "trend_window", None)
    if trend_window is not None and trend_window < 1:
        raise ConfigValidationError(
            f"trend_window must be >= 1, got {trend_window}. "
            f"At least 1 candle is required for trend analysis."
        )

    # Validate swing lookback
    swing_lookback = getattr(profile_settings, "trend_swing_lookback", None)
    if swing_lookback is not None and swing_lookback < 1:
        raise ConfigValidationError(
            f"trend_swing_lookback must be >= 1, got {swing_lookback}. "
            f"Swing detection requires at least 1 bar lookback on each side."
        )

    # Validate minimum swings
    min_swings = getattr(profile_settings, "trend_min_swings", None)
    if min_swings is not None and min_swings < 2:
        raise ConfigValidationError(
            f"trend_min_swings must be >= 2, got {min_swings}. "
            f"At least 2 swings are needed to determine trend direction."
        )

    # Validate risk percentages
    aggressive_risk = getattr(profile_settings, "aggressive_risk_per_trade_pct", None)
    if aggressive_risk is not None:
        if not (0.0 < aggressive_risk <= 1.0):
            raise ConfigValidationError(
                f"aggressive_risk_per_trade_pct must be between 0.0 and 1.0, got {aggressive_risk}. "
                f"Use fractional values (e.g., 0.03 for 3%)."
            )

    max_daily_loss = getattr(profile_settings, "max_daily_loss_pct", None)
    if max_daily_loss is not None:
        if not (0.0 < max_daily_loss <= 1.0):
            raise ConfigValidationError(
                f"max_daily_loss_pct must be between 0.0 and 1.0, got {max_daily_loss}. "
                f"Use fractional values (e.g., 0.06 for 6%)."
            )

    max_exposure = getattr(profile_settings, "max_exposure_pct", None)
    if max_exposure is not None:
        if not (0.0 < max_exposure <= 1.0):
            raise ConfigValidationError(
                f"max_exposure_pct must be between 0.0 and 1.0, got {max_exposure}. "
                f"Use fractional values (e.g., 0.40 for 40%)."
            )

    # Validate session overlap hours
    start_hour = getattr(profile_settings, "session_overlap_start_hour", None)
    if start_hour is not None:
        if not (0 <= start_hour <= 23):
            raise ConfigValidationError(
                f"session_overlap_start_hour must be between 0 and 23, got {start_hour}."
            )

    end_hour = getattr(profile_settings, "session_overlap_end_hour", None)
    if end_hour is not None:
        if not (0 <= end_hour <= 23):
            raise ConfigValidationError(
                f"session_overlap_end_hour must be between 0 and 23, got {end_hour}."
            )

    # Validate PDT settings
    max_roundtrips = getattr(profile_settings, "max_equity_roundtrips_per_day", None)
    if max_roundtrips is not None and max_roundtrips < 0:
        raise ConfigValidationError(
            f"max_equity_roundtrips_per_day must be >= 0, got {max_roundtrips}."
        )

    # Validate cooldown settings
    cooldown_cycles = getattr(profile_settings, "cooldown_cycles_after_block", None)
    if cooldown_cycles is not None and cooldown_cycles < 0:
        raise ConfigValidationError(
            f"cooldown_cycles_after_block must be >= 0, got {cooldown_cycles}."
        )


def validate_settings(settings: Any) -> None:
    """Validate main settings object.

    Args:
        settings: Settings object to validate

    Raises:
        ConfigValidationError: If validation fails
    """
    # Validate market settings
    if hasattr(settings, "market"):
        max_candles = getattr(settings.market, "max_candles", None)
        if max_candles is not None and max_candles < 10:
            raise ConfigValidationError(
                f"market.max_candles must be >= 10, got {max_candles}. "
                f"At least 10 candles are needed for meaningful analysis."
            )

    # Validate AI settings
    if hasattr(settings, "ai"):
        max_tokens = getattr(settings.ai, "max_tokens", None)
        if max_tokens is not None and max_tokens < 100:
            raise ConfigValidationError(
                f"ai.max_tokens must be >= 100, got {max_tokens}. "
                f"Too few tokens will truncate AI responses."
            )

        temperature = getattr(settings.ai, "temperature", None)
        if temperature is not None:
            if not (0.0 <= temperature <= 2.0):
                raise ConfigValidationError(
                    f"ai.temperature must be between 0.0 and 2.0, got {temperature}."
                )
