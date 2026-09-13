"""Shared test helpers for the tradebot-sci refactor.

The canonical configuration model no longer stores operational settings on
`TradingProfileSettings`.  Tests that used to build a profile with fields like
`market_poll_interval_seconds`, `risk_per_trade_pct`, or `sabbath_enabled` must
now place those fields in the top-level canonical sections (`runtime`, `risk`,
`safety`, `performance`) and attach the resulting `Settings` object to the active
profile so the backward-compat shim resolves test-specific values.
"""
from __future__ import annotations

from typing import Any

from tradebot_sci.config.models import (
    AppSettings,
    AISettings,
    LoggingSettings,
    MarketSettings,
    PerformanceSettings,
    RiskSettings,
    RuntimeSettings,
    SafetySettings,
    ScheduleSettings,
    Settings,
    TradingProfileSettings,
    RoboCopSettings,
)


# Profile-level keys that survived the refactor and are still valid on
# TradingProfileSettings.
_PROFILE_FIELDS = {
    "name",
    "strategy_variant",
    "strategies",
    "symbols",
    "candle_timeframe",
    "htf_timeframe",
    "mtf_timeframe",
    "ltf_timeframe",
    "xtf_timeframe",
    "risk_dynamic_auto",
    "continuous_mode",
}


def make_test_settings(
    profile_name: str = "test",
    profile_overrides: dict[str, Any] | None = None,
    **section_overrides: Any,
) -> Settings:
    """Build a Settings object suitable for unit tests.

    Any keyword argument whose name is a known profile field goes into the active
    profile; everything else is treated as a canonical-section override and is
    forwarded to the matching top-level section (`runtime`, `risk`, `safety`,
    `performance`, `market`, `ai`, `robocop`, `schedule`, `logging`).
    """
    profile_overrides = profile_overrides or {}
    profile_kwargs: dict[str, Any] = {}
    canonical_kwargs: dict[str, dict[str, Any]] = {}

    for key, value in section_overrides.items():
        if key in _PROFILE_FIELDS:
            profile_kwargs[key] = value
        else:
            # Determine which canonical section owns this field.
            target_section = _section_for_field(key)
            canonical_kwargs.setdefault(target_section, {})[key] = value

    profile_kwargs.update(profile_overrides)

    profiles = {profile_name: TradingProfileSettings(**profile_kwargs)}

    return Settings(
        app=AppSettings(profile_name=profile_name),
        logging=LoggingSettings(**canonical_kwargs.get("logging", {})),
        ai=AISettings(**canonical_kwargs.get("ai", {})),
        market=MarketSettings(**canonical_kwargs.get("market", {})),
        runtime=RuntimeSettings(**canonical_kwargs.get("runtime", {})),
        risk=RiskSettings(**canonical_kwargs.get("risk", {})),
        safety=SafetySettings(**canonical_kwargs.get("safety", {})),
        performance=PerformanceSettings(**canonical_kwargs.get("performance", {})),
        robocop=RoboCopSettings(**canonical_kwargs.get("robocop", {})),
        schedule=ScheduleSettings(**canonical_kwargs.get("schedule", {})),
        profiles=profiles,
    )


def make_test_profile(**overrides: Any) -> TradingProfileSettings:
    """Build an active profile with attached canonical Settings.

    This is a drop-in replacement for the old ``TradingProfileSettings(**kwargs)``
    calls in tests.  Operational fields are promoted to canonical sections and the
    resulting ``Settings`` object is attached as ``profile._settings`` so the
    profile's backward-compat ``__getattr__`` resolves test-specific values.
    """
    settings = make_test_settings(**overrides)
    profile = settings.get_active_profile()
    profile._settings = settings  # type: ignore[attr-defined]
    return profile


def _section_for_field(name: str) -> str:
    """Return the canonical section that owns a given operational field.

    The lookup order matches the order used by the profile backward-compat
    shim (risk, safety, performance, runtime) so that test values resolve
    correctly when code reads them via ``profile.field``.
    """
    if name in RiskSettings.model_fields:
        return "risk"
    if name in SafetySettings.model_fields:
        return "safety"
    if name in PerformanceSettings.model_fields:
        return "performance"
    if name in RuntimeSettings.model_fields:
        return "runtime"
    if name in MarketSettings.model_fields:
        return "market"
    if name in AISettings.model_fields:
        return "ai"
    if name in RoboCopSettings.model_fields:
        return "robocop"
    if name in ScheduleSettings.model_fields:
        return "schedule"
    if name in LoggingSettings.model_fields:
        return "logging"
    # Unknown fields are treated as runtime by default; this keeps tests that
    # pass ad-hoc keys (e.g. custom test toggles) from crashing.
    return "runtime"
