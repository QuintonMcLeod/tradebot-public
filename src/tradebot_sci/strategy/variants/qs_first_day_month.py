from __future__ import annotations
import logging
from typing import Optional
import datetime
import calendar
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

class QS_FirstDayOfMonthStrategy(BaseStrategy):
    """
    7. First Trading Day of the Month (Calendar Effect)
    Core Idea: Capitalizes on the seasonal effect where the first trading day of the month
    frequently registers anomalous positive returns due to capital inflows.
    Rules: Buy near the close of the last trading day of the month; sell near the close of the first day.
    """
    def __init__(self, **kwargs):
        super().__init__("QS First Day of Month Seasonality")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles:
            return None
        
        current_time = snapshot.candles[-1].timestamp
        
        # NOTE: Calendar-based timing (end-of-month entries) is inherently date-specific.
        # This strategy only triggers on month-end/month-start dates regardless of session timing.
        # The Global Scheduler can be used to further restrict which hours these trades execute.
        
        # Check if we are on the very last day of the current month
        # Assuming typical trading days, if we're on the last calendar day, or the last Friday
        # A simple robust way in forex/crypto is testing if tomorrow is month 1.
        tomorrow = current_time + datetime.timedelta(days=1)
        
        if tomorrow.month != current_time.month:
            # We are on the last day of the month!
            # NOTE: Hour restriction removed - Global Scheduler handles session timing
            # Entry logic now focuses purely on date-based calendar effect
            last_close = snapshot.candles[-1].close
            stop_loss = last_close * 0.95
            take_profit = last_close + (last_close - stop_loss) * 2.0
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="management", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                structure_summary=f"End of Month Calendar Entry ({current_time.strftime('%Y-%m-%d')})",
                invalidation_conditions="End of First Trading Day",
                urgency="low",
                risk_per_trade_pct=self.get_risk_pct()
            )
                
        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles:
            return None
            
        current_time = snapshot.candles[-1].timestamp
        
        # Determine if we are on the first trading day of the new month
        # In Crypto, day 1 is the 1st. In Forex, day 1 might be the 1st through 3rd.
        # NOTE: Hour restriction removed - Global Scheduler handles session timing
        # Exit logic now focuses purely on date-based calendar effect
        if current_time.day <= 3:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "First Trading Day Elapsed - Seasonal Exit")
            
        return None
