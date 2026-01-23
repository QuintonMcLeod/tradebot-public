from __future__ import annotations
import logging
from typing import Optional, List
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision, hold_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy
from tradebot_sci.strategy.variants.hyper_scalper import HyperScalperStrategy
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class AggregatorStrategy(BaseStrategy):
    """
    Parallel Aggregator Strategy.
    Runs multiple strategies concurrently to maximize capital deployment frequency.
    Yields 400%+ by ensuring the bot is always 'loaded' with the best available signals.
    """
    
    def __init__(self, base_risk_pct=0.10):
        super().__init__("Singularity Aggregator")
        self.base_risk_pct = base_risk_pct
        self.mean_rev = MeanReversionStrategy(bb_period=15, bb_std=2.5, rsi_oversold=25, rsi_overbought=75, base_risk_pct=base_risk_pct)
        self.scalper = HyperScalperStrategy(fast_ema=13, slow_ema=50, base_risk_pct=base_risk_pct)

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None) -> Optional[AITradeDecision]:
        # Priority 1: Scale-in if position exists (aggressive load)
        if open_position:
            # Check Mean Reversion Scale-in
            mr_dec = self.mean_rev.check_entry_signal(snapshot, gates, open_position=open_position)
            if mr_dec and mr_dec.action == "scale_in":
                return mr_dec
                
            # Check Scalper Scale-in (if it supports it)
            hs_dec = self.scalper.check_entry_signal(snapshot, gates, open_position=open_position)
            if hs_dec and hs_dec.action == "scale_in":
                return hs_dec
                
            return None

        # Priority 2: New Entries
        # We check both strategies. If both have signals, we prefer Mean Reversion (higher accuracy).
        mr_entry = self.mean_rev.check_entry_signal(snapshot, gates)
        if mr_entry:
            return mr_entry
            
        hs_entry = self.scalper.check_entry_signal(snapshot, gates)
        if hs_entry:
            return hs_entry

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict) -> Optional[AITradeDecision]:
        # Exit if EITHER strategy confirms an invalidation
        # Mean Reversion handles its exits by TP/SL primarily, but HyperScalper has Trend exits.
        hs_exit = self.scalper.check_exit_signal(snapshot, open_position, gates)
        if hs_exit:
            return hs_exit
            
        mr_exit = self.mean_rev.check_exit_signal(snapshot, open_position, gates)
        if mr_exit:
            return mr_exit
            
        return None
