from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

class QS_TqqqBtalStrategy(BaseStrategy):
    """
    5. TQQQ and BTAL Annual Index Fund Rebalancing
    Core Idea: Exploits trading opportunities created by periodic rebalancing. 
    Combines TQQQ (growth) with BTAL (hedge). Since the bot evaluates symbols sequentially, 
    this module acts as a passive container to trigger allocations on target ETFs globally.
    """
    def __init__(self):
        super().__init__("QS TQQQ/BTAL Rebalancer")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.symbol.upper() in ("TQQQ", "BTAL"):
            return None
            
        # Rebalancing logic requires portfolio-level awareness which is handled upstream.
        # This proxy just ensures valid ETF target acquisition on the first of the month.
        if snapshot.candles:
            current_day = snapshot.candles[-1].timestamp.day
            if current_day == 1 and not open_position:
                last_close = snapshot.candles[-1].close
                stop_loss = last_close * 0.90
                take_profit = last_close + (last_close - stop_loss) * 2.0
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="rebalance", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                    structure_summary=f"Monthly Rebalance Allocation for {snapshot.symbol}",
                    invalidation_conditions="End of Month",
                    urgency="low",
                    risk_per_trade_pct=self.get_risk_pct()
                )
        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        return None
