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
    """Log a message exactly once in the current process lifetime."""
    # Use the message as the key; including args makes it too specific
    # but for these audit logs it works well enough.
    key = msg
    if key not in _LOGGED_MESSAGES:
        logger.log(level, msg, *args)
        _LOGGED_MESSAGES.add(key)


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_path(path_str: str | None) -> str | None:
    if not path_str:
        return None
    p = Path(path_str)
    if p.is_absolute():
        return path_str
    return str(BASE_DIR / p)


def _apply_env_overrides(base_data: Dict[str, Any]) -> Dict[str, Any]:
    app_overrides = {
        "environment": os.getenv("APP_ENVIRONMENT"),
        "profile_name": os.getenv("PROFILE_NAME"),
    }
    app = {**base_data.get("app", {}), **{k: v for k, v in app_overrides.items() if v}}

    logging_overrides = {"level": os.getenv("LOG_LEVEL")}
    logging = {
        **base_data.get("logging", {}),
        **{k: v for k, v in logging_overrides.items() if v},
    }

    ai_overrides = {
        "provider": os.getenv("TRADE_SCI_PROVIDER"),
        "base_url": os.getenv("TRADE_SCI_API_BASE_URL"),
        "api_key": os.getenv("TRADE_SCI_API_KEY") or os.getenv("CHATGPT_KEY"),
        "model_name": os.getenv("TRADE_SCI_MODEL_NAME"),
        "temperature": _maybe_float(os.getenv("TRADE_SCI_TEMPERATURE")),
        "max_tokens": _maybe_int(os.getenv("TRADE_SCI_MAX_TOKENS")),
    }
    ai = {**base_data.get("ai", {}), **{k: v for k, v in ai_overrides.items() if v is not None}}

    def _split_symbols(value: str | None) -> list[str] | None:
        if not value:
            return None
        return [s.strip() for s in value.split(",") if s.strip()]

    market_overrides = {
        "exchange_provider": os.getenv("EXCHANGE_PROVIDER"),
        "market_data_mode": os.getenv("MARKET_DATA_MODE"),
        "broker_mode": os.getenv("BROKER_MODE"),
        "alternative_market_data": os.getenv("ALTERNATIVE_MARKET_DATA"),
        "alternative_broker": os.getenv("ALTERNATIVE_BROKER"),
        "default_symbol": os.getenv("MARKET_DEFAULT_SYMBOL"),
        "default_timeframe": os.getenv("MARKET_DEFAULT_TIMEFRAME"),
        "max_candles": _maybe_int(os.getenv("MARKET_MAX_CANDLES")),
        "symbols": _split_symbols(os.getenv("MARKET_SYMBOLS")),
    }
    market = {
        **base_data.get("market", {}),
        **{k: v for k, v in market_overrides.items() if v is not None},
    }

    runtime_overrides = {
        "cancel_orders_on_start": os.getenv("CANCEL_ORDERS_ON_START"),
        "flatten_on_exit": os.getenv("FLATTEN_ON_EXIT"),
        "intraday_flatten": os.getenv("INTRADAY_FLATTEN"),
        "allow_inherited_position": os.getenv("ALLOW_INHERITED_POSITION"),
        "scale_out_fraction": os.getenv("SCALE_OUT_FRACTION"),
        "min_position_size_to_scale": os.getenv("MIN_POSITION_SIZE_TO_SCALE"),
        "emergency_stop_pct": os.getenv("EMERGENCY_STOP_PCT"),
        "max_scale_ins_per_leg": os.getenv("MAX_SCALE_INS_PER_LEG"),
        "multi_position_enabled": os.getenv("MULTI_POSITION_ENABLED"),
        "max_concurrent_positions": os.getenv("MAX_CONCURRENT_POSITIONS"),
        "min_equity_for_margin": os.getenv("MIN_EQUITY_FOR_MARGIN"),
        "allow_day_trades": os.getenv("ALLOW_DAY_TRADES"),
        "min_hold_seconds": os.getenv("MIN_HOLD_SECONDS"),
        "auto_restart_on_error": os.getenv("AUTO_RESTART_ON_ERROR"),
        "auto_restart_stale_seconds": os.getenv("AUTO_RESTART_STALE_SECONDS"),
        "auto_restart_min_uptime_seconds": os.getenv("AUTO_RESTART_MIN_UPTIME_SECONDS"),
        "auto_restart_cooldown_seconds": os.getenv("AUTO_RESTART_COOLDOWN_SECONDS"),
    }
    runtime = {
        **base_data.get("runtime", {}),
        **{
            k: (
                float(v)
                if k in {"scale_out_fraction", "min_position_size_to_scale", "emergency_stop_pct", "min_equity_for_margin"}
                else int(v)
                if k
                in {
                    "max_scale_ins_per_leg",
                    "max_concurrent_positions",
                    "min_hold_seconds",
                    "auto_restart_stale_seconds",
                    "auto_restart_min_uptime_seconds",
                    "auto_restart_cooldown_seconds",
                }
                else v.lower() == "true"
            )
            for k, v in runtime_overrides.items()
            if v is not None
        },
    }

    return {"app": app, "logging": logging, "ai": ai, "market": market, "runtime": runtime}


def _maybe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _apply_profile_runtime_overrides(settings: Settings) -> None:
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        return
    overrides = getattr(profile, "runtime_overrides", None) or {}
    for key, value in overrides.items():
        if not hasattr(settings.runtime, key):
            logger.warning(
                "Unknown runtime override '%s' in profile '%s'; skipping",
                key,
                profile_name,
            )
            continue
        setattr(settings.runtime, key, value)

    # [ANTIGRAVITY FIX] Propagate direct profile overrides for multi-position mode
    # These fields are often set directly on the profile model, not just in runtime_overrides
    if getattr(profile, "multi_position_enabled", None) is not None:
        settings.runtime.multi_position_enabled = profile.multi_position_enabled
        logger.debug("Applying profile override: multi_position_enabled=%s", profile.multi_position_enabled)
    
    if getattr(profile, "max_concurrent_positions", None) is not None:
        settings.runtime.max_concurrent_positions = profile.max_concurrent_positions
        logger.debug("Applying profile override: max_concurrent_positions=%s", profile.max_concurrent_positions)


def _apply_profile_sabbath_overrides(settings: Settings) -> None:
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        return

    def _env_bool(key: str) -> bool | None:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return None
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        logger.warning("Invalid boolean for %s: %s", key, raw)
        return None

    enabled = _env_bool("SABBATH_ENABLED")
    if enabled is not None:
        profile.sabbath_enabled = enabled

    astro = _env_bool("SABBATH_ASTRONOMICAL")
    if astro is not None:
        profile.sabbath_astronomical = astro

    tz = os.getenv("SABBATH_TIMEZONE")
    if tz is not None and tz.strip():
        profile.sabbath_timezone = tz.strip()

    start_local = os.getenv("SABBATH_START_LOCAL")
    if start_local is not None and start_local.strip():
        profile.sabbath_start_local = start_local.strip()

    end_local = os.getenv("SABBATH_END_LOCAL")
    if end_local is not None and end_local.strip():
        profile.sabbath_end_local = end_local.strip()

    lat = _maybe_float(os.getenv("SABBATH_LAT"))
    if lat is not None:
        profile.sabbath_lat = lat

    lon = _maybe_float(os.getenv("SABBATH_LON"))
    if lon is not None:
        profile.sabbath_lon = lon


def _apply_profile_env_overrides(settings: Settings) -> None:
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        return

    def _env_bool(key: str) -> bool | None:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return None
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        logger.warning("Invalid boolean for %s: %s", key, raw)
        return None

    def _env_int(key: str) -> int | None:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return None
        return _maybe_int(raw)

    def _env_float(key: str) -> float | None:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return None
        return _maybe_float(raw)

    def _env_str(key: str) -> str | None:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return None
        return raw.strip()

    def _env_symbols(key: str) -> list[str] | None:
        raw = os.getenv(key)
        if raw is None:
            return None
        cleaned = raw.strip()
        if cleaned == "":
            return []
        return [s.strip() for s in cleaned.split(",") if s.strip()]

    def _set(attr: str, value: object | None) -> None:
        if value is not None and hasattr(profile, attr):
            setattr(profile, attr, value)

    _set("htf_timeframe", _env_str("PROFILE_HTF_TIMEFRAME"))
    raw_ltf = os.getenv("PROFILE_LTF_TIMEFRAME")
    if raw_ltf is not None:
        cleaned = raw_ltf.strip()
        if cleaned == "" or cleaned.lower() in {"auto", "default", "none"}:
            profile.ltf_timeframe = None
        else:
            profile.ltf_timeframe = cleaned

    _set("trend_window", _env_int("PROFILE_TREND_WINDOW"))
    _set("ltf_trend_window", _env_int("PROFILE_LTF_TREND_WINDOW"))
    _set("trend_swing_lookback", _env_int("PROFILE_TREND_SWING_LOOKBACK"))
    _set("trend_min_swings", _env_int("PROFILE_TREND_MIN_SWINGS"))
    _set("trend_strength_floor", _env_float("PROFILE_TREND_STRENGTH_FLOOR"))
    _set("session_gate_enabled", _env_bool("PROFILE_SESSION_GATE_ENABLED"))
    _set("session_gate_min_candles", _env_int("PROFILE_SESSION_GATE_MIN_CANDLES"))
    _set("session_range_multiplier", _env_float("PROFILE_SESSION_RANGE_MULTIPLIER"))
    _set("session_volume_multiplier", _env_float("PROFILE_SESSION_VOLUME_MULTIPLIER"))
    _set("session_overlap_start_hour", _env_int("PROFILE_SESSION_OVERLAP_START_HOUR"))
    _set("session_overlap_end_hour", _env_int("PROFILE_SESSION_OVERLAP_END_HOUR"))
    _set("session_overlap_timezone", _env_str("PROFILE_SESSION_OVERLAP_TIMEZONE"))
    _set("structure_score_threshold", _env_float("PROFILE_STRUCTURE_SCORE_THRESHOLD"))

    _set("pdt_guard_enabled", _env_bool("PROFILE_PDT_GUARD_ENABLED"))
    _set("max_equity_roundtrips_per_day", _env_int("PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY"))
    _set("flip_actions_enabled", _env_bool("PROFILE_FLIP_ACTIONS_ENABLED"))
    _set("flip_cooldown_seconds", _env_int("PROFILE_FLIP_COOLDOWN_SECONDS"))

    _set("cooldown_enabled", _env_bool("PROFILE_COOLDOWN_ENABLED"))
    _set("cooldown_cycles_after_block", _env_int("PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK"))
    _set("cooldown_cycles_after_success", _env_int("PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS"))
    _set("cooldown_scope", _env_str("PROFILE_COOLDOWN_SCOPE"))
    _set("stick_to_active_symbol_until", _env_str("PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL"))

    _set("auto_schedule_enabled", _env_bool("PROFILE_AUTO_SCHEDULE_ENABLED"))
    _set("auto_flatten_on_close", _env_bool("PROFILE_AUTO_FLATTEN_ON_CLOSE"))
    _set("continuous_mode", _env_bool("PROFILE_CONTINUOUS_MODE"))
    _set("crypto_only", _env_bool("PROFILE_CRYPTO_ONLY"))

    _set("icc_aggressive_mode", _env_bool("PROFILE_ICC_AGGRESSIVE_MODE"))
    _set("aggressive_risk_per_trade_pct", _env_float("PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT"))
    _set("max_daily_loss_pct", _env_float("PROFILE_MAX_DAILY_LOSS_PCT"))
    _set("max_exposure_pct", _env_float("PROFILE_MAX_EXPOSURE_PCT"))
    _set("max_consecutive_losses", _env_int("PROFILE_MAX_CONSECUTIVE_LOSSES"))
    _set("symbols", _env_symbols("PROFILE_SYMBOLS"))


def _enforce_profile_guardrails(settings: Settings) -> None:
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        return
    if getattr(profile, "pdt_guard_enabled", False) and getattr(profile, "auto_flatten_on_close", False):
        _log_once(
            logging.WARNING,
            "PDT guard enabled; forcing auto_flatten_on_close=false for profile '%s'",
            profile_name,
        )
        profile.auto_flatten_on_close = False

    # Auto-Resolve Crypto Conflicts (PDT / Hold Times)
    is_crypto = getattr(profile, "crypto_only", False) or getattr(profile, "crypto_only_profile", False)
    if not is_crypto:
        # Check Exchange Provider (CCXT = Crypto)
        # We assume 'alternative' implies our CCXT/Crypto backend, or explicit 'ccxt' provider.
        # We avoid hardcoding specific exchange names here to remain generic.
        provider = (getattr(settings.market, "exchange_provider", "") or "").lower()
        if provider == "alternative" or "ccxt" in provider or provider == "crypto":
            is_crypto = True

    if not is_crypto:
        # Fallback: check symbols if explicit flag is missing
        symbols = getattr(profile, "symbols", []) or []
        for s in symbols:
            if "BTC" in s or "ETH" in s or "SOL" in s or "DOGE" in s or "USDT" in s:
                is_crypto = True
                break

    if is_crypto:
        changes = []
        if getattr(profile, "pdt_guard_enabled", False):
            profile.pdt_guard_enabled = False
            changes.append("pdt_guard_enabled=False")
        
        hold_hours = float(getattr(profile, "min_hold_hours", 0.0) or 0.0)
        if hold_hours > 0.0:
            profile.min_hold_hours = 0.0
            changes.append(f"min_hold_hours=0.0 (was {hold_hours})")

        if changes:
             _log_once(
                logging.WARNING,
                "Audit: Crypto profile '%s' detected with conflicting settings. Auto-correcting: %s",
                profile_name,
                ", ".join(changes),
            )

    # 1. Intraday Profile + CCXT Warning
    if profile_name == "intraday" and is_crypto:
        _log_once(
            logging.WARNING,
            "Audit: 'intraday' profile selected with Crypto provider. "
            "Consider using 'crypto_247' or 'auto_schedule' for 24/7 markets."
        )

    # 2. Continuous Mode vs Intraday Flatten
    if getattr(profile, "continuous_mode", False) and settings.runtime.intraday_flatten:
        settings.runtime.intraday_flatten = False
        _log_once(logging.WARNING, "Audit: intraday_flatten disabled for continuous_mode profile '%s'", profile_name)

    # 3. Symbol List Mismatch Audit
    profile_symbols = set(getattr(profile, "symbols", []) or [])
    base_symbols = set(settings.market.symbols or [])
    # Only warn if both lists exist, are different, and pair selector isn't likely managing it entirely
    if profile_symbols and base_symbols and profile_symbols != base_symbols:
        _log_once(
            logging.INFO,
            "Audit: Profile symbols (%d) differ from base settings symbols (%d). Using Profile symbols.",
            len(profile_symbols), len(base_symbols)
        )

    # 4. PDT + High Roundtrip Limit
    if getattr(profile, "pdt_guard_enabled", False):
        max_rt = getattr(profile, "max_equity_roundtrips_per_day", 99)
        if max_rt > 3:
            _log_once(
                logging.INFO,
                "Audit: PDT guard enabled. Hard limit is 3 day trades/5 rolling days. "
                "Configured max_equity_roundtrips_per_day=%d is effectively overridden by regulatory rules.",
                max_rt
            )

    # 5. Pair Selector + Fixed Symbols
    if getattr(profile, "pair_selector_enabled", False) and getattr(profile, "symbols", []):
         _log_once(
             logging.INFO,
             "Audit: pair_selector_enabled=True with fixed symbols list. "
             "The fixed symbols will be used as the candidate pool (or initial universe)."
         )

    # 6. Crypto Fractional + Traditional Symbols
    if getattr(profile, "crypto_fractional_enabled", False):
        profile_symbols = getattr(profile, "symbols", []) or []
        non_crypto_symbols = []
        for sym in profile_symbols:
            # Check if symbol is NOT crypto (doesn't contain crypto ticker patterns)
            if not any(crypto_token in sym.upper() for crypto_token in
                      ["BTC", "ETH", "SOL", "DOGE", "USDT", "USDC", "XRP", "ADA", "MATIC", "AVAX"]):
                non_crypto_symbols.append(sym)

        if non_crypto_symbols:
            _log_once(
                logging.WARNING,
                "Audit: crypto_fractional_enabled=True but profile contains non-crypto symbols %s. "
                "Traditional brokers (IBKR) may reject fractional orders for these symbols.",
                non_crypto_symbols
            )

    # 7. Allow Day Trades + Min Hold Seconds (Ambiguous Settings)
    if not settings.runtime.allow_day_trades:
        min_hold_sec = settings.runtime.min_hold_seconds or 0
        if 0 < min_hold_sec < 3600:  # Less than 1 hour
            _log_once(
                logging.INFO,
                "Audit: allow_day_trades=False but min_hold_seconds=%d (< 1 hour). "
                "This combination is ambiguous. Clarify: use allow_day_trades=True for intraday, "
                "or set min_hold_seconds >= 3600 for overnight holds.",
                min_hold_sec
            )

    # 8. Local Stops + CCXT (Synthetic Stops Warning)
    if settings.runtime.allow_local_stops:
        provider = (getattr(settings.market, "exchange_provider", "") or "").lower()
        if provider in ("alternative", "ccxt", "crypto"):
            local_stop_syms = settings.runtime.local_stop_symbols or []
            if local_stop_syms:
                _log_once(
                    logging.INFO,
                    "Audit: allow_local_stops=True with CCXT/crypto provider. "
                    "Stop orders will be synthetic (bot-monitored) rather than native exchange stops. "
                    "Ensure bot remains running to honor stops."
                )

    # 9. Continuous Mode + Schedule Sessions (Potential Conflict)
    if getattr(profile, "continuous_mode", False):
        # Check if auto_schedule_enabled might create conflicts
        auto_schedule = getattr(profile, "auto_schedule_enabled", None)
        has_sessions = bool(getattr(settings.schedule, "sessions", []))

        if has_sessions and auto_schedule is not False:  # None or True
            _log_once(
                logging.INFO,
                "Audit: continuous_mode=True with scheduled sessions defined. "
                "Verify that auto_schedule_enabled is explicitly set to False if 24/7 operation is desired."
            )

    # 10. Sabbath + Continuous Mode (Intentional Check)
    if getattr(profile, "sabbath_enabled", False) and getattr(profile, "continuous_mode", False):
        _log_once(
            logging.INFO,
            "Audit: sabbath_enabled=True with continuous_mode=True. "
            "Trading will pause during Sabbath hours even in 24/7 crypto markets. "
            "If unintentional, disable sabbath_enabled."
        )

    # 11. Legacy exchange_provider vs New Mode Settings
    legacy_provider = (getattr(settings.market, "exchange_provider", "") or "").lower()
    broker_mode = (getattr(settings.market, "broker_mode", "") or "").lower()
    market_mode = (getattr(settings.market, "market_data_mode", "") or "").lower()

    if legacy_provider and (broker_mode or market_mode):
        # Check if legacy conflicts with new settings
        conflicts = []
        if broker_mode and legacy_provider != broker_mode:
            conflicts.append(f"broker_mode='{broker_mode}'")
        if market_mode and legacy_provider != market_mode:
            conflicts.append(f"market_data_mode='{market_mode}'")

        if conflicts:
            _log_once(
                logging.WARNING,
                "Audit: exchange_provider='%s' conflicts with %s. "
                "Legacy exchange_provider may override newer mode settings. "
                "Recommend using only broker_mode/market_data_mode for clarity.",
                legacy_provider, ", ".join(conflicts)
            )

    # 12. Coinbase Provider + 4h Timeframe (Unsupported Granularity)
    htf = getattr(profile, "htf_timeframe", "4h")
    alt_data = (getattr(settings.market, "alternative_market_data", "") or "").lower()

    if htf == "4h" and "coinbase" in alt_data:
        _log_once(
            logging.INFO,
            "Audit: HTF timeframe '4h' with Coinbase provider. "
            "Coinbase API will remap 4h to 6h (closest supported granularity). "
            "Consider using htf_timeframe='6h' explicitly to match actual data."
        )


def load_settings() -> Settings:
    # Force override=True so that changes to .env (e.g. via GUI) take precedence
    # over the stale environment variables inherited from the long-running tmux session.
    # explicit path helps if CWD is somehow wrong.
    dotenv_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=True)
    base_raw = _load_yaml(BASE_SETTINGS_FILE)
    profiles_raw = _load_yaml(PROFILE_SETTINGS_FILE)

    merged = _apply_env_overrides(base_raw)

    profiles_config = profiles_raw.get("profiles", {})
    profiles = {
        name: TradingProfileSettings(**profile_data)
        for name, profile_data in profiles_config.items()
    }

    schedule_cfg = base_raw.get("schedule", {}) or {}
    schedule = ScheduleSettings(**schedule_cfg) if schedule_cfg else ScheduleSettings()
    runtime_cfg = merged.get("runtime", {}) or base_raw.get("runtime", {}) or {}
    runtime = RuntimeSettings(**runtime_cfg) if runtime_cfg else RuntimeSettings()

    # Broker optional
    broker_path = CONFIG_DIR / "broker_ibkr.yaml"
    broker_settings = None
    if broker_path.exists():
        broker_settings = load_ibkr_broker_options(broker_path)

    market_settings = MarketSettings(**merged["market"])
    configure_crypto_routing(market_settings.crypto_routing)
    settings = Settings(
        app=AppSettings(**merged["app"]),
        logging=LoggingSettings(**merged["logging"]),
        ai=AISettings(**merged["ai"]),
        market=market_settings,
        profiles=profiles,
        runtime=runtime,
        schedule=schedule,
        broker=broker_settings,
    )

    # Resolve relative paths to absolute project paths
    settings.logging.file = _resolve_path(settings.logging.file) or settings.logging.file
    settings.runtime.position_hold_store_path = (
        _resolve_path(settings.runtime.position_hold_store_path)
        or settings.runtime.position_hold_store_path
    )
    for p in settings.profiles.values():
        p.synthetic_stop_store_path = _resolve_path(p.synthetic_stop_store_path) or p.synthetic_stop_store_path

    _apply_profile_runtime_overrides(settings)
    _apply_profile_sabbath_overrides(settings)
    _apply_profile_env_overrides(settings)
    _enforce_profile_guardrails(settings)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
