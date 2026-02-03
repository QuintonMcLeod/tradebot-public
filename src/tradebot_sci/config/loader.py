from __future__ import annotations

import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

from .models import (
    AISettings,
    AppSettings,
    LoggingSettings,
    MarketSettings,
    RuntimeSettings,
    ScheduleSettings,
    Settings,
    TradingProfileSettings,
    RiskSettings,
    RoboCopSettings,
)
from tradebot_sci.config.broker import BrokerSettings, load_ibkr_broker_options
from tradebot_sci.market.contracts import configure_crypto_routing

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
BASE_SETTINGS_FILE = CONFIG_DIR / "settings_base.yaml"
PROFILE_SETTINGS_FILE = CONFIG_DIR / "settings_profiles.yaml"

logger = logging.getLogger(__name__)

_LOGGED_MESSAGES = set()

def _log_once(level: int, msg: str, *args: Any) -> None:
    key = msg
    if key not in _LOGGED_MESSAGES:
        logger.log(level, msg, *args)
        _LOGGED_MESSAGES.add(key)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_path(path_str: str | None) -> str | None:
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_absolute():
        return path_str
    return str(BASE_DIR / p)


def _enforce_profile_guardrails(settings: Settings) -> None:
    """Enforce domain-specific safety rules across settings components."""
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        return

    # 1. PDT Guard vs Auto-Flatten
    if getattr(profile, "pdt_guard_enabled", False) and getattr(profile, "auto_flatten_on_close", False):
        _log_once(
            logging.WARNING,
            "PDT guard enabled; forcing auto_flatten_on_close=false for profile '%s'",
            profile_name,
        )
        profile.auto_flatten_on_close = False

    # 2. Crypto Mode Detection & Auto-Correction
    is_crypto = getattr(profile, "crypto_only", False)
    provider = settings.market.broker_mode
    if provider in ("alternative", "coinbase_futures") or "ccxt" in provider:
        is_crypto = True

    if is_crypto:
        if getattr(profile, "pdt_guard_enabled", False):
            profile.pdt_guard_enabled = False
            _log_once(logging.WARNING, "Crypto profile '%s': disabling PDT guard (not applicable).", profile_name)
        
        if getattr(profile, "min_hold_hours", 0.0) > 0:
            profile.min_hold_hours = 0.0
            _log_once(logging.WARNING, "Crypto profile '%s': zeroing min_hold_hours.", profile_name)

    # 3. Continuous Mode vs Intraday Flatten
    if getattr(profile, "continuous_mode", False) and settings.runtime.intraday_flatten:
        settings.runtime.intraday_flatten = False
        _log_once(logging.WARNING, "intraday_flatten disabled for continuous_mode profile '%s'", profile_name)


def load_settings() -> Settings:
    """Main entry point for loading and merging configuration."""
    # 1. Load environment variables from .env
    dotenv_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=True)

    # 2. Load YAML base and profiles
    base_raw = _load_yaml(BASE_SETTINGS_FILE)
    profiles_raw = _load_yaml(PROFILE_SETTINGS_FILE)

    # 3. Initialize components (Pydantic handles environment overrides via default_factories)
    # We pass YAML data for keys that exist in YAML; others will fall back to Env/Defaults.
    app_cfg = base_raw.get("app", {})
    # Override profile name from Env if present
    env_profile = os.getenv("APP_PROFILE") or os.getenv("PROFILE_NAME")
    if env_profile:
        print(f"DEBUG: Loader resolved profile_name override to '{env_profile}'")
        app_cfg["profile_name"] = env_profile

    settings = Settings(
        app=AppSettings(**app_cfg),
        logging=LoggingSettings(**base_raw.get("logging", {})),
        ai=AISettings(**base_raw.get("ai", {})),
        market=MarketSettings(**base_raw.get("market", {})),
        runtime=RuntimeSettings(**base_raw.get("runtime", {})),
        risk=RiskSettings(**base_raw.get("risk", {})),
        robocop=RoboCopSettings(**base_raw.get("robocop", {})),
        schedule=ScheduleSettings(**base_raw.get("schedule", {})),
        profiles={
            name: TradingProfileSettings(name=name, **p_data)
            for name, p_data in profiles_raw.get("profiles", {}).items()
        }
    )

    # 4. Handle Optional Broker Configs
    broker_path = CONFIG_DIR / "broker_ibkr.yaml"
    if broker_path.exists():
        settings.broker = load_ibkr_broker_options(broker_path)
    
    from tradebot_sci.config.broker import load_oanda_broker_options
    settings.oanda = load_oanda_broker_options()

    # 5. Post-initialization normalization
    settings.logging.file = _resolve_path(settings.logging.file) or settings.logging.file
    settings.runtime.position_hold_store_path = _resolve_path(settings.runtime.position_hold_store_path) or settings.runtime.position_hold_store_path
    
    for p in settings.profiles.values():
        p.synthetic_stop_store_path = _resolve_path(p.synthetic_stop_store_path) or p.synthetic_stop_store_path

    # 6. Final safety audit
    configure_crypto_routing(settings.market.crypto_routing)
    _enforce_profile_guardrails(settings)

    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

def reload_settings() -> Settings:
    """Forces a reload of settings from disk (clears cache)."""
    get_settings.cache_clear()
    logger.info("[CONFIG] Reloading settings from disk...")
    return get_settings()
