from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)

class VolatilityBreakoutStrategy(BaseStrategy):
    """
    High-frequency breakout strategy.
    Captures explosive moves when price breaks the recent range with high ATR/RSI momentum.
    """
    
    def __init__(self, range_period=20, atr_mult=1.5):
        super().__init__("Volatility Breakout")
        self.range_period = range_period
        self.atr_mult = atr_mult

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.range_period + 1:
            return None
            
        recent_high = max(c.high for c in snapshot.candles[-self.range_period:-1])
        recent_low = min(c.low for c in snapshot.candles[-self.range_period:-1])
        
        last_candle = snapshot.candles[-1]
        last_close = last_candle.close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)
        rsi = calculate_rsi(closes, 14)
        
        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # ── Quality Filters ──────────────────────────────────────────
        # 1. ATR Expansion: current ATR must exceed its 20-bar average
        #    Ensures we only enter during REAL volatility, not Asian chop
        atr_history = []
        for i in range(max(0, len(snapshot.candles) - 20), len(snapshot.candles)):
            slice_end = i + 1
            if slice_end >= 15:
                a = calculate_atr(snapshot.candles[slice_end-14:slice_end], period=14)
                if a:
                    atr_history.append(a)
        avg_atr = sum(atr_history) / len(atr_history) if atr_history else atr
        if atr < avg_atr * 1.2:
            return None  # Flat market — no real breakout

        # 2. Candle body must confirm direction (close in outer 25% of range)
        candle_range = last_candle.high - last_candle.low
        if candle_range <= 0:
            return None

        # Long Entry: Breakout of range high + RSI > 70 + ATR expanding
        if htf_dir in ("long", "neutral") and last_close > recent_high and rsi > 70:
            body_ratio = (last_close - last_candle.low) / candle_range
            if body_ratio < 0.75:
                return None  # Weak close — likely false breakout
            
            stop_dist = atr * 2.0
            stop_loss = last_close - stop_dist
            target = last_close + (stop_dist * 2.5)  # Raised to 2.5R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Volatility Breakout (High={recent_high:.4f}, RSI={rsi:.1f}, ATR expand={atr/avg_atr:.2f}x)",
                invalidation_conditions="Close below breakout bar",
                management_instructions="Net-Zero at 1xATR",
                notes="Armor Entry (2x ATR)",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )

        # Short Entry: Breakout of range low + RSI < 30 + ATR expanding
        if htf_dir in ("short", "neutral") and last_close < recent_low and rsi < 30:
            body_ratio = (last_candle.high - last_close) / candle_range
            if body_ratio < 0.75:
                return None  # Weak close — likely false breakout
            
            stop_dist = atr * 2.0
            stop_loss = last_close + stop_dist
            target = last_close - (stop_dist * 2.5)  # Raised to 2.5R
            
            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                structure_summary=f"Volatility Breakout (Low={recent_low:.4f}, RSI={rsi:.1f}, ATR expand={atr/avg_atr:.2f}x)",
                invalidation_conditions="Close above breakout bar",
                management_instructions="Net-Zero at 1xATR",
                notes="Armor Entry (2x ATR)",
                urgency="high",
                risk_per_trade_pct=self.get_risk_pct()
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """All exits managed by SafetyGuard. No strategy-level exit authority."""
        return None
