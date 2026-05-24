from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from tradebot_sci.market.trend_enums import TrendDirection


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TrendState:
    direction: str | TrendDirection  # Accept both string and enum for backwards compatibility
    strength: float  # 0-1 scale
    adx: float = 0.0  # ADX trend strength (0-100 scale)
    last_confirmed_swings: Optional[List[Dict[str, float | int]]] = None
    key_levels: Optional[Dict[str, float]] = None


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    candles: List[Candle]
    trend_htf: TrendState
    trend_ltf: TrendState
    trend_mtf: Optional[TrendState] = None
    trend_exec: Optional[TrendState] = None
    htf_candles: Optional[List[Candle]] = None
    mtf_candles: Optional[List[Candle]] = None
    ltf_candles: Optional[List[Candle]] = None
    htf_timeframe: Optional[str] = None
    mtf_timeframe: Optional[str] = None
    ltf_timeframe: Optional[str] = None
    micro_candles: Optional[List[Candle]] = None
    micro_timeframe: Optional[str] = None


@dataclass
class Ticker:
    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    volume_24h_quote_usd: float | None

    def get(self, key: str, default: object = None) -> object:
        return getattr(self, key, default)


@dataclass
class OrderBookLevel:
    price: float
    size: float


@dataclass
class Ask:
    price: float
    size: float


@dataclass
class Bid:
    price: float
    size: float


@dataclass
class OrderBook:
    symbol: str
    bids: list[Bid]
    asks: list[Ask]
    timestamp: datetime
