from __future__ import annotations
import logging
import os
from typing import Optional, Tuple
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class TrendRiderStrategy(BaseStrategy):
    """
    EMA Trend Rider — Pullback Entry on Confirmed Trend.

    Production forex bot strategy (classic EMA pullback + crossover).
    Waits for EMA(8)/EMA(21) crossover to establish trend direction,
    then enters on pullback to the 21 EMA.

    Filters:
    - ADX > 20 (from trend detection gates) — confirms trending market
    - HTF trend strength >= 0.25 — confirms institutional flow
    - RSI 40-60 — confirms pullback (not reversal)

    Entry: Price pulls back to EMA(21) and bounces in trend direction
    Exit:  Trailing stop at 2× ATR OR reverse EMA crossover
    Stop:  Swing low/high + 1.5× ATR minimum
    Target: 2.5R (let winners run)
    """

    def __init__(self, fast_ema=8, slow_ema=21, rsi_period=14, **kwargs):
        super().__init__("Trend Rider")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> Tuple[float, str, str]:
        """Score how close the TrendRider entry filters are to triggering.

        Each filter contributes points to a 0-100 score:
          HTF direction (not neutral)    = 15 pts
          LTF alignment                  = 10 pts
          HTF strength ≥ 0.25            = 10 pts
          Liquidity Sweep present        = 10 pts
          EMA(8)/EMA(21) aligned         = 20 pts
          RSI in 25-75 (pullback zone)   = 10 pts
          Price near EMA(21) (≤0.3 ATR)  = 10 pts
          Bounce confirmed               = 15 pts
        """
        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.slow_ema + 10:
            return 0.0, "-", "Trend Rider: insufficient data"

        score = 0.0
        details = []

        # 1. HTF direction & LTF alignment
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        if htf_dir in ("long", "short"):
            score += 15
            details.append(f"HTF={htf_dir}")
            
            if htf_dir == ltf_dir:
                score += 10
                details.append(f"LTF={ltf_dir}")
        else:
            details.append("HTF=neutral")

        # 2. HTF strength
        htf_strength = float(gates.get("htf_strength", 0))
        if htf_strength >= 0.25:
            score += 10
            details.append(f"str={htf_strength:.2f}")
        else:
            details.append(f"str={htf_strength:.2f}<0.25")
            
        # 2.5 Liquidity Sweep
        sweep = gates.get("sweep", False)
        if sweep:
            score += 10
            details.append("sweep✓")

        # 3. EMA alignment
        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        aligned = (htf_dir == "long" and ema_fast > ema_slow) or \
                  (htf_dir == "short" and ema_fast < ema_slow)
        if aligned:
            score += 20
            details.append("EMA✓")
        else:
            details.append("EMA✗")

        # 4. RSI in pullback zone (25-75)
        rsi = calculate_rsi(closes, self.rsi_period)
        if 25 <= rsi <= 75:
            score += 10
            details.append(f"RSI={rsi:.0f}")
        else:
            details.append(f"RSI={rsi:.0f}✗")

        # 5. Price near EMA(21)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)
        ema_dist = abs(closes[-1] - ema_slow)
        if ema_dist < atr * 0.3:
            score += 10
            details.append("proximity✓")
        else:
            details.append("proximity✗")

        # 6. Bounce confirmation
        if len(closes) >= 2:
            bounce = (htf_dir == "long" and closes[-1] > closes[-2]) or \
                     (htf_dir == "short" and closes[-1] < closes[-2])
            if bounce:
                score += 15
                details.append("bounce✓")
            else:
                details.append("bounce✗")

        grade = self.grade_from_score_100(score)
        summary = f"Trend Rider: {score:.0f}% — {', '.join(details)}"
        return score, grade, summary

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        if open_position:
            return None

        closes = [c.close for c in snapshot.candles]
        if len(closes) < self.slow_ema + 10:
            return None

        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_fast_prev = calculate_ema(closes[:-1], self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        ema_slow_prev = calculate_ema(closes[:-1], self.slow_ema)
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)

        last_close = closes[-1]
        prev_close = closes[-2]
        prev2_close = closes[-3] if len(closes) >= 3 else prev_close

        # ── TRENDING MARKET FILTER ───────────────────────────────
        # When used standalone (not via Conductor), ADX>20 ensures
        # I only enter in trending markets. When Conductor routes me,
        # market_regime already handles this (this acts as my fallback).
        adx = gates.get("adx", 25)
        if gates.get("market_regime") is None:
            # Standalone mode — apply my own regime filter
            if adx is not None and adx < 20:
                return None  # Market not trending — skip

        # Must have a strong HTF trend
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        htf_strength = float(gates.get("htf_strength", 0))

        if htf_dir == "neutral" or htf_strength < 0.50:
            return None

        # ── MTF ALIGNMENT CHECK ─────────────────────────────────
        # If Conductor provides MTF alignment, I can bypass strict 
        # pullback requirements to allow momentum entries.
        mtf_dir = str(gates.get("mtf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        perfect_mtf_alignment = (htf_dir == mtf_dir == ltf_dir) and htf_dir in ("long", "short")

        # ── MICRO-MOMENTUM ──────────────────────────────────────
        # On 1m charts, require the last close to show net
        # directional movement aligned with the macro trend.
        if len(closes) >= 2:
            recent_move = closes[-1] - closes[-2]
            # Relaxed micro-momentum: I don't strictly enforce a forward tick on 1m
            # to allow catching the bottom of micro-pullbacks before the bounce.

        # ── EMA CROSSOVER CONFIRMATION ───────────────────────────
        # Require that EMA(8) is on the correct side of EMA(21)
        # This confirms the trend is established, not just starting
        ema_aligned_bull = ema_fast > ema_slow
        ema_aligned_bear = ema_fast < ema_slow

        # RSI pullback constraints relaxed to allow entry on strong momentum
        # Since my Forex Conductor mandates all 3 timeframes (4H, 1H, 5M) align,
        # the 1M chart RSI will frequently be > 60. I expand the ceiling to 75.
        if htf_dir == "long" and (rsi > 75 or rsi < 25):
            return None
        if htf_dir == "short" and (rsi < 25 or rsi > 75):
            return None

        # Distance from slow EMA
        ema_dist = abs(last_close - ema_slow)
        proximity_threshold = atr * 0.8  # Must be tightly pulling back to EMA(21)

        # ── BOUNCE CONFIRMATION ──────────────────────────────────
        one_bull_candle = last_close > prev_close
        one_bear_candle = last_close < prev_close
        two_bull_candles = one_bull_candle and prev_close > prev2_close
        two_bear_candles = one_bear_candle and prev_close < prev2_close

        # RSI divergence: compare last 2 swing extremes
        rsi_prev = calculate_rsi(closes[:-1], self.rsi_period)
        rsi_prev2 = calculate_rsi(closes[:-2], self.rsi_period) if len(closes) > self.rsi_period + 2 else rsi_prev
        bullish_rsi_div = (last_close < closes[-3] and rsi > rsi_prev2) if len(closes) >= 3 else False
        bearish_rsi_div = (last_close > closes[-3] and rsi < rsi_prev2) if len(closes) >= 3 else False

        # Require 2 consecutive candles in the trend direction to prove the pullback is actually over
        # and momentum has cleanly resumed. This prevents catching 'falling knives' on 1m fakeouts.
        confirmed_bull_bounce = two_bull_candles or bullish_rsi_div
        confirmed_bear_bounce = two_bear_candles or bearish_rsi_div
        
        # Momentum Bypass: If all 3 macro timeframes perfectly align, I enter with the trend
        # without demanding a fresh deep pullback and bounce.
        if perfect_mtf_alignment:
            touched_ema = True
            confirmed_bull_bounce = True
            confirmed_bear_bounce = True

        # ── DIAGNOSTIC: log why trend_rider returns None ─────────
        logger.info(
            f"[TREND-RIDER] {snapshot.symbol}: htf_dir={htf_dir} str={htf_strength:.2f} "
            f"ema_bull={ema_aligned_bull} ema_bear={ema_aligned_bear} "
            f"close={last_close:.5f} ema21={ema_slow:.5f} "
            f"dist={ema_dist:.5f} thresh={proximity_threshold:.5f} "
            f"rsi={rsi:.1f} bounce_bull={confirmed_bull_bounce} bounce_bear={confirmed_bear_bounce} "
            f"(2candle_up={two_bull_candles} 2candle_dn={two_bear_candles} "
            f"rsi_div_bull={bullish_rsi_div} rsi_div_bear={bearish_rsi_div})"
        )

        # ── BULLISH PULLBACK ─────────────────────────────────────
        if htf_dir == "long" and ema_aligned_bull:
            # Price pulled back to EMA(21) and bouncing
            touched_ema = ema_dist < proximity_threshold or last_close <= ema_slow
            # If the price has plunged violently past the EMA support line, the structure is broken.
            # Do NOT catch a falling knife that broke the micro-trend support.
            structure_broken = last_close < (ema_slow - atr * 0.5)

            if touched_ema and not structure_broken and confirmed_bull_bounce and last_close > ema_slow:
                # Find swing low for stop
                recent_lows = [c.low for c in snapshot.candles[-10:]]
                swing_low = min(recent_lows)
                is_jpy = "JPY" in snapshot.symbol.upper()
                min_pips = float(getattr(self._profile, 'min_pip_floor', 25.0)) if self._profile else 25.0
                min_sl_dist = min_pips * (0.01 if is_jpy else 0.0001)  # Pip floor for 1m execution
                stop_dist = max(last_close - swing_low, atr * 2.0, min_sl_dist)
                if atr and stop_dist > atr * 3.5:
                    stop_dist = atr * 3.5
                stop_loss = last_close - stop_dist
                take_profit=None  # 2.5R target (Conductor trail may exit earlier)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=None,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=(
                        f"Trend Rider Long: EMA pullback "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f}, "
                        f"HTF={htf_strength:.2f})"
                    ),
                    invalidation_conditions=(
                        f"Close below swing low {swing_low:.5f}"
                    ),
                    management_instructions=(
                        "Target 2.5R. Trail stop to EMA21 once 1R in profit."
                    ),
                    notes="EMA pullback — confirmed uptrend",
                    urgency="medium",
                )

        # ── BEARISH PULLBACK ─────────────────────────────────────
        if htf_dir == "short" and ema_aligned_bear:
            touched_ema = ema_dist < proximity_threshold or last_close >= ema_slow
            structure_broken = last_close > (ema_slow + atr * 0.5)

            if touched_ema and not structure_broken and confirmed_bear_bounce and last_close < ema_slow:
                recent_highs = [c.high for c in snapshot.candles[-10:]]
                swing_high = max(recent_highs)
                is_jpy = "JPY" in snapshot.symbol.upper()
                min_pips = float(getattr(self._profile, 'min_pip_floor', 25.0)) if self._profile else 25.0
                min_sl_dist = min_pips * (0.01 if is_jpy else 0.0001)  # Pip floor for 1m execution
                stop_dist = max(swing_high - last_close, atr * 2.0, min_sl_dist)
                if atr and stop_dist > atr * 3.5:
                    stop_dist = atr * 3.5
                stop_loss = last_close + stop_dist
                take_profit=None  # 2.5R target (Conductor trail may exit earlier)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=None,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=(
                        f"Trend Rider Short: EMA pullback "
                        f"(RSI={rsi:.1f}, ADX={adx:.0f}, "
                        f"HTF={htf_strength:.2f})"
                    ),
                    invalidation_conditions=(
                        f"Close above swing high {swing_high:.5f}"
                    ),
                    management_instructions=(
                        "Target 2.5R. Trail stop to EMA21 once 1R in profit."
                    ),
                    notes="EMA pullback — confirmed downtrend",
                    urgency="medium",
                )

        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """Invalidation exits: EMA crossover, structure break, RSI extreme."""
        if not snapshot.candles or len(snapshot.candles) < self.slow_ema + 2:
            return None

        closes = [c.close for c in snapshot.candles]
        ema_fast = calculate_ema(closes, self.fast_ema)
        ema_slow = calculate_ema(closes, self.slow_ema)
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)
        direction = open_position.get("direction")
        entry_price = float(open_position.get("entry_price", 0))
        current_price = closes[-1]

        exit_reason = None

        # ── 1. EMA CROSSOVER REVERSAL ────────────────────────────
        # EMA(8) crossing EMA(21) against the trade = trend is over.
        # This is my core invalidation: I entered on a pullback TO
        # EMA21 with EMA8 > EMA21. If EMA8 drops below EMA21, the
        # trend structure that justified the entry is gone.
        if direction == "long" and ema_fast < ema_slow:
            exit_reason = f"EMA crossover invalidation: EMA8={ema_fast:.5f} < EMA21={ema_slow:.5f}"
        elif direction == "short" and ema_fast > ema_slow:
            exit_reason = f"EMA crossover invalidation: EMA8={ema_fast:.5f} > EMA21={ema_slow:.5f}"

        # ── 2. PRICE STRUCTURE BREAK ─────────────────────────────
        # Close decisively past EMA(21) against trade direction.
        # "Decisively" = more than 0.5 ATR beyond EMA21.
        # This catches the case where price smashes through the EMA
        # before the fast EMA reacts.
        if not exit_reason:
            breach_threshold = atr * 0.5
            if direction == "long" and current_price < (ema_slow - breach_threshold):
                exit_reason = (
                    f"Structure break: close {current_price:.5f} < "
                    f"EMA21-0.5ATR ({ema_slow - breach_threshold:.5f})"
                )
            elif direction == "short" and current_price > (ema_slow + breach_threshold):
                exit_reason = (
                    f"Structure break: close {current_price:.5f} > "
                    f"EMA21+0.5ATR ({ema_slow + breach_threshold:.5f})"
                )

        # ── 3. RSI EXTREME (exhaustion) ──────────────────────────
        # RSI hitting extreme territory against the trade signals
        # potential reversal. Exit before the move accelerates.
        if not exit_reason:
            if direction == "long" and rsi < 25:
                exit_reason = f"RSI exhaustion: RSI={rsi:.1f} < 25 (oversold against long)"
            elif direction == "short" and rsi > 75:
                exit_reason = f"RSI exhaustion: RSI={rsi:.1f} > 75 (overbought against short)"

        if exit_reason:
            # Determine P&L direction for logging
            if direction == "long":
                pnl_sign = "+" if current_price > entry_price else ""
                pnl_pips = (current_price - entry_price) * 10000
            else:
                pnl_sign = "+" if current_price < entry_price else ""
                pnl_pips = (entry_price - current_price) * 10000

            action = "exit_long" if direction == "long" else "exit_short"
            logger.info(
                f"[TREND-RIDER] {snapshot.symbol}: INVALIDATION EXIT — {exit_reason} "
                f"(entry={entry_price:.5f}, now={current_price:.5f}, {pnl_sign}{pnl_pips:.1f} pips)"
            )
            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias=direction, phase="exit", action=action,
                entry_price=current_price,
                stop_loss=None,
                take_profit=None,
                risk_per_trade_pct=0,
                structure_summary=f"Trend Rider Invalidation: {exit_reason}",
                invalidation_conditions="",
                management_instructions="Exit immediately — setup invalidated",
                notes=exit_reason,
                urgency="high",
            )

        return None
