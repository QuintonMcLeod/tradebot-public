"""Quantum Forex Strategy — Trend-following with HTF alignment and LTF MA pullbacks.

Entry Logic:
    1. HTF and LTF trends must align (both long or both short) via engine consensus
    2. Price must pull back TO or THROUGH the SMA20, then bounce
    3. Bounce candle must show momentum (body > 0.3× ATR)
    4. Entry on the bounce candle close

This is designed for structural stability in high-volume Forex markets.
"""
from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class QuantumStrategy(BaseStrategy):
    """
    Quantum Forex Strategy: Trend-following with HTF alignment and LTF MA pullbacks.
    
    Requires:
    - HTF + LTF trend alignment (both long or both short)
    - Price pulled back to SMA20 zone
    - Bounce confirmation (strong body candle)
    """
    
    def __init__(self, sma_period=20):
        super().__init__("Quantum")
        self.sma_period = sma_period

    def check_entry_signal(
        self, snapshot: MarketSnapshot, gates: dict, 
        open_position: Optional[dict] = None, **kwargs
    ) -> Optional[AITradeDecision]:
        candles = snapshot.candles or []
        if len(candles) < self.sma_period + 5:
            return None
            
        # 1. Get trend direction from ENGINE consensus (not raw snapshot)
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        
        # Both timeframes must agree on direction
        if htf_dir not in ("long", "short"):
            return None
        if htf_dir != ltf_dir:
            return None
        
        # 2. Calculate SMA and ATR
        closes = [c.close for c in candles]
        sma = calculate_sma(closes, self.sma_period)
        if sma is None or sma <= 0:
            return None
            
        last_close = closes[-1]
        prev_close = closes[-2]
        prev2_close = closes[-3] if len(closes) >= 3 else prev_close
        atr = calculate_atr(candles, period=14) or (last_close * 0.001)
        
        # 3. Pullback + Bounce detection
        # The previous bar(s) must have been AT or THROUGH the SMA zone
        # Then the current bar bounces away from the SMA
        sma_zone = atr * 0.3  # SMA "zone" = within 0.3 ATR of SMA
        
        action = None
        bias = None
        
        if htf_dir == "long":
            # LONG pullback: prev bar was AT or BELOW SMA, current bar closes above SMA
            was_near_sma = prev_close <= sma + sma_zone
            bounced = last_close > sma and last_close > prev_close
            # Momentum: current candle has a bullish body > 0.3 ATR
            body = candles[-1].close - candles[-1].open
            has_momentum = body > atr * 0.3
            
            if was_near_sma and bounced and has_momentum:
                action = "enter_long"
                bias = "long"
                
        elif htf_dir == "short":
            # SHORT pullback: prev bar was AT or ABOVE SMA, current bar closes below SMA
            was_near_sma = prev_close >= sma - sma_zone
            bounced = last_close < sma and last_close < prev_close
            # Momentum: current candle has a bearish body > 0.3 ATR
            body = candles[-1].open - candles[-1].close
            has_momentum = body > atr * 0.3
            
            if was_near_sma and bounced and has_momentum:
                action = "enter_short"
                bias = "short"
        
        if not action:
            return None
        
        logger.info(
            f"[QUANTUM] ENTRY: {snapshot.symbol} {action} "
            f"HTF={htf_dir} LTF={ltf_dir} SMA={sma:.5f} close={last_close:.5f} "
            f"ATR={atr:.5f}"
        )
        
        # 4. Stop/Target (2:1 R:R)
        stop_mult = 2.0  # 2× ATR stop for forex breathing room
        stop_dist = max(atr * stop_mult, last_close * 0.0015)  # Min 15 pips
        
        if action == "enter_long":
            stop_loss = last_close - stop_dist
            take_profit = last_close + (stop_dist * 2.0)  # 2R
        else:
            stop_loss = last_close + stop_dist
            take_profit = last_close - (stop_dist * 2.0)  # 2R

        return AITradeDecision(
            symbol=snapshot.symbol, timeframe=snapshot.timeframe,
            bias=bias, phase="trend", action=action,
            entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=f"Quantum {action}: HTF/LTF Aligned + SMA{self.sma_period} Pullback Bounce",
            invalidation_conditions="HTF trend reversal",
            management_instructions="Target 2R. Trend-following entry.",
            notes=f"Quantum Trend Entry (2x ATR stop)",
            urgency="medium"
        )

    def check_exit_signal(
        self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs
    ) -> Optional[AITradeDecision]:
        """Exit if HTF trend flips against position."""
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        pos_dir = open_position.get("direction")
        
        if pos_dir == "long" and htf_dir == "short":
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe, 
                "Quantum Exit: HTF trend flip to short"
            )
        if pos_dir == "short" and htf_dir == "long":
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe, 
                "Quantum Exit: HTF trend flip to long"
            )
            
        # [SAFETY] Managed by StrategyEngine via SafetyGuard
        return None
