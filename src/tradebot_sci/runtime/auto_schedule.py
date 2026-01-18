from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from tradebot_sci.market.symbols import AssetClass, MARKET_HOURS, MarketType, SYMBOL_METADATA


@dataclass(frozen=True)
class AutoScheduleSelection:
    mode: str  # "equity" | "crypto"
    symbols: list[str]


def _is_us_equity_session_open(now_utc: datetime) -> bool:
    hours = MARKET_HOURS.get(MarketType.US_EQUITY)
    if not hours:
        return False
    tz = ZoneInfo(hours["timezone"])
    local = now_utc.astimezone(tz)
    if local.weekday() >= 5:
        return False
    open_hour, open_minute = map(int, hours["open"].split(":"))
    close_hour, close_minute = map(int, hours["close"].split(":"))
    open_dt = local.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    close_dt = local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    return open_dt <= local < close_dt


def select_auto_schedule_symbols(
    symbols: list[str],
    now_utc: datetime,
) -> AutoScheduleSelection:
    """Auto-switch between equities (US market hours) and crypto (off-hours)."""
    desired_class = AssetClass.EQUITY if _is_us_equity_session_open(now_utc) else AssetClass.CRYPTO
    mode = "equity" if desired_class == AssetClass.EQUITY else "crypto"
    selected: list[str] = []
    for symbol in symbols:
        metadata = SYMBOL_METADATA.get(symbol)
        if not metadata:
            continue
        if metadata.asset_class == desired_class:
            selected.append(symbol)
    return AutoScheduleSelection(mode=mode, symbols=selected)

