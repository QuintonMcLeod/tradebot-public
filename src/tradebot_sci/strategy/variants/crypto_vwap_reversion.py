from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi, calculate_ema, calculate_vwap
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.config.models import UserConfig

logger = logging.getLogger(__name__)


class CryptoVWAPReversionStrategy(BaseStrategy):
    """
    VWAP Mean Reversion — Crypto-Optimized.
    
    Buy below VWAP in uptrending markets, sell above VWAP in downtrending.
    Uses EMA-20 as trend filter and RSI for confirmation.
    
    ⚠️ Designed for crypto markets. May not perform well on forex or equities.
    """
    ASSET_TAG = "crypto"

    def __init__(self, ema_period=20, rsi_period=14,
                 rsi_long_threshold=40, rsi_short_threshold=60,
                 vwap_deviation_pct=0.003, **kwargs):
        super().__init__("crypto_vwap_reversion")
        self.ema_period = int(kwargs.get('ema_period', ema_period))
        self.rsi_period = int(kwargs.get('rsi_period', rsi_period))
        self.rsi_long_threshold = float(kwargs.get('rsi_long_threshold', rsi_long_threshold))
        self.rsi_short_threshold = float(kwargs.get('rsi_short_threshold', rsi_short_threshold))
        self.vwap_deviation_pct = float(kwargs.get('vwap_deviation_pct', vwap_deviation_pct))

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        closes = [c.close for c in candles]

        if len(closes) < max(self.ema_period + 5, 30):
            return None

        last_close = closes[-1]
        vwap = calculate_vwap(candles)
        ema = calculate_ema(closes, self.ema_period)
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = calculate_atr(candles, period=14) or (last_close * 0.002)

        if vwap == 0 or ema == 0:
            return None

        deviation = (last_close - vwap) / vwap
        prev_ema = calculate_ema(closes[:-1], self.ema_period)
        ema_rising = ema > prev_ema
        ema_falling = ema < prev_ema

        # Handle pyramiding
        if open_position:
            max_entries = UserConfig.MAX_PYRAMID_ENTRIES
            if open_position.get("pyramid_count", 0) >= max_entries:
                return None
            if open_position.get("bars_since_scale", 0) < 6:
                return None

            pos_dir = open_position.get("direction")
            entry_price = open_position.get("entry_price", last_close)

            if pos_dir == "long" and deviation < -self.vwap_deviation_pct * 2 and last_close < entry_price:
                if rsi < 25:
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="correction", action="scale_in",
                        entry_price=last_close,
                        stop_loss=open_position.get("stop_loss"),
                        take_profit=vwap + (atr * 0.5),
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"VWAP Scale-in (Dev={deviation:.4f}, RSI={rsi:.1f})",
                        invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                        management_instructions="Target VWAP reversion.",
                        urgency="high", notes="Crypto VWAP pyramid"
                    )
            if pos_dir == "short" and deviation > self.vwap_deviation_pct * 2 and last_close > entry_price:
                if rsi > 75:
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="correction", action="scale_in",
                        entry_price=last_close,
                        stop_loss=open_position.get("stop_loss"),
                        take_profit=vwap - (atr * 0.5),
                        risk_per_trade_pct=self.get_risk_pct(),
                        structure_summary=f"VWAP Scale-in (Dev={deviation:.4f}, RSI={rsi:.1f})",
                        invalidation_conditions=f"Stop at {open_position.get('stop_loss')}",
                        management_instructions="Target VWAP reversion.",
                        urgency="high", notes="Crypto VWAP pyramid"
                    )
            return None

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # LONG: Price below VWAP + EMA trending up + RSI < threshold (only when trend allows)
        if htf_dir in ("long", "neutral") and deviation < -self.vwap_deviation_pct and ema_rising and rsi < self.rsi_long_threshold:
            stop_dist = atr * UserConfig.STOP_ATR_MULTIPLIER
            stop_loss = last_close - stop_dist
            target = vwap + (vwap - last_close) * 0.5
            min_target = last_close + (stop_dist * 2.0)
            take_profit = max(target, min_target)

            score = 55
            if deviation < -self.vwap_deviation_pct * 2:
                score += 10
            if rsi < 30:
                score += 10

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="long", phase="correction", action="enter_long",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"VWAP Reversion Long (VWAP={vwap:.5f}, Dev={deviation:.4f})",
                invalidation_conditions=f"Close below {stop_loss:.5f}",
                management_instructions="Target VWAP reversion + extension. Exit if EMA flips.",
                urgency="high" if deviation < -self.vwap_deviation_pct * 2 else "medium",
                notes="Crypto VWAP Mean Reversion",
                score=score, grade="A" if score >= 70 else "B"
            )

        # SHORT: Price above VWAP + EMA trending down + RSI > threshold (only when trend allows)
        if htf_dir in ("short", "neutral") and deviation > self.vwap_deviation_pct and ema_falling and rsi > self.rsi_short_threshold:
            stop_dist = atr * UserConfig.STOP_ATR_MULTIPLIER
            stop_loss = last_close + stop_dist
            target = vwap - (last_close - vwap) * 0.5
            min_target = last_close - (stop_dist * 2.0)
            take_profit = min(target, min_target)

            score = 55
            if deviation > self.vwap_deviation_pct * 2:
                score += 10
            if rsi > 70:
                score += 10

            return AITradeDecision(
                symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                bias="short", phase="correction", action="enter_short",
                entry_price=last_close, stop_loss=stop_loss, take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"VWAP Reversion Short (VWAP={vwap:.5f}, Dev={deviation:.4f})",
                invalidation_conditions=f"Close above {stop_loss:.5f}",
                management_instructions="Target VWAP reversion + extension. Exit if EMA flips.",
                urgency="high" if deviation > self.vwap_deviation_pct * 2 else "medium",
                notes="Crypto VWAP Mean Reversion",
                score=score, grade="A" if score >= 70 else "B"
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, **kwargs) -> Optional[AITradeDecision]:
        from tradebot_sci.strategy.decisions import close_position_decision

        candles = snapshot.candles
        closes = [c.close for c in candles]
        if len(closes) < self.ema_period + 5:
            return None

        last_close = closes[-1]
        vwap = calculate_vwap(candles)
        ema = calculate_ema(closes, self.ema_period)
        prev_ema = calculate_ema(closes[:-1], self.ema_period)

        direction = open_position.get("direction")

        if direction == "long":
            if last_close >= vwap or ema < prev_ema:
                return close_position_decision(
                    snapshot.symbol, snapshot.timeframe,
                    f"VWAP Reversion Exit Long (Price={last_close:.5f}, VWAP={vwap:.5f})"
                )

        if direction == "short":
            if last_close <= vwap or ema > prev_ema:
                return close_position_decision(
                    snapshot.symbol, snapshot.timeframe,
                    f"VWAP Reversion Exit Short (Price={last_close:.5f}, VWAP={vwap:.5f})"
                )

        return None
