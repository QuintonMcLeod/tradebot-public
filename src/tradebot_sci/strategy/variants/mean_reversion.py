from __future__ import annotations
import logging
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_bollinger_bands, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Scalper — Bollinger Band + RSI.

    Production forex bot strategy (Evening Scalper Pro style).
    Trades when price is overextended outside bands and RSI shows exhaustion.
    Best during quiet/ranging markets (ADX < 25).

    Entry: Price closes outside BB(20,2) + RSI exhaustion
    Exit:  Price returns to middle BB (SMA 20) = take profit
    Stop:  1.5× ATR beyond the outer band
    """

    def __init__(self, bb_period=20, bb_std=2.0, rsi_period=14,
                 rsi_overbought=75, rsi_oversold=25):
        super().__init__("Mean Reversion")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           **kwargs) -> Optional[AITradeDecision]:
        if open_position:
            return None

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period + 5:
            return None

        lower, middle, upper = calculate_bollinger_bands(
            closes, self.bb_period, self.bb_std
        )
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        prev_close = closes[-2]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # ── BB WIDTH FILTER ──────────────────────────────────────
        # Skip entries when bands are too narrow (squeeze) — false bounces
        bb_width = upper - lower
        if bb_width < atr * 0.5:
            return None  # Bands too narrow, squeeze condition

        # ── RANGING MARKET FILTER ────────────────────────────────
        # When used standalone (not via Conductor), ADX<25 ensures
        # we only enter in ranging markets. When Conductor routes us,
        # market_regime already handles this (this acts as fallback).
        adx = gates.get("adx", 20)
        if gates.get("market_regime") is None:
            # Standalone mode — apply our own regime filter
            if adx is not None and adx > 25:
                return None  # Market is trending — skip

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # ── BOUNCE CONFIRMATION ──────────────────────────────────
        # Require that the previous candle touched/pierced the BB
        # but the current candle is closing back inside = bounce started

        # ── LONG: Price bouncing off lower BB ────────────────────
        if htf_dir in ("long", "neutral"):
            prev_touched_lower = prev_close <= lower or min(
                c.low for c in snapshot.candles[-3:]
            ) <= lower
            bouncing_back = last_close > lower  # Closing back inside bands
            rsi_oversold = rsi < self.rsi_oversold

            if prev_touched_lower and bouncing_back and rsi_oversold:
                stop_loss = last_close - (atr * 1.2)  # Moderately wide stop
                risk = abs(last_close - stop_loss)
                take_profit = last_close + (risk * 2.0)  # 2:1 R:R always

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="long", phase="correction", action="enter_long",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(fallback=0.01),
                    structure_summary=(
                        f"Mean Reversion Long: BB bounce "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f})"
                    ),
                    invalidation_conditions=f"Close below {stop_loss:.5f}",
                    management_instructions="Target middle BB. Move to BE at 1R.",
                    notes="BB+RSI mean reversion — ranging market",
                    urgency="medium",
                )

        # ── SHORT: Price bouncing off upper BB ───────────────────
        if htf_dir in ("short", "neutral"):
            prev_touched_upper = prev_close >= upper or max(
                c.high for c in snapshot.candles[-3:]
            ) >= upper
            bouncing_back = last_close < upper  # Closing back inside bands
            rsi_overbought = rsi > self.rsi_overbought

            if prev_touched_upper and bouncing_back and rsi_overbought:
                stop_loss = last_close + (atr * 1.2)  # Equalized with long side
                risk = abs(stop_loss - last_close)
                take_profit = last_close - (risk * 2.0)  # 2:1 R:R always

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="short", phase="correction", action="enter_short",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(fallback=0.01),
                    structure_summary=(
                        f"Mean Reversion Short: BB bounce "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f})"
                    ),
                    invalidation_conditions=f"Close above {stop_loss:.5f}",
                    management_instructions="Target middle BB. Move to BE at 1R.",
                    notes="BB+RSI mean reversion — ranging market",
                    urgency="medium",
                )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot,
                          open_position: dict, gates: dict,
                          **kwargs) -> Optional[AITradeDecision]:
        """All exits managed by backtester TP/SL. No early exit."""
        if not open_position or not snapshot.candles:
            return None

        # Breakeven management only
        entry_price = float(open_position["entry_price"])
        current_price = snapshot.candles[-1].close
        current_stop = float(open_position.get("stop_price") or 0.0)
        direction = open_position.get("direction")
        initial_risk = abs(entry_price - current_stop)

        if initial_risk > 0:
            profit_dist = (
                (current_price - entry_price)
                if direction == "long"
                else (entry_price - current_price)
            )
            r_multiple = profit_dist / initial_risk
            if direction == "long" and current_stop < entry_price and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="management", action="hold",
                    stop_loss=entry_price,
                    notes="[MANAGEMENT] Mean Reversion: stop → BREAKEVEN (1R)"
                )
            if direction == "short" and current_stop > entry_price and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="management", action="hold",
                    stop_loss=entry_price,
                    notes="[MANAGEMENT] Mean Reversion: stop → BREAKEVEN (1R)"
                )

        return None
