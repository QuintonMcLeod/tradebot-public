from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi, calculate_macd, calculate_macd_series
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)


class CryptoDoubleMACDStrategy(BaseStrategy):
    """
    Double MACD Scalper — Crypto-Optimized.
    
    Uses slow MACD for trend direction and fast MACD for entry timing on pullbacks.
    RSI filter ensures entries occur during pullback zones (not overextended).
    
    ⚠️ Designed for crypto markets. May not perform well on forex or equities.
    """
    ASSET_TAG = "crypto"

    def __init__(self,
                 slow_fast=26, slow_slow=52, slow_signal=18,
                 fast_fast=5, fast_slow=13, fast_signal=4,
                 rsi_period=10, rsi_pullback_low=35, rsi_pullback_high=65):
        super().__init__("crypto_double_macd")
        # Slow MACD — trend direction
        self.slow_fast = slow_fast
        self.slow_slow = slow_slow
        self.slow_signal = slow_signal
        # Fast MACD — entry timing
        self.fast_fast = fast_fast
        self.fast_slow = fast_slow
        self.fast_signal = fast_signal
        # RSI for pullback detection
        self.rsi_period = rsi_period
        self.rsi_pullback_low = rsi_pullback_low
        self.rsi_pullback_high = rsi_pullback_high

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        closes = [c.close for c in snapshot.candles]
        min_bars = self.slow_slow + self.slow_signal + 2
        if len(closes) < min_bars:
            return None

        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.002)
        rsi = calculate_rsi(closes, self.rsi_period)

        # Slow MACD — trend filter
        slow_macd, slow_sig, slow_hist = calculate_macd(
            closes, self.slow_fast, self.slow_slow, self.slow_signal
        )

        # Fast MACD — entry timing  
        fast_lines, fast_sigs, fast_hists = calculate_macd_series(
            closes, self.fast_fast, self.fast_slow, self.fast_signal
        )

        if len(fast_lines) < 2 or len(fast_sigs) < 2:
            return None

        # Detect fast MACD crossover
        fast_now = fast_lines[-1]
        fast_prev = fast_lines[-2]
        fsig_now = fast_sigs[-1]
        fsig_prev = fast_sigs[-2]

        fast_bull_cross = fast_prev <= fsig_prev and fast_now > fsig_now
        fast_bear_cross = fast_prev >= fsig_prev and fast_now < fsig_now

        # Handle pyramiding
        if open_position:
            max_entries = UserConfig.MAX_PYRAMID_ENTRIES
            if open_position.get("pyramid_count", 0) >= max_entries:
                return None
            if open_position.get("bars_since_scale", 0) < 4:
                return None  # Faster cooldown for scalper

            pos_dir = open_position.get("direction")
            entry_price = open_position.get("entry_price", last_close)

            if pos_dir == "long" and slow_hist > 0 and fast_bull_cross and last_close < entry_price:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="continuation", action="scale_in",
                    entry_price=last_close,
                    stop_loss=open_position.get("stop_loss"),
                    take_profit=open_position.get("take_profit"),
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Double MACD Scale-in (SlowH={slow_hist:.6f})",
                    invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                    management_instructions="Fast scalp pyramid.",
                    urgency="medium", notes="Crypto Double MACD pyramid"
                )
            if pos_dir == "short" and slow_hist < 0 and fast_bear_cross and last_close > entry_price:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="continuation", action="scale_in",
                    entry_price=last_close,
                    stop_loss=open_position.get("stop_loss"),
                    take_profit=open_position.get("take_profit"),
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"Double MACD Scale-in (SlowH={slow_hist:.6f})",
                    invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                    management_instructions="Fast scalp pyramid.",
                    urgency="medium", notes="Crypto Double MACD pyramid"
                )
            return None

        # --- Initial Entry ---
        # LONG: Slow MACD histogram > 0 (uptrend) + Fast MACD bullish crossover + RSI in pullback zone
        if slow_hist > 0 and fast_bull_cross and rsi < self.rsi_pullback_high:
            stop_dist = atr * 1.0  # Tight for scalping
            stop_loss = last_close - stop_dist
            take_profit = last_close + (stop_dist * 1.5)  # 1.5:1 RR for quick exits

            score = 60
            if rsi < self.rsi_pullback_low:
                score += 10  # Deep pullback = better entry
            if slow_hist > abs(slow_macd) * 0.3:
                score += 10  # Strong trend momentum

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Double MACD Long (SlowH={slow_hist:.6f}, FastX ✓, RSI={rsi:.1f})",
                invalidation_conditions=f"Close below {stop_loss:.5f}",
                management_instructions="Scalp exit at 1.5:1 RR or slow MACD flip.",
                urgency="medium",
                notes="Crypto Double MACD Scalper",
                score=score, grade="A" if score >= 70 else "B"
            )

        # SHORT: Slow MACD histogram < 0 (downtrend) + Fast MACD bearish crossover + RSI in pullback zone
        if slow_hist < 0 and fast_bear_cross and rsi > self.rsi_pullback_low:
            stop_dist = atr * 1.0
            stop_loss = last_close + stop_dist
            take_profit = last_close - (stop_dist * 1.5)

            score = 60
            if rsi > self.rsi_pullback_high:
                score += 10
            if abs(slow_hist) > abs(slow_macd) * 0.3:
                score += 10

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Double MACD Short (SlowH={slow_hist:.6f}, FastX ✓, RSI={rsi:.1f})",
                invalidation_conditions=f"Close above {stop_loss:.5f}",
                management_instructions="Scalp exit at 1.5:1 RR or slow MACD flip.",
                urgency="medium",
                notes="Crypto Double MACD Scalper",
                score=score, grade="A" if score >= 70 else "B"
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, **kwargs) -> Optional[AITradeDecision]:
        from tradebot_sci.strategy.decisions import close_position_decision

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.slow_slow + self.slow_signal + 2:
            return None

        # Exit when slow MACD flips against position
        slow_macd, slow_sig, slow_hist = calculate_macd(
            closes, self.slow_fast, self.slow_slow, self.slow_signal
        )

        direction = open_position.get("direction")

        if direction == "long" and slow_hist < 0:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Double MACD Exit Long (Slow MACD flipped bearish)"
            )

        if direction == "short" and slow_hist > 0:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Double MACD Exit Short (Slow MACD flipped bullish)"
            )

        return None
