from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from tradebot_sci.market.models import Candle, TrendState
from tradebot_sci.market.trend_enums import TrendDirection
from tradebot_sci.market.swing_analysis import swing_points

logger = logging.getLogger(__name__)

class ICCPhase(Enum):
    WAITING = "WAITING"
    INDICATION = "INDICATION"
    CORRECTION = "CORRECTION"
    CONTINUATION = "CONTINUATION"

@dataclass
class ICCState:
    symbol: str
    phase: ICCPhase = ICCPhase.WAITING
    direction: TrendDirection = TrendDirection.NEUTRAL
    indication_level: Optional[float] = None  # The level that was broken
    extreme_price: Optional[float] = None    # The HH or LL reached after break
    correction_depth_pct: float = 0.0        # How much we retraced
    last_processed_index: int = -1

class ICCStateMachine:
    """Tracks the Indication-Correction-Continuation state for a symbol.
    
    Standard Flow:
    1. WAITING: Looking for structure break.
    2. INDICATION: Structure break detected (BOS). Tracking extension.
    3. CORRECTION: Retracement started toward the broken level.
    4. CONTINUATION: Price re-breaks the indication extreme/level.
    """
    
    def __init__(self, symbol: str, min_correction_pct: float = 0.5):
        self.symbol = symbol
        self.state = ICCState(symbol=symbol)
        self.min_correction_pct = min_correction_pct
        
    def update(self, candles: list[Candle], trend_state: TrendState) -> ICCState:
        if not candles:
            return self.state
            
        current_price = candles[-1].close
        current_index = len(candles) - 1
        
        if current_index <= self.state.last_processed_index:
            return self.state
            
        self.state.last_processed_index = current_index
        
        # 1. WAITING -> INDICATION
        if self.state.phase == ICCPhase.WAITING:
            self._check_for_indication(trend_state, current_price)
            
        # 2. INDICATION -> CORRECTION (or update extreme)
        elif self.state.phase == ICCPhase.INDICATION:
            self._handle_indication_phase(current_price)
            
        # 3. CORRECTION -> CONTINUATION
        elif self.state.phase == ICCPhase.CORRECTION:
            self._handle_correction_phase(current_price)
            
        # 4. CONTINUATION -> WAITING (Reset after one bar in continuation to allow entry)
        elif self.state.phase == ICCPhase.CONTINUATION:
            # We stay in continuation for one bar to signal entry
            # Then we reset to look for the next cycle
            self.state = ICCState(symbol=self.symbol, last_processed_index=current_index)
            
        return self.state

    def _check_for_indication(self, trend_state: TrendState, current_price: float):
        """Look for a trend transition or structure break to start the cycle."""
        if trend_state.direction == TrendDirection.LONG:
            # If we recently turned LONG, we consider the last swing high as the indication level
            if trend_state.key_levels and "last_swing_high" in trend_state.key_levels:
                self.state.phase = ICCPhase.INDICATION
                self.state.direction = TrendDirection.LONG
                self.state.indication_level = trend_state.key_levels["last_swing_high"]
                self.state.extreme_price = current_price
                logger.info(f"[ICC] {self.symbol} INDICATION (LONG) at {self.state.indication_level}")
        
        elif trend_state.direction == TrendDirection.SHORT:
            if trend_state.key_levels and "last_swing_low" in trend_state.key_levels:
                self.state.phase = ICCPhase.INDICATION
                self.state.direction = TrendDirection.SHORT
                self.state.indication_level = trend_state.key_levels["last_swing_low"]
                self.state.extreme_price = current_price
                logger.info(f"[ICC] {self.symbol} INDICATION (SHORT) at {self.state.indication_level}")

    def _handle_indication_phase(self, current_price: float):
        """Track the move higher/lower and look for local reversal to start correction."""
        if self.state.direction == TrendDirection.LONG:
            if current_price > self.state.extreme_price:
                self.state.extreme_price = current_price
            else:
                # Potential start of correction
                move_size = self.state.extreme_price - self.state.indication_level
                if move_size > 0:
                    correction_depth = (self.state.extreme_price - current_price) / move_size
                    if correction_depth > 0.1: # 10% pullback starts CORRECTION phase
                        self.state.phase = ICCPhase.CORRECTION
                        logger.info(f"[ICC] {self.symbol} CORRECTION (LONG) started. Move: {move_size:.2f}")
        
        elif self.state.direction == TrendDirection.SHORT:
            if current_price < self.state.extreme_price:
                self.state.extreme_price = current_price
            else:
                move_size = self.state.indication_level - self.state.extreme_price
                if move_size > 0:
                    correction_depth = (current_price - self.state.extreme_price) / move_size
                    if correction_depth > 0.1:
                        self.state.phase = ICCPhase.CORRECTION
                        logger.info(f"[ICC] {self.symbol} CORRECTION (SHORT) started. Move: {move_size:.2f}")

    def _handle_correction_phase(self, current_price: float):
        """Track correction depth and look for continuation break."""
        move_size = abs(self.state.extreme_price - self.state.indication_level)
        if move_size == 0:
            self.state.phase = ICCPhase.WAITING
            return

        if self.state.direction == TrendDirection.LONG:
            current_depth = (self.state.extreme_price - current_price) / move_size
            self.state.correction_depth_pct = max(self.state.correction_depth_pct, current_depth)
            
            # Continuation condition:
            # 1. We had enough correction (min_correction_pct)
            # 2. Price breaks the extreme_price (2nd move in direction)
            if self.state.correction_depth_pct >= self.min_correction_pct:
                if current_price > self.state.extreme_price:
                    self.state.phase = ICCPhase.CONTINUATION
                    logger.info(f"[ICC] {self.symbol} CONTINUATION (LONG) confirmed!")
            
            # Reset if price drops below indication level (failure)
            if current_price < self.state.indication_level:
                self.state.phase = ICCPhase.WAITING
                logger.debug(f"[ICC] {self.symbol} LONG sequence failed (level lost)")

        elif self.state.direction == TrendDirection.SHORT:
            current_depth = (current_price - self.state.extreme_price) / move_size
            self.state.correction_depth_pct = max(self.state.correction_depth_pct, current_depth)
            
            if self.state.correction_depth_pct >= self.min_correction_pct:
                if current_price < self.state.extreme_price:
                    self.state.phase = ICCPhase.CONTINUATION
                    logger.info(f"[ICC] {self.symbol} CONTINUATION (SHORT) confirmed!")
            
            if current_price > self.state.indication_level:
                self.state.phase = ICCPhase.WAITING
                logger.debug(f"[ICC] {self.symbol} SHORT sequence failed (level lost)")
