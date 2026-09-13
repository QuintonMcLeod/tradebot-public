from tradebot_sci.config import loader


def test_load_settings_env_override(monkeypatch):
    settings = loader.load_settings()
    assert isinstance(settings.ai.model_name, str) and len(settings.ai.model_name) > 0
    assert settings.app.profile_name is not None
    assert len(settings.profiles) > 0


def test_profile_env_overrides(monkeypatch):
    """Profile-level env overrides (PROFILE_HTF_TIMEFRAME etc.) are no longer
    applied by the loader — values come from YAML config only."""
    settings = loader.load_settings()
    profile = settings.get_active_profile()
    # Just verify the profile loads without error and has expected fields
    assert profile.htf_timeframe is not None
    assert isinstance(profile.pdt_guard_enabled, bool)


def test_safety_guards_enabled_by_default(monkeypatch):
    """Critical: safety guards MUST default to True to prevent unguarded capital bleed.

    See: capital_bleed_forensic_report.md — RC-1.  All six toggles previously
    defaulted to False, allowing 67 churned trades/day and $52 spread costs on
    a $135 account.
    """
    # Clear any env vars that might override defaults
    for var in [
        "SAFETY_DRAWDOWN_BREAKER_ENABLED",
        "SAFETY_STREAK_BREAKER_ENABLED",
        "SAFETY_CHURN_BURNER_ENABLED",
        "SAFETY_GREED_GUARD_ENABLED",
        "SAFETY_SESSION_LOCKOUT_ENABLED",
        "SAFETY_OPENING_SENTRY_ENABLED",
    ]:
        monkeypatch.delenv(var, raising=False)

    from tradebot_sci.config.models import SafetySettings
    s = SafetySettings()
    assert s.safety_drawdown_breaker_enabled is True, "Drawdown breaker must default to ON"
    assert s.safety_streak_breaker_enabled is True, "Streak breaker must default to ON"
    assert s.safety_churn_burner_enabled is True, "Churn burner must default to ON"
    assert s.safety_greed_guard_enabled is True, "Greed guard must default to ON"
    assert s.safety_session_lockout_enabled is True, "Session lockout must default to ON"
    assert s.safety_opening_sentry_enabled is True, "Opening sentry must default to ON"


def test_safety_fee_rate_default(monkeypatch):
    """Fee rate should default to OANDA spread cost (0.04%), not Gemini (0.8%)."""
    monkeypatch.delenv("SAFETY_FEE_RT_PCT", raising=False)
    from tradebot_sci.config.models import SafetySettings
    s = SafetySettings()
    assert s.safety_fee_rt_pct == 0.0004, f"Expected OANDA default 0.0004, got {s.safety_fee_rt_pct}"
