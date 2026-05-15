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
        # Crypto has data-driven trading hours (Morning Kill Zone avoidance)
        hours = MARKET_HOURS.get(MarketType.CRYPTO)
        if not hours:
            return True  # Fallback: always open if no hours defined
        tz = ZoneInfo(hours["timezone"])
        local = now.astimezone(tz)
        open_h, open_m = map(int, hours["open"].split(":"))
        close_h, close_m = map(int, hours["close"].split(":"))
        open_dt = local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        close_dt = local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
        # Overnight window: open 12PM, close 6AM next day
        if open_dt <= close_dt:
            return open_dt <= local < close_dt
        return local >= open_dt or local < close_dt

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

    # Crypto market hours are now handled above via MARKET_HOURS
    # (removed unconditional return True for MarketType.CRYPTO)
        
    if is_ccxt_data and (metadata.market_type == MarketType.FOREX or metadata.market_type == MarketType.COMMODITY):
        # OANDA is NOT 24/7 for Forex, but it IS for Crypto.
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


def get_schedule_status(profile_name: str, now: datetime, settings: Any, session_id: Optional[str] = None) -> tuple[bool, bool, List[Any]]:
    """
    Evaluates the ScheduleSettings for a given profile_name (or specific session_id) at the current time.
    Returns:
        (is_scheduled, paper_trade_off_hours, active_sessions)
        - is_scheduled: True if the bot should be running right now based on any matching session.
        - paper_trade_off_hours: True if there is a session for this profile, but we are outside its
          active window AND it allows paper trading during off-hours.
        - active_sessions: List of session objects that are currently active.
          
    If NO sessions exist for the profile, default to fully scheduled (True, False, []).
    """
    if not hasattr(settings, "schedule") or not settings.schedule.sessions:
        return True, False, []
        
    # Filter sessions: if session_id is provided, match by ID. 
    # Otherwise, match by profile_name (legacy behavior).
    profile_sessions = []
    for s in settings.schedule.sessions:
        # Strictly respect the 'active' flag
        if not getattr(s, "active", True):
            continue
            
        if session_id:
            if getattr(s, "id", None) == session_id:
                profile_sessions.append(s)
        elif s.profile_name == profile_name:
            profile_sessions.append(s)
            
    if not profile_sessions:
        # If a specific session was requested but not found (or inactive), block execution.
        if session_id:
            return False, False, []
        # If no profile-wide sessions defined, default to 24/7.
        return True, False, []
        
    tz = ZoneInfo(settings.schedule.timezone)
    local_now = now.astimezone(tz)
    weekday_str = local_now.strftime("%A")
    import math
    week_of_month = math.ceil(local_now.day / 7)
    
    can_paper_trade = False
    active_sessions = []
    is_scheduled = False
    
    for sess in profile_sessions:
        sess_active = False
        if sess.mode == "24/7":
            sess_active = True
        elif sess.mode == "one_time" and sess.specific_date:
            date_str = local_now.strftime("%Y-%m-%d")
            if sess.specific_date == date_str:
                # Check Times for one_time
                start_h, start_m = map(int, sess.start_time.split(":"))
                end_h, end_m = map(int, sess.end_time.split(":"))
                start_dt = local_now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                end_dt = local_now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
                if start_dt <= local_now < end_dt:
                    sess_active = True
            elif sess.paper_trade_off_hours:
                can_paper_trade = True
        else:
            # Check Days & Weeks
            if weekday_str in sess.days_of_week and week_of_month in sess.weeks_of_month:
                # Check Times
                start_h, start_m = map(int, sess.start_time.split(":"))
                end_h, end_m = map(int, sess.end_time.split(":"))
                start_dt = local_now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                end_dt = local_now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
                
                if start_dt <= local_now < end_dt:
                    sess_active = True
                elif sess.paper_trade_off_hours:
                    can_paper_trade = True
            elif sess.paper_trade_off_hours:
                can_paper_trade = True
        
        if sess_active:
            is_scheduled = True
            active_sessions.append(sess)
            
    return is_scheduled, can_paper_trade, active_sessions


def get_current_session(now: datetime, sessions: List[Any], tz: ZoneInfo) -> Optional[Dict[str, Any]]:
    """Determine the active session from a list of scheduled sessions."""
    for sess in sessions:
        start_h, start_m = map(int, sess.start_time.split(":"))
        end_h, end_m = map(int, sess.end_time.split(":"))
        start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start_dt <= now < end_dt:
            return {"name": sess.profile_name, "end": end_dt}
    return None


def get_next_session_start(now: datetime, sessions: List[Any], tz: ZoneInfo) -> tuple[Optional[datetime], Optional[Any]]:
    """Find the start time and object of the next scheduled session."""
    upcoming: list[tuple[datetime, Any]] = []
    for sess in sessions:
        sh, sm = map(int, sess.start_time.split(":"))
        start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if start_dt <= now:
            start_dt = start_dt + timedelta(days=1)
        upcoming.append((start_dt, sess))
    if not upcoming:
        return None, None
    next_start, sess = min(upcoming, key=lambda pair: pair[0])
    return next_start, sess
