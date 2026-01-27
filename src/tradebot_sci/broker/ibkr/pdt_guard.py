from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Dict, Optional, TYPE_CHECKING

from tradebot_sci.market.symbols import AssetClass, SymbolMetadata

logger = logging.getLogger(__name__)

class PDTGuard:
    """Enforces regulatory guardrails and Pattern Day Trader (PDT) compliance."""
    
    def __init__(self, profile_settings: Any):
        self.enabled = bool(getattr(profile_settings, "pdt_guard_enabled", False))
        self.roundtrip_limit = int(getattr(profile_settings, "max_equity_roundtrips_per_day", 3))
        self.roundtrips_today = 0
        self.current_date: Optional[date] = None
        self.entry_dates: Dict[str, date] = {}
        self.flip_last_ts: Dict[str, float] = {}
        self.flip_cooldown_seconds = int(getattr(profile_settings, "flip_cooldown_seconds", 600))

    def check_pdt_guard(self, symbol: str, metadata: SymbolMetadata) -> bool:
        """True if we can safely enter a position without violating PDT limits."""
        if not self.enabled:
            return True
        if metadata.asset_class != AssetClass.EQUITY:
            return True
            
        now_date = date.today()
        if self.current_date != now_date:
            self.current_date = now_date
            self.roundtrips_today = 0
            
        if self.roundtrips_today >= self.roundtrip_limit:
            logger.warning("[PDT] Roundtrip limit reached (%d/%d) for today", self.roundtrips_today, self.roundtrip_limit)
            return False
        return True

    def record_equity_entry(self, symbol: str):
        if self.enabled:
            self.entry_dates[symbol.upper()] = date.today()

    def record_equity_exit(self, symbol: str):
        if not self.enabled:
            return
        symbol = symbol.upper()
        if symbol in self.entry_dates and self.entry_dates[symbol] == date.today():
            self.roundtrips_today += 1
            logger.info("[PDT] Recorded roundtrip for %s (%d/%d)", symbol, self.roundtrips_today, self.roundtrip_limit)
            self.entry_dates.pop(symbol, None)

    def is_flip_allowed(self, symbol: str) -> tuple[bool, float]:
        """Checks if a flip is allowed based on cooldown."""
        last_ts = self.flip_last_ts.get(symbol.upper())
        if last_ts is not None:
            elapsed = datetime.now().timestamp() - last_ts
            if elapsed < self.flip_cooldown_seconds:
                return False, self.flip_cooldown_seconds - elapsed
        return True, 0.0

    def record_flip(self, symbol: str):
        self.flip_last_ts[symbol.upper()] = datetime.now().timestamp()
