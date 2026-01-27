from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Tuple, TYPE_CHECKING

from tradebot_sci.market.symbols import AssetClass, SymbolMetadata, SYMBOL_METADATA

if TYPE_CHECKING:
    from ib_insync import IB, Contract, Order

logger = logging.getLogger(__name__)

class BracketManager:
    """Encapsulates IBKR bracket order construction and venue-specific formatting."""
    
    def __init__(self, ib: Optional[Any], runtime_settings: Any, profile_settings: Any):
        self.ib = ib
        self.runtime = runtime_settings
        self.profile = profile_settings
        self._min_tick_cache: dict[str, float] = {}

    @staticmethod
    def effective_tif(asset_class: AssetClass | None, exchange: str | None, default: str) -> str:
        """Return a venue-safe time-in-force."""
        if asset_class == AssetClass.CRYPTO and (exchange or "").upper() == "ZEROHASH":
            override = (os.getenv("IBKR_ZEROHASH_CRYPTO_TIF") or "Minutes").strip()
            if not override:
                return "Minutes"
            override_l = override.lower()
            if override_l in {"ioc"}:
                return "IOC"
            if override_l in {"minutes", "minute"}:
                return "Minutes"
            return "Minutes"
        return default

    def get_min_tick(self, contract: Any, symbol: str) -> float | None:
        cached = self._min_tick_cache.get(symbol)
        if cached:
            return cached
        if not self.ib:
            return None
        try:
            details = self.ib.reqContractDetails(contract)
            if not details:
                return None
            min_tick = getattr(details[0], "minTick", None)
            if not min_tick or min_tick <= 0:
                return None
            self._min_tick_cache[symbol] = float(min_tick)
            return float(min_tick)
        except Exception as exc:
            logger.warning("[BRACKET] Failed to fetch contract details for %s: %s", symbol, exc)
            return None

    @staticmethod
    def round_price_to_tick(price: float, tick: float) -> float:
        from decimal import Decimal, ROUND_HALF_UP
        if tick <= 0:
            return price
        ticks = Decimal(str(price)) / Decimal(str(tick))
        rounded_ticks = ticks.to_integral_value(rounding=ROUND_HALF_UP)
        return float(rounded_ticks * Decimal(str(tick)))

    @staticmethod
    def align_prices(
        direction: str,
        entry: float,
        take_profit: float,
        stop_loss: float,
        tick: float,
    ) -> tuple[float, float, float]:
        if tick <= 0:
            return entry, take_profit, stop_loss
        if direction == "long":
            if take_profit <= entry:
                take_profit = entry + tick
            if stop_loss >= entry:
                stop_loss = entry - tick
        else:
            if take_profit >= entry:
                take_profit = entry - tick
            if stop_loss <= entry:
                stop_loss = entry + tick
        return entry, take_profit, stop_loss

    @staticmethod
    def apply_zerohash_minutes_tif(order: Any) -> None:
        if not order or getattr(order, "tif", None) != "Minutes":
            return
        try:
            raw = (os.getenv("IBKR_ZEROHASH_CRYPTO_TIF_MINUTES") or "").strip() or "1"
            minutes = int(float(raw))
        except Exception:
            minutes = 1
        minutes = max(1, min(60, minutes))
        gtd = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        order.goodTillDate = gtd.strftime("%Y%m%d %H:%M:%S")

    @staticmethod
    def set_order_ref(order: Any, symbol: str, tag: str) -> None:
        if not order:
            return
        try:
            existing = getattr(order, "orderRef", "") or ""
            if existing.strip():
                return
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            nonce = uuid.uuid4().hex[:8]
            setattr(order, "orderRef", f"TBSCI:{symbol.upper()}:{tag}:{stamp}:{nonce}")
        except Exception:
            return
