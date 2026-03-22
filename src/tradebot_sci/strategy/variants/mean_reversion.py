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
                 rsi_overbought=70, rsi_oversold=30, **kwargs):
        super().__init__("Mean Reversion")
        self.bb_period = int(kwargs.get('bb_period', bb_period))
        self.bb_std = float(kwargs.get('bb_std', bb_std))
        self.rsi_period = int(kwargs.get('rsi_period', rsi_period))
        self.rsi_overbought = float(kwargs.get('rsi_overbought', rsi_overbought))
        self.rsi_oversold = float(kwargs.get('rsi_oversold', rsi_oversold))

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """Score how close current conditions are to a Mean Reversion entry.

        Each factor contributes points to a 0-100 score:
          Price at/outside BB edge            = 25 pts
          RSI in exhaustion zone (≤25 or ≥75) = 25 pts
          BB width (not squeezed)             = 20 pts
          HTF direction alignment             = 15 pts
          Bounce confirmation (last 3 bars)   = 15 pts
        """
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.bb_period + 5:
            return 0.0, "F-", "Mean Reversion: insufficient data"

        score = 0.0
        details = []

        lower, middle, upper = calculate_bollinger_bands(
            closes, self.bb_period, self.bb_std
        )
        rsi = calculate_rsi(closes, self.rsi_period)
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # 1. BB proximity — how close/beyond the bands?
        if last_close <= lower:
            score += 25
            details.append("BB-lower✓")
        elif last_close >= upper:
            score += 25
            details.append("BB-upper✓")
        else:
            bb_range = upper - lower
            if bb_range > 0:
                dist_to_edge = min(abs(last_close - lower), abs(last_close - upper))
                pct_from_edge = dist_to_edge / bb_range
                if pct_from_edge < 0.15:
                    score += 15
                    details.append("BB-near")
                elif pct_from_edge < 0.3:
                    score += 8
                    details.append("BB-mid")
                else:
                    details.append("BB-center")

        # 2. RSI exhaustion
        if rsi <= self.rsi_oversold:
            score += 25
            details.append(f"RSI={rsi:.0f}↓")
        elif rsi >= self.rsi_overbought:
            score += 25
            details.append(f"RSI={rsi:.0f}↑")
        elif rsi <= 35 or rsi >= 65:
            score += 12
            details.append(f"RSI={rsi:.0f}~")
        else:
            details.append(f"RSI={rsi:.0f}")

        # 3. BB width (not squeezed)
        bb_width = upper - lower
        if bb_width >= atr * 1.0:
            score += 20
            details.append("width✓")
        elif bb_width >= atr * 0.5:
            score += 10
            details.append("width~")
        else:
            details.append("squeeze")

        # 4. HTF direction alignment
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        if (last_close <= lower and htf_dir in ("long", "neutral")) or \
           (last_close >= upper and htf_dir in ("short", "neutral")):
            score += 15
            details.append(f"HTF={htf_dir}✓")
        elif htf_dir != "neutral":
            score += 5
            details.append(f"HTF={htf_dir}")
        else:
            details.append("HTF=neutral")

        # 5. Bounce confirmation (recent candles showing reversal)
        if len(closes) >= 3:
            recent_lows_touching = any(
                c.low <= lower for c in snapshot.candles[-3:]
            )
            recent_highs_touching = any(
                c.high >= upper for c in snapshot.candles[-3:]
            )
            bounce_up = last_close > closes[-2] and recent_lows_touching
            bounce_down = last_close < closes[-2] and recent_highs_touching
            if bounce_up or bounce_down:
                score += 15
                details.append("bounce✓")
            elif recent_lows_touching or recent_highs_touching:
                score += 8
                details.append("touch~")
            else:
                details.append("no-touch")

        grade = self.grade_from_score_100(score)
        summary = f"Mean Reversion: {score:.0f}% — {', '.join(details)}"
        return score, grade, summary

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
        # NOTE: engine gates publish "htf_adx" and "adx" (same value).
        adx = gates.get("htf_adx") or gates.get("adx")

        if gates.get("market_regime") is None:
            # ── STANDALONE WARMUP + REGIME GUARD ─────────────────
            # Only needed standalone — conductor already verified regime.
            if adx is None:
                return None  # HTF truly hasn't initialized — wait for warm-up
            if adx > 25:
                return None  # Market is trending — skip mean reversion

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis.
        # When HTF is neutral (ranging/flat market), use LTF price action
        # alone to determine direction — BB bounce defines trade direction.
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_strength = float(gates.get("htf_strength", 0.0))

        # ── BOUNCE CONFIRMATION ──────────────────────────────────
        # Require that the previous candle touched/pierced the BB
        # but the current candle is closing back inside = bounce started

        # ── LONG: Price bouncing off lower BB ────────────────────
        # Allow when HTF is bullish, OR neutral AND genuinely flat (htf_strength<0.25).
        # Neutral+strong = developing trend — avoid counter-trend entries.
        is_long_allowed  = (htf_dir == "long") or (htf_dir == "neutral" and htf_strength < 0.25)
        is_short_allowed = (htf_dir == "short") or (htf_dir == "neutral" and htf_strength < 0.25)

        if is_long_allowed:
            prev_touched_lower = prev_close <= lower or min(
                c.low for c in snapshot.candles[-3:]
            ) <= lower
            bouncing_back = last_close > lower  # Closing back inside bands
            rsi_oversold = rsi < 35  # Restored from 25 — 5m bars rarely hit RSI<25

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
        # Allow when HTF is bearish, OR neutral AND genuinely flat (htf_strength<0.25).
        if is_short_allowed:
            prev_touched_upper = prev_close >= upper or max(
                c.high for c in snapshot.candles[-3:]
            ) >= upper
            bouncing_back = last_close < upper  # Closing back inside bands
            rsi_overbought = rsi > 65  # Restored from 75 — 5m bars rarely hit RSI>75

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

        pass

        return None
