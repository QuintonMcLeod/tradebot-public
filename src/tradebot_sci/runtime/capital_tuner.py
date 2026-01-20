from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.schemas import ChatMessage
from tradebot_sci.config.models import Settings

logger = logging.getLogger(__name__)

AUTO_TUNE_ENABLED_ENV = "ICC_CAPITAL_TUNE_AUTO"
AUTO_TUNE_LAST_TS_ENV = "ICC_CAPITAL_TUNE_LAST_TS"
AUTO_TUNE_LAST_EQUITY_ENV = "ICC_CAPITAL_TUNE_LAST_EQUITY"
AUTO_TUNE_LAST_BROKER_ENV = "ICC_CAPITAL_TUNE_LAST_BROKER"

ALLOWED_TUNE_KEYS: dict[str, tuple[str, float, float, int]] = {
    "PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT": ("float", 0.0, 1.0, 3),
    "PROFILE_MAX_DAILY_LOSS_PCT": ("float", 0.0, 1.0, 3),
    "PROFILE_MAX_EXPOSURE_PCT": ("float", 0.0, 1.0, 3),
    "PROFILE_MAX_CONSECUTIVE_LOSSES": ("int", 1.0, 50.0, 0),
    "IBKR_MAX_DOLLAR_RISK_PER_SYMBOL": ("float", 0.0, 1_000_000.0, 2),
    "IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT": ("float", 0.0, 10_000_000.0, 2),
    "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER": ("float", 0.0, 1.0, 4),
}


@dataclass(frozen=True)
class CapitalTuneResult:
    equity: float
    broker: str
    overrides: dict[str, str]
    notes: str


def sanitize_context(values: dict[str, Any], *, redact_keys: set[str] | None = None) -> dict[str, str]:
    redacted = redact_keys or set()
    cleaned: dict[str, str] = {}
    for key, raw in values.items():
        if key in redacted:
            continue
        upper = key.upper()
        if upper.endswith(("_KEY", "_SECRET", "_TOKEN", "_PASSWORD")):
            continue
        if any(tag in upper for tag in ("SECRET", "TOKEN", "PASSWORD")):
            continue
        text = "" if raw is None else str(raw)
        if len(text) > 240:
            text = text[:240] + "..."
        cleaned[key] = text
    return cleaned


def load_log_excerpt(path: str, *, max_lines: int = 200, max_chars: int = 8_000) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    lines = text.splitlines()
    tail = lines[-max_lines:] if max_lines > 0 else lines
    excerpt = "\n".join(tail)
    if len(excerpt) > max_chars:
        excerpt = excerpt[-max_chars:]
    return excerpt


def merge_dotenv(path: Path, updates: dict[str, str]) -> None:
    """Merge updates into a .env file, preserving existing content."""
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    present: set[str] = set()
    out_lines: list[str] = []
    for raw in existing:
        line = raw
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                k = stripped[:eq_pos].strip()
                if k in updates:
                    line = f"{k}={updates[k]}"
                    present.add(k)
        out_lines.append(line)
    for k, v in sorted(updates.items()):
        if k not in present:
            out_lines.append(f"{k}={v}")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _format_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _clean_equity(value: Any) -> float | None:
    try:
        val = float(value)
    except Exception:
        return None
    if val <= 0:
        return None
    return val


def _parse_ibkr_equity(summary_rows: list[Any], default_ccy: str) -> float | None:
    preferred_tags = ("NetLiquidation", "TotalCashValue", "BuyingPower")
    for tag in preferred_tags:
        for row in summary_rows:
            if str(getattr(row, "tag", "")).strip() != tag:
                continue
            if str(getattr(row, "currency", "")).upper() != default_ccy:
                continue
            val = _clean_equity(getattr(row, "value", None))
            if val is not None:
                return val
    return None


def fetch_account_equity(settings: Settings) -> tuple[float | None, str]:
    provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
    if provider == "primary":
        try:
            from ib_insync import IB  # type: ignore
        except Exception as exc:
            return None, f"ib_insync missing: {exc}"

        created_loop = False
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            created_loop = True

        host = os.getenv("IBKR_HOST", "127.0.0.1")
        port = int(os.getenv("IBKR_PORT", "7497"))
        acct = os.getenv("IBKR_ACCOUNT_ID", "").strip()
        default_ccy = (os.getenv("IBKR_DEFAULT_CCY", "") or "USD").strip().upper()
        ib = IB()
        try:
            ib.connect(host, port, clientId=(int(time.time()) % 10_000) + 13, timeout=3.0)
            summary = ib.accountSummary(acct) if acct else ib.accountSummary()
            equity = _parse_ibkr_equity(summary, default_ccy)
            if equity is None:
                return None, "accountSummary missing NetLiquidation/TotalCashValue"
            return equity, f"IBKR:{default_ccy}"
        except Exception as exc:
            return None, f"IBKR fetch failed: {exc}"
        finally:
            try:
                if ib.isConnected():
                    ib.disconnect()
            except Exception:
                pass
            if created_loop and loop is not None:
                try:
                    loop.close()
                except Exception:
                    pass

    alt_broker = (os.getenv("ALTERNATIVE_BROKER") or settings.market.alternative_broker or "").strip().lower()
    if alt_broker == "ccxt":
        try:
            import ccxt  # type: ignore
        except Exception as exc:
            return None, f"ccxt missing: {exc}"
        exchange_id = os.getenv("CCXT_EXCHANGE", "").strip()
        if not exchange_id:
            return None, "CCXT_EXCHANGE not set"
        try:
            exchange_cls = getattr(ccxt, exchange_id)
        except AttributeError:
            return None, f"Unknown CCXT exchange: {exchange_id}"
        kwargs = {}
        if os.getenv("CCXT_ENABLE_RATE_LIMIT", "").strip().lower() in {"1", "true", "yes"}:
            kwargs["enableRateLimit"] = True
        exchange = exchange_cls(kwargs)
        api_key = os.getenv("CCXT_API_KEY", "").strip()
        secret = os.getenv("CCXT_SECRET", "").strip()
        password = os.getenv("CCXT_PASSWORD", "").strip()
        if api_key:
            exchange.apiKey = api_key
        if secret:
            exchange.secret = secret
        if password:
            exchange.password = password
        if os.getenv("CCXT_SANDBOX", "").strip().lower() in {"1", "true", "yes"}:
            exchange.set_sandbox_mode(True)
        try:
            balance = exchange.fetch_balance()
        except Exception as exc:
            return None, f"CCXT fetch_balance failed: {exc}"
        total = balance.get("total") or {}
        for key in ("USD", "USDC", "USDT"):
            val = _clean_equity(total.get(key))
            if val is not None:
                return val, f"CCXT:{key}"
        return None, "CCXT balance missing USD/USDC/USDT"

    if alt_broker == "mock":
        return 10000.0, "MOCK"

    return None, f"Unsupported broker provider: {provider}/{alt_broker}"


def _format_value(key: str, value: float) -> str:
    value_type, min_val, max_val, decimals = ALLOWED_TUNE_KEYS[key]
    if value_type == "int":
        clamped = int(max(min_val, min(max_val, round(value))))
        return str(clamped)
    clamped = max(min_val, min(max_val, value))
    fmt = f"{{:.{decimals}f}}".format(clamped)
    return fmt.rstrip("0").rstrip(".") if decimals > 0 else fmt


def sanitize_overrides(overrides: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, raw in overrides.items():
        if key not in ALLOWED_TUNE_KEYS:
            continue
        try:
            val = float(raw)
        except Exception:
            continue
        cleaned[key] = _format_value(key, val)
    return cleaned


def request_capital_tune(
    settings: Settings,
    *,
    equity: float,
    broker: str,
    profile_name: str,
    current: dict[str, str],
    context: dict[str, str] | None = None,
    log_excerpt: str | None = None,
) -> CapitalTuneResult:
    allowed_keys = ", ".join(sorted(ALLOWED_TUNE_KEYS.keys()))
    context_json = json.dumps(context, indent=2) if context else "{}"
    log_payload = log_excerpt.strip() if log_excerpt else ""
    log_section = (
        "Recent log excerpt (if present):\n"
        f"{log_payload}\n\n"
        if log_payload
        else ""
    )
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": (
                "You are an ICC/ICT risk calibration assistant. "
                "Return a single JSON object with keys: overrides (object) and notes (string). "
                "Only include overrides you recommend changing."
            ),
        },
        {
            "role": "user",
            "content": (
                "Account equity and context:\n"
                f"- equity: {equity:.2f}\n"
                f"- broker: {broker}\n"
                f"- profile: {profile_name}\n\n"
                "Current calibration-relevant settings:\n"
                f"{json.dumps(current, indent=2)}\n\n"
                "Full settings context (read-only, for understanding only):\n"
                f"{context_json}\n\n"
                f"{log_section}"
                "Return JSON like:\n"
                "{\n"
                '  "overrides": { "IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER": 0.0025 },\n'
                '  "notes": "Short rationale."\n'
                "}\n\n"
                f"Allowed override keys: {allowed_keys}\n"
                "If you do not want to change a key, omit it."
            ),
        },
    ]
    client = TradeSciAIClient(settings.ai)
    content = client.raw_chat(messages, expect_json=True)
    try:
        data = json.loads(content)
    except Exception as exc:
        raise ValueError(f"AI response was not valid JSON: {exc}") from exc
    overrides_raw = data.get("overrides", data) if isinstance(data, dict) else {}
    if not isinstance(overrides_raw, dict):
        raise ValueError("AI response overrides payload missing or invalid")
    overrides = sanitize_overrides(overrides_raw)
    notes = ""
    if isinstance(data, dict):
        notes = str(data.get("notes", "") or "").strip()
    return CapitalTuneResult(equity=equity, broker=broker, overrides=overrides, notes=notes)


def auto_tune_due(now_ts: float | None = None) -> bool:
    if os.getenv(AUTO_TUNE_ENABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    now = now_ts or time.time()
    last_raw = os.getenv(AUTO_TUNE_LAST_TS_ENV, "").strip()
    try:
        last_ts = float(last_raw)
    except Exception:
        last_ts = 0.0
    return (now - last_ts) >= 86400


def apply_tune_to_env(
    *,
    dotenv_path: Path,
    overrides: dict[str, str],
    equity: float,
    broker: str,
    notes: str = "",
) -> None:
    now = time.time()
    updates = dict(overrides)
    updates[AUTO_TUNE_LAST_TS_ENV] = f"{now:.0f}"
    updates[AUTO_TUNE_LAST_EQUITY_ENV] = f"{equity:.2f}"
    updates[AUTO_TUNE_LAST_BROKER_ENV] = broker
    if notes:
        updates["ICC_CAPITAL_TUNE_LAST_NOTE"] = notes[:200].replace("\n", " ").strip()
    merge_dotenv(dotenv_path, updates)
    for key, value in updates.items():
        os.environ[key] = value
    logger.info("[CAPITAL_TUNE] Applied overrides (%s) at %s", ", ".join(overrides.keys()), _format_timestamp(now))
