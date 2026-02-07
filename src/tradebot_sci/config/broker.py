from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BrokerSettings(BaseModel):
    """Loads your IBKR secrets so the bot can talk to your broker without rage-quitting."""

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=7497)
    client_id: int = Field(default=123)
    account_id: str = Field(default="DU1234567")
    use_paper_trading: bool = Field(default=True)
    read_only: bool = Field(default=True)
    default_currency: str = Field(default="USD")
    execution_mode: str = Field(default="simulate")  # simulate|paper|live
    max_shares_per_symbol: int = Field(default=5, description="Per-symbol share cap")
    max_dollar_risk_per_symbol: float = Field(
        default=3.0, description="Per-symbol dollar risk cap across open brackets"
    )
    max_dollar_risk_per_account: float | None = Field(
        default=None, description="Optional aggregate account risk cap"
    )
    auto_risk_fraction_of_buying_power: float | None = Field(
        default=0.001,
        description=(
            "Optional fraction of account buying power to use as per-symbol dollar risk. "
            "If set, overrides max_dollar_risk_per_symbol when accountSummary is available."
        ),
    )


class OandaSettings(BaseModel):
    """Configuration for OANDA v20 API."""
    account_id: str = Field(default="")
    api_key: str = Field(default="")
    environment: Literal["practice", "live"] = Field(default="practice")
    read_only: bool = Field(default=True)


def load_ibkr_broker_options(config_path: Optional[Path] = None, data: Optional[dict] = None) -> BrokerSettings:
    """Scoops IBKR settings from JSON data, YAML, or env so you don't have to babysit defaults."""
    if data:
        # Use provided JSON data
        filtered_data = {k: v for k, v in data.items() if v is not None}
        return BrokerSettings(**filtered_data)

    # Fallback to legacy YAML/Env logic
    if config_path:
        path = Path(config_path)
    else:
        try_paths = [
            Path(__file__).resolve().parents[4] / "config" / "broker_ibkr.yaml",  # project root
            Path(__file__).resolve().parents[3] / "config" / "broker_ibkr.yaml",  # fallback: cwd/src/config
            Path.cwd() / "config" / "broker_ibkr.yaml",  # last resort
        ]
        path = next((p for p in try_paths if p.exists()), try_paths[0])

    data = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        # environment fallback for the brave
        data = {
            "host": os.getenv("IBKR_HOST"),
            "port": os.getenv("IBKR_PORT"),
            "client_id": os.getenv("IBKR_CLIENT_ID"),
            "account_id": os.getenv("IBKR_ACCOUNT_ID"),
            "use_paper_trading": os.getenv("IBKR_PAPER", "true").lower() == "true",
            "read_only": os.getenv("IBKR_READ_ONLY", "true").lower() == "true",
            "default_currency": os.getenv("IBKR_DEFAULT_CCY", "USD"),
        }
    # Env overrides apply on top of YAML (GUI writes .env; we want it to take effect without editing YAML).
    env_overrides: dict[str, object] = {}
    if os.getenv("IBKR_HOST"):
        env_overrides["host"] = os.getenv("IBKR_HOST")
    if os.getenv("IBKR_PORT"):
        try:
            env_overrides["port"] = int(os.getenv("IBKR_PORT") or "0")
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_PORT: {e}")
            pass
    if os.getenv("IBKR_CLIENT_ID"):
        try:
            env_overrides["client_id"] = int(os.getenv("IBKR_CLIENT_ID") or "0")
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_CLIENT_ID: {e}")
            pass
    if os.getenv("IBKR_ACCOUNT_ID"):
        env_overrides["account_id"] = os.getenv("IBKR_ACCOUNT_ID")
    if os.getenv("IBKR_PAPER") is not None:
        env_overrides["use_paper_trading"] = (os.getenv("IBKR_PAPER") or "").lower() == "true"
    if os.getenv("IBKR_READ_ONLY") is not None:
        env_overrides["read_only"] = (os.getenv("IBKR_READ_ONLY") or "").lower() == "true"
    if os.getenv("IBKR_DEFAULT_CCY"):
        env_overrides["default_currency"] = os.getenv("IBKR_DEFAULT_CCY")
    if os.getenv("IBKR_EXECUTION_MODE"):
        env_overrides["execution_mode"] = os.getenv("IBKR_EXECUTION_MODE")
    if os.getenv("IBKR_MAX_SHARES_PER_SYMBOL"):
        try:
            env_overrides["max_shares_per_symbol"] = int(os.getenv("IBKR_MAX_SHARES_PER_SYMBOL") or "0")
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_MAX_SHARES_PER_SYMBOL: {e}")
            pass
    if os.getenv("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL"):
        try:
            env_overrides["max_dollar_risk_per_symbol"] = float(os.getenv("IBKR_MAX_DOLLAR_RISK_PER_SYMBOL") or "0")
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_MAX_DOLLAR_RISK_PER_SYMBOL: {e}")
            pass
    if os.getenv("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT"):
        try:
            env_overrides["max_dollar_risk_per_account"] = float(os.getenv("IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT") or "0")
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT: {e}")
            pass
    if os.getenv("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER"):
        try:
            env_overrides["auto_risk_fraction_of_buying_power"] = float(
                os.getenv("IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER") or "0"
            )
        except Exception as e:
            logger.warning(f"Failed to parse IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER: {e}")
            pass
    if env_overrides:
        data = {**(data or {}), **env_overrides}
    # filter out Nones to let Pydantic use defaults
    data = {k: v for k, v in data.items() if v is not None}
    return BrokerSettings(**data)

def load_oanda_broker_options(data: Optional[dict] = None) -> OandaSettings:
    """Loads OANDA credentials from provided data or environment variables."""
    if data:
        # Basic validation of environment
        if "environment" in data and data["environment"] not in ["practice", "live"]:
            data["environment"] = "practice"
        return OandaSettings(**data)

    data = {
        "account_id": os.getenv("OANDA_ACCOUNT_ID", ""),
        "api_key": os.getenv("OANDA_API_KEY", ""),
        "environment": os.getenv("OANDA_ENVIRONMENT", "practice").lower(),
        "read_only": os.getenv("OANDA_READ_ONLY", "true").lower() == "true",
    }
    # Basic validation of environment
    if data["environment"] not in ["practice", "live"]:
        data["environment"] = "practice"
    return OandaSettings(**data)


class PaxosSettings(BaseModel):
    """Configuration for Paxos (itBit) API."""
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    environment: Literal["sandbox", "production"] = Field(default="sandbox")


def load_paxos_broker_options(data: Optional[dict] = None) -> PaxosSettings:
    """Loads Paxos credentials from provided data or environment variables."""
    if data:
        if "environment" in data and data["environment"] not in ["sandbox", "production"]:
            data["environment"] = "sandbox"
        return PaxosSettings(**data)

    data = {
        "api_key": os.getenv("PAXOS_API_KEY", ""),
        "api_secret": os.getenv("PAXOS_API_SECRET", ""),
        "environment": os.getenv("PAXOS_ENVIRONMENT", "sandbox").lower(),
    }
    # Basic validation
    if data["environment"] not in ["sandbox", "production"]:
        data["environment"] = "sandbox"
    return PaxosSettings(**data)

class KrakenSettings(BaseModel):
    """Configuration for Kraken API."""
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    environment: Literal["sandbox", "production"] = Field(default="production")


def load_kraken_broker_options(data: Optional[dict] = None) -> KrakenSettings:
    """Loads Kraken credentials from provided data or environment variables."""
    if data:
        if "environment" in data and data["environment"] not in ["sandbox", "production"]:
            data["environment"] = "production"
        return KrakenSettings(**data)

    data = {
        "api_key": os.getenv("KRAKEN_API_KEY", ""),
        "api_secret": os.getenv("KRAKEN_API_SECRET", ""),
        "environment": os.getenv("KRAKEN_ENVIRONMENT", "production").lower(),
    }
    if data["environment"] not in ["sandbox", "production"]:
        data["environment"] = "production"
    return KrakenSettings(**data)
