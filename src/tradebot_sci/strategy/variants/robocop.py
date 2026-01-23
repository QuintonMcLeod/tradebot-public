from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import (
    detect_continuation, 
    detect_liquidity_sweep, 
    detect_indication, 
    detect_correction,
    detect_structure_invalidation
)
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class RoboCopStrategy(BaseStrategy):
    """
    High-frequency, aggressive ICC variant.
    Bypasses sessions, human delays, and allows 'naked' entries on strong signals.
    """
    
    def __init__(self):
        super().__init__("RoboCop")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None) -> Optional[AITradeDecision]:
        # [ROBOCOP] Combat Mode Entry: React to ANY valid micro-signal
        sweep = detect_liquidity_sweep(snapshot.candles, snapshot.trend_ltf.direction, swing_lookback=2)
        indication = detect_indication(snapshot.candles, swing_lookback=1)
        
        # [ROBOCOP] Naked Entry: Allow continuation without prior correction if momentum is high
        cont = detect_continuation(
            snapshot.candles, 
            snapshot.trend_ltf.direction, 
            sweep, 
            indication, 
            require_correction=False,
            confirmation_bars=1 # Faster confirmation
        )
        
        if cont:
             last_close = snapshot.candles[-1].close
             atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
             
             # Aggressive sizing
             stop_loss = last_close - (atr * 1.5) if cont.direction == "long" else last_close + (atr * 1.5)
             target = last_close + (atr * 3.0) if cont.direction == "long" else last_close - (atr * 3.0)
             
             return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias=cont.direction, phase="continuation", action="enter_long" if cont.direction == "long" else "enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"RoboCop Aggressive ICC (Sweep={bool(sweep)})",
                invalidation_conditions="Close below recent swing",
                management_instructions="Target 2R",
                notes="Combat Mode Entry",
                urgency="high"
            )
        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict) -> Optional[AITradeDecision]:
        # [ROBOCOP] Fast Exit Logic
        pos_dir = open_position.get("direction")
        unrealized_pnl = float(open_position.get("unrealized_pnl", 0.0))
        
        # 1. Structure Invalidation (Aggressive 0.5 ATR)
        inval = detect_structure_invalidation(snapshot.candles, pos_dir, atr_mult=0.5)
        if inval:
             return close_position_decision(snapshot.symbol, snapshot.timeframe, f"RoboCop Structure Invalidation: {inval.describe()}")
             
        # 2. Chop TP (Stagnation Exit)
        # We use the gates passed from engine which track 'phase'
        current_phase = gates.get("phase", "")
        if current_phase == "chop" and unrealized_pnl > 0:
             # If we've been in chop for more than 3 bars while profitable, bank it.
             # This is a classic 'RoboCop' move to keep the machine moving.
             return close_position_decision(snapshot.symbol, snapshot.timeframe, f"RoboCop Chop TP: Profitable (${unrealized_pnl:.2f}) + Market Stagnation")

        return None
