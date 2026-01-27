from __future__ import annotations

import logging
from datetime import datetime, timedelta, time as datetime_time
from zoneinfo import ZoneInfo
from typing import List, Optional, Dict, Any

from tradebot_sci.market.symbols import MARKET_HOURS, MarketType, SYMBOL_METADATA, is_crypto
from tradebot_sci.config.loader import get_settings

logger = logging.getLogger(__name__)

def is_market_open(symbol: str, now: datetime, settings: Optional[Any] = None) -> bool:
    """Determine if the market for a given symbol is currently open."""
    if is_crypto(symbol):
        return True

    metadata = SYMBOL_METADATA.get(symbol.strip().upper())
    if not metadata:
        logger.warning(f"[SCHEDULE] No metadata for {symbol}")
        return False
    
    if settings is None:
        settings = get_settings()
        
    market_data_mode = "primary"
    alt_market_data = "mock"
    
    if hasattr(settings, "market"):
        market_data_mode = getattr(settings.market, "market_data_mode", "primary")
        alt_market_data = getattr(settings.market, "alternative_market_data", "mock")
    
    # Check overrides if settings is a TradingProfileSettings-like object
    if hasattr(settings, "runtime_overrides"):
        ovr = settings.runtime_overrides
        if hasattr(ovr, "get"):
             market_data_mode = ovr.get("market_data_mode", market_data_mode)
             alt_market_data = ovr.get("alternative_market_data", alt_market_data)
        else:
             market_data_mode = getattr(ovr, "market_data_mode", market_data_mode)
             alt_market_data = getattr(ovr, "alternative_market_data", alt_market_data)

    is_ccxt_data = market_data_mode in ("alternative", "hybrid")

    if not is_ccxt_data and symbol in {"XPTUSD", "XPDUSD"}:
        return False

    if metadata.market_type == MarketType.CRYPTO:
        return True
        
    if is_ccxt_data and (metadata.market_type == MarketType.FOREX or metadata.market_type == MarketType.COMMODITY):
        # [ANTIGRAVITY FIX] OANDA is NOT 24/7 for Forex, but it IS for Crypto.
        # This branch only handles FOREX/COMMODITY.
        if alt_market_data != "oanda":
            return True

    hours = MARKET_HOURS.get(metadata.market_type)
    if not hours:
        return False
        
    if metadata.market_type == MarketType.FOREX:
        return _is_forex_open(now)
        
    tz = ZoneInfo(hours["timezone"])
    local = now.astimezone(tz)
    
    if metadata.market_type in {MarketType.US_EQUITY, MarketType.EU_EQUITY, MarketType.APAC_EQUITY}:
        if local.weekday() >= 5:
            return False
            
    open_hour, open_minute = map(int, hours["open"].split(":"))
    close_hour, close_minute = map(int, hours["close"].split(":"))
    
    open_dt = local.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    close_dt = local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    
    if open_dt <= close_dt:
        return open_dt <= local < close_dt
    return local >= open_dt or local < close_dt


def _is_forex_open(now: datetime) -> bool:
    """Forex specific open check (UTC based)."""
    utc = now.astimezone(ZoneInfo("UTC"))
    cutoff = datetime_time(22, 0)
    current = utc.time()
    weekday = utc.weekday()
    if weekday == 5: return False
    if weekday == 6: return current >= cutoff
    if weekday == 4: return current < cutoff
    return True


def get_current_session(now: datetime, sessions: List[Any], tz: ZoneInfo) -> Optional[Dict[str, Any]]:
    """Determine the active session from a list of scheduled sessions."""
    for sess in sessions:
        start_h, start_m = map(int, sess.start.split(":"))
        end_h, end_m = map(int, sess.end.split(":"))
        start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start_dt <= now < end_dt:
            return {"name": sess.name, "end": end_dt}
    return None


def get_next_session_start(now: datetime, sessions: List[Any], tz: ZoneInfo) -> tuple[Optional[datetime], Optional[Any]]:
    """Find the start time and object of the next scheduled session."""
    upcoming: list[tuple[datetime, Any]] = []
    for sess in sessions:
        sh, sm = map(int, sess.start.split(":"))
        start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if start_dt <= now:
            start_dt = start_dt + timedelta(days=1)
        upcoming.append((start_dt, sess))
    if not upcoming:
        return None, None
    next_start, sess = min(upcoming, key=lambda pair: pair[0])
    return next_start, sess
