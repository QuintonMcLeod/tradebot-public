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
    
    def __init__(self, fast_ema=9, slow_ema=21, trend_ema=200):
        super().__init__("HyperScalper")
        self.fast_ema_period = fast_ema
        self.slow_ema_period = slow_ema
        self.trend_ema_period = trend_ema

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
                stop_dist = max(atr * UserConfig.STOP_ATR_MULTIPLIER, last_close * 0.0005) 
                stop_loss = last_close - stop_dist
                target = last_close + (stop_dist * 3.0) # Aim for 3R to hit 100%+
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    structure_summary=f"HyperScalper Hardened Long (Trend={trend_ema:.4f})",
                    invalidation_conditions="Bearish EMA cross",
                    management_instructions="Target 3R. Filtered by EMA 200 + RSI.",
                    risk_per_trade_pct=self.get_risk_pct(),
                    notes="Aggressive compounding scalper",
                    urgency="high"
                )

        # Short Entry: Fast EMA cross below Slow EMA AND Price < EMA 200 AND RSI < 45 (only when trend allows)
        if htf_dir in ("short", "neutral") and fast_ema_prev >= slow_ema_prev and fast_ema_curr < slow_ema_curr:
            if last_close < trend_ema and rsi < 45:
                stop_dist = max(atr * UserConfig.STOP_ATR_MULTIPLIER, last_close * 0.0005)
                stop_loss = last_close + stop_dist
                target = last_close - (stop_dist * 3.0)
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close, stop_loss=stop_loss, take_profit=target,
                    structure_summary=f"HyperScalper Hardened Short (Trend={trend_ema:.4f})",
                    invalidation_conditions="Bullish EMA cross",
                    management_instructions="Target 3R. Filtered by EMA 200 + RSI.",
                    risk_per_trade_pct=self.get_risk_pct(),
                    notes="Aggressive compounding scalper",
                    urgency="high"
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.slow_ema_period:
            return None
            
        fast_ema = calculate_ema(closes, self.fast_ema_period)
        slow_ema = calculate_ema(closes, self.slow_ema_period)
        
        pos_dir = open_position.get("direction")
        
        # Exit on reverse cross (Fast-Fail)
        if pos_dir == "long" and fast_ema < slow_ema:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "HyperScalper: Bearish EMA Cross Exit")
        if pos_dir == "short" and fast_ema > slow_ema:
            return close_position_decision(snapshot.symbol, snapshot.timeframe, "HyperScalper: Bullish EMA Cross Exit")
            
        # [DYNAMIC RISK] Breakeven & Trailing
        entry_price = float(open_position["entry_price"])
        current_price = snapshot.candles[-1].close
        current_stop = float(open_position.get("stop_price") or 0.0)
        
        initial_risk = abs(entry_price - current_stop)
        if initial_risk > 0:
            profit_dist = (current_price - entry_price) if pos_dir == "long" else (entry_price - current_price)
            r_multiple = profit_dist / initial_risk
            
            # 1. Breakeven
            if pos_dir == "long" and current_stop < entry_price and r_multiple >= 1.0:
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="management", action="hold", stop_loss=entry_price,
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R)"
                )
            if pos_dir == "short" and current_stop > entry_price and r_multiple >= 1.0:
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="management", action="hold", stop_loss=entry_price,
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R)"
                )

        # [SAFETY] Managed by StrategyEngine via SafetyGuard

        return None
