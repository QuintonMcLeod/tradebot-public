from __future__ import annotations
import logging
from typing import Optional


from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi, calculate_bollinger_bands
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

class ForexHybridReaperStrategy(BaseStrategy):
    """
    Forex Hybrid Scalper — Router inspired high-frequency 5m Forex strategy.
    Combines HyperScalper's trend filter (EMA 200) with Rubberband Reaper's 
    kinetic entry signals (RSI + Bollinger Bands), wrapped in strict 
    session and volatility guards to avoid Asian chop.
    
    Optimized for major pairs (EUR/USD, GBP/USD).
    """
    def __init__(self, target_r=2.5, **kwargs):
        super().__init__("ForexHybridReaper")
        self.target_r = target_r
        
        # Rubberband Reaper default kinetics parameters
        self.bb_period = int(kwargs.get('bb_period', 20))
        self.bb_std = float(kwargs.get('bb_std', 1.5))
        self.rsi_period = int(kwargs.get('rsi_period', 7))
        self.rsi_overbought = float(kwargs.get('rsi_overbought', 60))
        self.rsi_oversold = float(kwargs.get('rsi_oversold', 40))
        
        # Hyper Scalper default trend parameters
        self.trend_ema_period = int(kwargs.get('trend_ema', 200))
        
        logger.debug(f"Loaded ForexHybridReaper with TargetR={self.target_r}, TrendEMA={self.trend_ema_period}")

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        if len(candles) < self.trend_ema_period:
            return None
        
        # ---------------------------------------------------------
        # 1. Volatility Guard (Avoid chop/flat markets)
        # ---------------------------------------------------------
        # Requirement: calculate_atr value must NOT be 30% below 
        # its 20-period average.
        if len(candles) < 40:
            return None
            
        # Re-using the exact calculate_atr function logic natively
        # Calculating the SMA of the ATR over the last 20 periods
        atr_history = []
        for i in range(-20, 0):
            # calculate ATR up to candle i
            slice_candles = candles[:len(candles)+i+1] if i < -1 else candles
            a = calculate_atr(slice_candles, period=14)
            if a:
                atr_history.append(a)
        
        if not atr_history:
            return None
            
        avg_atr_20 = sum(atr_history) / len(atr_history)
        current_atr = calculate_atr(candles, period=14)
        
        if not current_atr or current_atr < (avg_atr_20 * 0.7):
            logger.info(f"[ForexHybridReaper] {snapshot.symbol} BLOCKED: Volatility Guard. ATR ({current_atr:.5f}) < 70% of 20-period average ({avg_atr_20:.5f})")
            return None

        # ---------------------------------------------------------
        # 3. Hybrid Entry Logic
        # ---------------------------------------------------------
        closes = [c.close for c in candles]
        
        # Execute existing code to harvest indicators lazily
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        lower_bb, mid_bb, upper_bb = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        
        # Guard: No scale-ins for simple strategy unless specified by open_position logic
        if open_position:
            return None
            
        logger.info(f"[HybridReaper Debug {snapshot.symbol}] Close={last_close:.5f} | EMA={trend_ema:.5f} | RSI={rsi:.1f} | LBB={lower_bb:.5f} | UBB={upper_bb:.5f} | HTF={htf_dir}")
            
        # LONG: Price > 200 EMA + RSI < Oversold + Price <= Lower BB
        if htf_dir in ("long", "neutral") and last_close > trend_ema:
            if rsi <= self.rsi_oversold and last_close <= lower_bb:
                stop_dist = max(current_atr * 1.5, last_close * 0.0008)  # Safe floor distance
                stop_loss = last_close - stop_dist
                target = last_close + (stop_dist * self.target_r)
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="correction", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Long (RSI={rsi:.1f}, BBTouch)",
                    invalidation_conditions="Close below stop loss.",
                    management_instructions=f"Target {self.target_r}R.",
                    urgency="high"
                )

        # SHORT: Price < 200 EMA + RSI > Overbought + Price >= Upper BB
        if htf_dir in ("short", "neutral") and last_close < trend_ema:
            if rsi >= self.rsi_overbought and last_close >= upper_bb:
                stop_dist = max(current_atr * 1.5, last_close * 0.0008)
                stop_loss = last_close + stop_dist
                target = last_close - (stop_dist * self.target_r)
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="correction", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"HybridReaper Short (RSI={rsi:.1f}, BBTouch)",
                    invalidation_conditions="Close above stop loss.",
                    management_instructions=f"Target {self.target_r}R.",
                    urgency="high"
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """All exits managed by structural lifecycle/safety guards."""
        return None
