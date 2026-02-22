from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_sma
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class QuantumStrategy(BaseStrategy):
    """
    Quantum Forex Strategy: Trend-following with HTF alignment and LTF MA pullbacks.
    Designed for structural stability in high-volume Forex markets.
    """
    
    def __init__(self, sma_period=20):
        super().__init__("Quantum")
        self.sma_period = sma_period

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        # [QUANTUM] High-Efficiency Trend Entry
        lookback = snapshot.candles
        htf_dir = snapshot.trend_htf.direction
        ltf_dir = snapshot.trend_ltf.direction
        
        # 1. Trend Alignment
        if htf_dir == "neutral" or htf_dir != ltf_dir:
            return None
            
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.sma_period:
            return None
            
        sma = calculate_sma(closes, self.sma_period)
        last_close = closes[-1]
        prev_close = closes[-2]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # Bullish Pullback: Price was above SMA, pulled back to it, then closed above prev bar
        if htf_dir == "long":
            if prev_close < sma * 1.001 and last_close > prev_close:
                # [ARMOR] Dynamic Stops based on UserConfig
                stop_loss = last_close - (atr * UserConfig.STOP_ATR_MULTIPLIER)
                target = last_close + (atr * UserConfig.STOP_ATR_MULTIPLIER * 2.0)  # 2:1 R:R
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Quantum Long: HTF/LTF Aligned + SMA {self.sma_period} Pullback",
                    invalidation_conditions="HTF trend reversal",
                    management_instructions="Net-Zero at 1xATR",
                    notes=f"Armor Entry ({UserConfig.STOP_ATR_MULTIPLIER}x ATR)",
                    urgency="medium"
                )

        # Bearish Pullback
        if htf_dir == "short":
            if prev_close > sma * 0.999 and last_close < prev_close:
                # [ARMOR] Dynamic Stops based on UserConfig
                stop_loss = last_close + (atr * UserConfig.STOP_ATR_MULTIPLIER)
                target = last_close - (atr * UserConfig.STOP_ATR_MULTIPLIER * 2.0)  # 2:1 R:R
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Quantum Short: HTF/LTF Aligned + SMA {self.sma_period} Pullback",
                    invalidation_conditions="HTF trend reversal",
                    management_instructions="Net-Zero at 1xATR",
                    notes="Armor Entry (2x ATR)",
                    urgency="medium"
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        # Exit if HTF trend flips
        htf_dir = snapshot.trend_htf.direction
        pos_dir = open_position.get("direction")
        
        if pos_dir == "long" and htf_dir == "short":
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Quantum Exit: HTF trend flip to short")
        if pos_dir == "short" and htf_dir == "long":
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "Quantum Exit: HTF trend flip to long")
            
        # [SAFETY] Managed by StrategyEngine via SafetyGuard
        return None
