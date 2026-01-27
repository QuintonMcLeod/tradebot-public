from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from tradebot_sci.broker.execution import ExecutionResult

logger = logging.getLogger(__name__)

@dataclass
class SyntheticStop:
    """Represents a locally monitored stop/TP order."""
    symbol: str
    direction: str
    stop_price: float
    tp_price: float | None
    size: float
    entry_order: Any | None
    tp_order: Any | None
    state: str
    created_at: datetime

    def should_trigger(self, last_price: float) -> bool:
        if self.state != "armed":
            return False
        if self.direction == "long":
            return last_price <= self.stop_price
        return last_price >= self.stop_price

    def should_take_profit(self, last_price: float) -> bool:
        if self.state != "armed" or self.tp_price is None:
            return False
        if self.direction == "long":
            return last_price >= self.tp_price
        return last_price <= self.tp_price


class SyntheticStopManager:
    """Manages evaluation of local synthetic stops and take-profits."""
    
    def __init__(self, stop_store: Any = None):
        self.stops: Dict[str, SyntheticStop] = {}
        self.stop_store = stop_store
        self.integrity_counter = 0

    def register(self, stop: SyntheticStop):
        self.stops[stop.symbol.upper()] = stop

    def clear(self, symbol: str):
        self.stops.pop(symbol.upper(), None)

    def evaluate_all(
        self, 
        provider: Any, 
        get_last_price_fn: Callable[[str], Optional[float]],
        trigger_cb: Callable[[SyntheticStop, float, str], Any]
    ) -> List[Any]:
        """Iterates through armed stops and triggers callbacks if price thresholds are met."""
        results = []
        for symbol, stop in list(self.stops.items()):
            if stop.state != "armed":
                continue
                
            last_price = get_last_price_fn(symbol)
            if last_price is None:
                continue
                
            if stop.should_take_profit(last_price):
                logger.info("[SYNTHETIC] TP triggered for %s (price=%.4f tp=%.4f)", symbol, last_price, stop.tp_price)
                res = trigger_cb(stop, last_price, "TP")
                if res: results.append(res)
                self.clear(symbol)
            elif stop.should_trigger(last_price):
                logger.info("[SYNTHETIC] Stop triggered for %s (price=%.4f sl=%.4f)", symbol, last_price, stop.stop_price)
                res = trigger_cb(stop, last_price, "SL")
                if res: results.append(res)
                self.clear(symbol)
                
        return results
