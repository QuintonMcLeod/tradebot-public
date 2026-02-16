from __future__ import annotations

import json
import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

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
    SafetySettings,
    PerformanceSettings,
    OandaSettings,
    PaxosSettings,
    KrakenSettings,
)
from tradebot_sci.config.broker import (
    BrokerSettings, 
    load_ibkr_broker_options,
    load_oanda_broker_options,
    load_paxos_broker_options,
    load_kraken_broker_options,
)
from tradebot_sci.market.contracts import configure_crypto_routing

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_JSON_FILE = BASE_DIR / "config.json"
SECRETS_FILE = BASE_DIR / ".env.secrets"

# Legacy paths (for fallback if config.json doesn't exist yet)
CONFIG_DIR = BASE_DIR / "config"
LEGACY_BASE_SETTINGS_FILE = CONFIG_DIR / "settings_base.yaml"
LEGACY_PROFILE_SETTINGS_FILE = CONFIG_DIR / "settings_profiles.yaml"

logger = logging.getLogger(__name__)

_LOGGED_MESSAGES = set()


def _log_once(level: int, msg: str, *args: Any) -> None:
    key = msg
    if key not in _LOGGED_MESSAGES:
        logger.log(level, msg, *args)
        _LOGGED_MESSAGES.add(key)


def _load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON file, return empty dict if missing."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Legacy YAML loader for fallback."""
    if not path.exists():
        return {}
    import yaml
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

def _load_from_json(config: Dict[str, Any]) -> Settings:
    """Map config.json dictionary to Settings model."""
    app_cfg = config.get("global", {})
    # Map 'active_profile' from root to app.profile_name
    active_profile = config.get("active_profile") or config.get("APP_PROFILE")
    
    # If no profile specified or requested one doesn't exist in the profiles dict, 
    # we don't crash here, get_active_profile() will handle the fallback.
    app_cfg["profile_name"] = active_profile or "auto_schedule"
    
    log_cfg = config.get("logging", {})
    
    # Robustly fetch AI settings
    g_cfg = config.get("global", {})
    ai_raw = config.get("ai", {})
    ai_model_cfg = {
        "provider": ai_raw.get("provider") or g_cfg.get("trade_sci_provider") or os.getenv("TRADE_SCI_PROVIDER", "openai"),
        "base_url": ai_raw.get("base_url") or g_cfg.get("trade_sci_api_base_url") or os.getenv("TRADE_SCI_API_BASE_URL", "https://api.openai.com/v1"),
        "api_key": ai_raw.get("api_key") or os.getenv("TRADE_SCI_API_KEY") or os.getenv("CHATGPT_KEY"),
        "model_name": ai_raw.get("model_name") or g_cfg.get("trade_sci_model_name") or os.getenv("TRADE_SCI_MODEL_NAME", "trade-sci-max-icc"),
        "temperature": ai_raw.get("temperature") or g_cfg.get("trade_sci_temperature") or float(os.getenv("TRADE_SCI_TEMPERATURE", "0.2")),
        "max_tokens": ai_raw.get("max_tokens") or g_cfg.get("trade_sci_max_tokens") or int(os.getenv("TRADE_SCI_MAX_TOKENS", "2048")),
    }
    
    # Robustly fetch market/broker modes from potentially inconsistent JSON
    # It might be in 'global', 'market', or even 'brokers'
    m_cfg = config.get("market", {})
    b_cfg = config.get("brokers", {})
    
    market_data_mode = m_cfg.get("market_data_mode") or g_cfg.get("market_data_mode") or os.getenv("MARKET_DATA_MODE", "primary")
    broker_mode = m_cfg.get("broker_mode") or b_cfg.get("broker_mode") or g_cfg.get("broker_mode") or os.getenv("BROKER_MODE", "primary")
    exchange_provider = m_cfg.get("exchange_provider") or g_cfg.get("exchange_provider") or os.getenv("EXCHANGE_PROVIDER", "primary")
    primary_market_provider = m_cfg.get("primary_market_provider") or g_cfg.get("primary_provider") or os.getenv("PRIMARY_PROVIDER", exchange_provider)
    primary_broker = b_cfg.get("primary_broker") or m_cfg.get("primary_broker") or g_cfg.get("primary_broker") or os.getenv("PRIMARY_BROKER", exchange_provider)



    market_cfg = {
        "market_data_mode": market_data_mode,
        "broker_mode": broker_mode,
        "exchange_provider": exchange_provider,
        "primary_market_provider": primary_market_provider,
        "primary_broker": primary_broker,
        "primary_forex": b_cfg.get("primary_forex") or m_cfg.get("primary_forex") or g_cfg.get("primary_forex") or os.getenv("PRIMARY_FOREX", "oanda"),
        "primary_crypto": b_cfg.get("primary_crypto") or m_cfg.get("primary_crypto") or g_cfg.get("primary_crypto") or os.getenv("PRIMARY_CRYPTO", "gemini"),
        "primary_equities": b_cfg.get("primary_equities") or m_cfg.get("primary_equities") or g_cfg.get("primary_equities") or os.getenv("PRIMARY_EQUITIES", "disabled"),
        "alternative_market_data": m_cfg.get("alternative_market_data") or g_cfg.get("alternative_market_data") or "ccxt",
        "alternative_broker": m_cfg.get("alternative_broker") or g_cfg.get("alternative_broker") or "ccxt",
        "default_symbol": m_cfg.get("default_symbol") or g_cfg.get("market_default_symbol") or "SPY",
        "default_timeframe": m_cfg.get("default_timeframe") or g_cfg.get("market_default_timeframe") or "5m",
        "max_candles": m_cfg.get("max_candles") or g_cfg.get("market_max_candles") or 200,
        "trading_confirmation": config.get("trading_confirmation") or g_cfg.get("trading_confirmation") or os.getenv("TRADING_CONFIRMATION"),
    }

    runtime_cfg = config.get("global", {}) # Many runtime settings are in global
    # [ANTIGRAVITY FIX] The settings UI writes runtime fields (time_format,
    # pnl_timeframe, global_default_risk_pct, etc.) to config["runtime"].
    # Merge those in so they aren't silently dropped.
    runtime_cfg.update(config.get("runtime", {}))
    risk_model_cfg = config.get("risk", {})
    schedule_cfg = config.get("schedule", {})

    # ── Inject global risk/ICC values into profiles as defaults ──
    # Risk & ICC are now stored in the global "risk" section (set by
    # the UI's "Global Risk Limits" / "ICC Settings" panels).  We
    # merge them into each profile as defaults so that every broker
    # and strategy reading profile.risk_per_trade_pct etc. gets the
    # global value automatically.  Profile-specific overrides still
    # win if present.
    _PROMOTED_RISK_KEYS = [
        "risk_per_trade_pct", "risk_per_trade_dollars",
        "aggressive_risk_per_trade_pct", "max_exposure_pct", "limit_loss_daily_pct",
        "icc_auto_entry_enabled", "icc_aggressive_mode", "icc_entry_score_threshold",
        "icc_auto_entry_require_sweep", "icc_auto_entry_min_htf_strength",
        "icc_two_signal_override_enabled", "icc_auto_entry_cooldown_minutes",
        "icc_score_continuation_points", "icc_score_sweep_points",
        "icc_score_htf_ltf_align_points", "icc_score_strong_htf_points",
        "icc_score_phase_points", "icc_score_indication_points",
        "icc_score_htf_strength_threshold",
    ]

    _profile_fields = set(TradingProfileSettings.model_fields.keys())

    profiles = {}
    for name, p_data in config.get("profiles", {}).items():
        merged = dict(p_data)  # shallow copy
        for key in _PROMOTED_RISK_KEYS:
            if key not in merged and key in risk_model_cfg and key in _profile_fields:
                merged[key] = risk_model_cfg[key]
        profiles[name] = TradingProfileSettings(**merged)

    brokers_cfg = config.get("brokers", {})
    
    # Inject Secrets into Broker Configs before loading
    # (since brokers_cfg from config.json won't have the API keys)
    oanda_data = brokers_cfg.get("oanda", {})
    if not oanda_data.get("api_key"):
        oanda_data["api_key"] = os.getenv("OANDA_API_KEY", "")
    
    ibkr_data = brokers_cfg.get("ibkr", {})
    
    gemini_data = brokers_cfg.get("gemini", {})
    if not gemini_data.get("api_key"):
        gemini_data["api_key"] = os.getenv("GEMINI_API_KEY", "")
    if not gemini_data.get("api_secret"):
        gemini_data["api_secret"] = os.getenv("GEMINI_API_SECRET", "")
        
    ccxt_data = brokers_cfg.get("ccxt", {})
    if not ccxt_data.get("api_key"):
        ccxt_data["api_key"] = os.getenv("CCXT_API_KEY", "")
    if not ccxt_data.get("secret"):
        ccxt_data["secret"] = os.getenv("CCXT_SECRET", "")
    
    # [ANTIGRAVITY] Sync CCXT settings to Environment Variables
    if ccxt_data.get("exchange"):
        os.environ["CCXT_EXCHANGE"] = ccxt_data["exchange"]
    if ccxt_data.get("default_type"):
        os.environ["CCXT_DEFAULT_TYPE"] = ccxt_data["default_type"]

    # Broker Options
    ibkr_cfg = load_ibkr_broker_options(data=ibkr_data)
    oanda_cfg = load_oanda_broker_options(data=oanda_data)
    paxos_cfg = load_paxos_broker_options(data=brokers_cfg.get("paxos"))
    kraken_cfg = load_kraken_broker_options(data=brokers_cfg.get("kraken"))



    settings = Settings(
        app=AppSettings(**app_cfg),
        logging=LoggingSettings(**log_cfg),
        ai=AISettings(**ai_model_cfg),
        market=MarketSettings(**market_cfg),
        runtime=RuntimeSettings(**runtime_cfg),
        risk=RiskSettings(**risk_model_cfg),
        safety=SafetySettings(**config.get("safety", {})),
        performance=PerformanceSettings(**config.get("performance", {})),
        robocop=RoboCopSettings(),  # Use defaults
        schedule=ScheduleSettings(**schedule_cfg),
        profiles=profiles,
        broker=ibkr_cfg,
        oanda=oanda_cfg,
        paxos=paxos_cfg,
        kraken=kraken_cfg,
    )
    
    return settings


def _auto_migrate_legacy_config() -> None:
    """
    Auto-detect and migrate legacy config files (.env, YAML) to config.json.
    
    This runs on first startup after updating to the new config system.
    If config.json already exists, this does nothing.
    If legacy files exist, they are migrated and then removed.
    """
    import json
    import re
    import shutil
    from datetime import datetime
    
    # Skip if config.json already exists
    if CONFIG_JSON_FILE.exists():
        return
    
    legacy_env = BASE_DIR / ".env"
    legacy_profiles = LEGACY_PROFILE_SETTINGS_FILE
    legacy_base = LEGACY_BASE_SETTINGS_FILE
    
    # Check if any legacy files exist
    has_legacy = legacy_env.exists() or legacy_profiles.exists() or legacy_base.exists()
    if not has_legacy:
        logger.info("[CONFIG] No config files found. Creating default config.json...")
        _create_default_config()
        return
    
    logger.warning("=" * 60)
    logger.warning("[CONFIG] Legacy config files detected - MIGRATING AUTOMATICALLY")
    logger.warning("=" * 60)
    
    # Create backup directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BASE_DIR / "config_backup" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Backup legacy files
    for f in [legacy_env, legacy_profiles, legacy_base]:
        if f.exists():
            shutil.copy2(f, backup_dir / f.name)
            logger.info(f"[CONFIG] Backed up: {f.name}")
    
    # Parse legacy .env
    env_data = {}
    if legacy_env.exists():
        with open(legacy_env, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
                if match:
                    key, value = match.groups()
                    value = value.strip('"').strip("'")
                    env_data[key] = value
    
    # Parse legacy YAML profiles
    profiles_data = {}
    if legacy_profiles.exists():
        import yaml
        with open(legacy_profiles, "r") as f:
            profiles_yaml = yaml.safe_load(f) or {}
            profiles_data = profiles_yaml.get("profiles", {})
    
    # Secret keys to extract
    SECRET_KEYS = {
        "TRADE_SCI_API_KEY", "CHATGPT_KEY", "OANDA_API_KEY",
        "GEMINI_API_KEY", "GEMINI_API_SECRET", "CCXT_API_KEY",
        "CCXT_SECRET", "PAXOS_API_KEY", "PAXOS_API_SECRET",
    }
    
    # Build new config structure
    # Robustly determine the initial active profile from env or YAML keys
    default_active = env_data.get("APP_PROFILE")
    if not default_active and profiles_data:
        # Fallback to the first profile found in YAML if no env override
        default_active = next(iter(profiles_data))
    
    default_active = default_active or "auto_schedule"

    secrets = {}
    config = {
        "active_profile": default_active,
        "global": {},
        "brokers": {"ibkr": {}, "oanda": {}, "gemini": {}, "ccxt": {}},
        "ai": {},
        "safety": {},
        "performance": {},
        "risk": {},
        "profiles": profiles_data,
    }
    
    # Categorize env keys
    for key, value in env_data.items():
        # Convert value types
        if value.lower() == "true":
            val = True
        elif value.lower() == "false":
            val = False
        else:
            try:
                val = float(value) if "." in value else int(value)
            except ValueError:
                val = value
        
        key_upper = key.upper()
        
        if key_upper in SECRET_KEYS:
            secrets[key] = value
        elif key.startswith("IBKR_"):
            config["brokers"]["ibkr"][key.replace("IBKR_", "").lower()] = val
        elif key.startswith("OANDA_"):
            config["brokers"]["oanda"][key.replace("OANDA_", "").lower()] = val
        elif key.startswith("GEMINI_"):
            config["brokers"]["gemini"][key.replace("GEMINI_", "").lower()] = val
        elif key.startswith("CCXT_"):
            config["brokers"]["ccxt"][key.replace("CCXT_", "").lower()] = val
        elif any(x in key_upper for x in ["BROKER", "PRIMARY"]):
            config["brokers"][key.lower()] = val
        elif any(x in key_upper for x in ["SAFETY_", "SABBATH", "GUARD", "EMERGENCY"]):
            config["safety"][key.lower()] = val
        elif any(x in key_upper for x in ["PERFORMANCE_", "TRAILING_"]):
            config["performance"][key.lower()] = val
        elif any(x in key_upper for x in ["RISK_", "MAX_LOSS", "MAX_DAILY"]):
            config["risk"][key.lower()] = val
        elif key.startswith("PROFILE_"):
            # Add to active profile
            clean_key = key.replace("PROFILE_", "").lower()
            active = config["active_profile"]
            if active in config["profiles"]:
                config["profiles"][active][clean_key] = val
        else:
            config["global"][key.lower()] = val
    
    # Write new config.json
    with open(CONFIG_JSON_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    logger.info(f"[CONFIG] Created: config.json ({len(config['profiles'])} profiles)")
    
    # Write secrets file
    with open(SECRETS_FILE, "w") as f:
        f.write("# API Keys and Secrets - DO NOT COMMIT TO GIT\n\n")
        for key, value in sorted(secrets.items()):
            f.write(f"{key}={value}\n")
    logger.info(f"[CONFIG] Created: .env.secrets ({len(secrets)} keys)")
    
    # Remove legacy files
    for f in [legacy_env, legacy_profiles, legacy_base]:
        if f.exists():
            f.unlink()
            logger.info(f"[CONFIG] Removed legacy file: {f.name}")
    
    logger.warning("=" * 60)
    logger.warning("[CONFIG] MIGRATION COMPLETE - Using new config.json")
    logger.warning(f"[CONFIG] Backups saved to: {backup_dir}")
    logger.warning("=" * 60)


def _create_default_config() -> None:
    """Create a minimal default config.json for first-time users."""
    import json
    
    default_config = {
        "active_profile": "default",
        "global": {
            "bot_mode": "continuous",
            "execute_trades": False,
            "log_level": "INFO",
        },
        "brokers": {
            "primary_forex": "oanda",
            "primary_crypto": "gemini",
            "ibkr": {},
            "oanda": {},
            "gemini": {},
            "ccxt": {},
        },
        "ai": {
            "provider": "deepseek",
            "model": "deepseek-chat",
        },
        "safety": {
            "pdt_guard_enabled": False,
            "sabbath_enabled": False,
        },
        "performance": {},
        "risk": {
            "max_daily_loss_pct": 0.05,
        },
        "profiles": {
            "default": {
                "symbols": ["EURUSD", "BTCUSD"],
                "strategies": {"forex": "meta_sci", "crypto": "meta_sci"},
                "risk_per_trade_pct": 0.01,
            }
        },
    }
    
    with open(CONFIG_JSON_FILE, "w") as f:
        json.dump(default_config, f, indent=2)
    logger.info("[CONFIG] Created default config.json - Please configure your settings!")


def load_settings() -> Settings:
    """Main entry point for loading and merging configuration."""
    # 1. Load secrets from .env.secrets (API keys only)
    if SECRETS_FILE.exists():
        load_dotenv(dotenv_path=SECRETS_FILE, override=True)
    
    # Auto-migrate legacy config if needed
    _auto_migrate_legacy_config()
    
    # 2. Check for new config.json (preferred)
    if CONFIG_JSON_FILE.exists():
        logger.info("[CONFIG] Loading from config.json")
        config = _load_json(CONFIG_JSON_FILE)
        settings = _load_from_json(config)
    else:
        # Fallback to legacy YAML loading
        logger.warning("[CONFIG] config.json not found, falling back to YAML files")
        import yaml
        base_raw = _load_yaml(LEGACY_BASE_SETTINGS_FILE)
        profiles_raw = _load_yaml(LEGACY_PROFILE_SETTINGS_FILE)
        
        app_cfg = base_raw.get("app", {})
        env_profile = os.getenv("APP_PROFILE") or os.getenv("PROFILE_NAME")
        if env_profile:
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
    
    # 3. Handle Legacy Optional Broker Configs (Deprecated)
    if not CONFIG_JSON_FILE.exists():
        broker_path = CONFIG_DIR / "broker_ibkr.yaml"
        if broker_path.exists():
            settings.broker = load_ibkr_broker_options(broker_path)
        
        settings.oanda = load_oanda_broker_options()

    # 4. Post-initialization normalization
    settings.logging.file = _resolve_path(settings.logging.file) or settings.logging.file
    settings.runtime.position_hold_store_path = _resolve_path(settings.runtime.position_hold_store_path) or settings.runtime.position_hold_store_path
    
    for p in settings.profiles.values():
        p.synthetic_stop_store_path = _resolve_path(p.synthetic_stop_store_path) or p.synthetic_stop_store_path

    # 5. Final safety audit
    configure_crypto_routing(settings.market.crypto_routing)
    _enforce_profile_guardrails(settings)

    # Final safety check: Ensure profiles is not empty
    if not settings.profiles:
        logger.warning("[CONFIG] No profiles found in config. Adding default profile.")
        settings.profiles["default"] = TradingProfileSettings(
            name="default",
            symbols=["EURUSD", "BTCUSD"],
            strategies={"forex": "meta_sci", "crypto": "meta_sci"}
        )
        if settings.app.profile_name not in settings.profiles:
            settings.app.profile_name = "default"

    # [ANTIGRAVITY DEBUG]
    logger.info(f"[CONFIG] load_settings complete. Active profile: {settings.app.profile_name}. Available profiles: {list(settings.profiles.keys())}")

    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reload_settings() -> Settings:
    """Forces a reload of settings from disk (clears cache)."""
    get_settings.cache_clear()
    logger.info("[CONFIG] Reloading settings from disk...")
    return get_settings()


def save_settings_to_json(settings_dict: Dict[str, Any]) -> None:
    """Save settings dictionary back to config.json."""
    with open(CONFIG_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(settings_dict, f, indent=2, ensure_ascii=False)
    logger.info("[CONFIG] Saved config.json")


def load_config_json() -> Dict[str, Any]:
    """Load config.json as a raw dictionary (for GUI editing)."""
    return _load_json(CONFIG_JSON_FILE)
