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

class HyperScalperStrategy(BaseStrategy):
    """
    High-frequency 5m Forex strategy.
    Uses EMA Crossovers (9/21) and ATR for rapid compounding.
    Designed for 100%+ weekly returns.
    """
    
    def __init__(self, fast_ema=9, slow_ema=21, trend_ema=200, **kwargs):
        super().__init__("HyperScalper")
        self.fast_ema_period = int(kwargs.get('fast_ema', fast_ema))
        self.slow_ema_period = int(kwargs.get('slow_ema', slow_ema))
        self.trend_ema_period = int(kwargs.get('trend_ema', trend_ema))
        
        # Overrideable via Context Masking
        self.stop_atr_mult = float(kwargs.get('stop_atr_mult', 2.0))
        self.target_r = float(kwargs.get('target_r', 3.0))

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.trend_ema_period:
            return None
            
        fast_ema_curr = calculate_ema(closes, self.fast_ema_period)
        fast_ema_prev = calculate_ema(closes[:-1], self.fast_ema_period)
        
        slow_ema_curr = calculate_ema(closes, self.slow_ema_period)
        slow_ema_prev = calculate_ema(closes[:-1], self.slow_ema_period)
        
        trend_ema = calculate_ema(closes, self.trend_ema_period)
        rsi = calculate_rsi(closes, 14)
        
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.0005)
        
        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # Long Entry: Fast EMA cross above Slow EMA AND Price > EMA 200 AND RSI > 55 (only when trend allows)
        if htf_dir in ("long", "neutral") and fast_ema_prev <= slow_ema_prev and fast_ema_curr > slow_ema_curr:
            if last_close > trend_ema and rsi > 55:
                # Stop loss at the slow EMA or UserConfig ATR (ARMOR)
                stop_dist = max(atr * self.stop_atr_mult, last_close * 0.0005) 
                stop_loss = last_close - stop_dist
                target = last_close + (stop_dist * self.target_r)
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    structure_summary=f"HyperScalper Hardened Long (Trend={trend_ema:.4f})",
                    invalidation_conditions="Bearish EMA cross",
                    management_instructions=f"Target {self.target_r}R. Filtered by EMA {self.trend_ema_period} + RSI.",
                    risk_per_trade_pct=self.get_risk_pct(),
                    notes="Aggressive compounding scalper",
                    urgency="high"
                )

        # Short Entry: Fast EMA cross below Slow EMA AND Price < EMA 200 AND RSI < 45 (only when trend allows)
        if htf_dir in ("short", "neutral") and fast_ema_prev >= slow_ema_prev and fast_ema_curr < slow_ema_curr:
            if last_close < trend_ema and rsi < 45:
                stop_dist = max(atr * self.stop_atr_mult, last_close * 0.0005)
                stop_loss = last_close + stop_dist
                target = last_close - (stop_dist * self.target_r)
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    structure_summary=f"HyperScalper Hardened Short (Trend={trend_ema:.4f})",
                    invalidation_conditions="Bullish EMA cross",
                    management_instructions=f"Target {self.target_r}R. Filtered by EMA {self.trend_ema_period} + RSI.",
                    risk_per_trade_pct=self.get_risk_pct(),
                    notes="Aggressive compounding scalper",
                    urgency="high"
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        """All exits managed by SafetyGuard. No strategy-level exit authority."""
        return None
