from __future__ import annotations
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision

class BaseStrategy:
    """Interface for all bot strategy variants."""
    
    def __init__(self, name: str):
        self.name = name

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for a new trade entry signal."""
        raise NotImplementedError

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, trade_history: Optional[list] = None) -> Optional[AITradeDecision]:
        """Check for an exit signal for an open position."""
        raise NotImplementedError
