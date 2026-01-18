from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    price: float | None = None
    post_only: bool = False
    reduce_only: bool = False
    client_order_id: str | None = None


@dataclass
class OrderState:
    order_id: int
    request: OrderRequest
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    reason: str | None = None

