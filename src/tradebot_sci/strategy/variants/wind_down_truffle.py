"""
Wind Down Truffle — Friday Afternoon Fade Strategy

Captures the Friday wind-down drift where liquidity thins and
prices tend to fade toward weekly close.

Active window: Friday 12:00 PM – 4:30 PM ET
Bias: Short (markets typically drift down into the close)
SAR: Relied upon to catch occasional late squeeze spikes

Entry criteria:
- Friday afternoon within the active window
- Price drifting BELOW VWAP (confirming fade)
- EMA(8) < EMA(21) (short-term momentum declining)
- No volume surge (thin liquidity = fade, not breakout)

Exit: SAR handles reversals. Strategy defers to SafetyGuard
for TP/SL management.

R:R: 2:1 minimum (tight stop, let the fade run).
"""

from __future__ import annotations
import logging
from datetime import time
from zoneinfo import ZoneInfo
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class WindDownTruffleStrategy(BaseStrategy):
    """
    Friday Wind-Down Truffle — short-biased fade into the weekly close.
    Relies on SAR to catch occasional late-session spikes.
    """

    # Friday afternoon window (Eastern Time)
    WIND_DOWN_START = time(12, 0)   # 12:00 PM ET
    WIND_DOWN_END   = time(16, 30)  # 4:30 PM ET (30 min before close)

    # EMAs for momentum confirmation
    EMA_FAST = 8
    EMA_SLOW = 21

    def __init__(self):
        super().__init__("Wind Down Truffle")

    def _is_friday_afternoon(self, snapshot: MarketSnapshot) -> bool:
        """Check if we're in the Friday wind-down window."""
        if not snapshot.candles:
            return False

        ts = snapshot.candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("UTC"))

        et = ts.astimezone(ZoneInfo("America/New_York"))

        # Friday = weekday 4
        if et.weekday() != 4:
            return False

        return self.WIND_DOWN_START <= et.time() < self.WIND_DOWN_END

    @staticmethod
    def _ema(closes: list[float], period: int) -> float:
        """Calculate EMA of the last `period` values."""
        if len(closes) < period:
            return closes[-1]
        k = 2.0 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema

    def _calculate_vwap(self, snapshot: MarketSnapshot) -> float | None:
        """Calculate session VWAP from available candles."""
        if not snapshot.candles or len(snapshot.candles) < 5:
            return None
        total_vol = 0.0
        total_pv = 0.0
        for c in snapshot.candles[-30:]:
            typical = (c.high + c.low + c.close) / 3.0
            vol = c.volume if c.volume > 0 else 1.0
            total_pv += typical * vol
            total_vol += vol
        return total_pv / total_vol if total_vol > 0 else None

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        if open_position:
            return None

        # ── GATE 1: Must be Friday afternoon ─────────────────────
        if not self._is_friday_afternoon(snapshot):
            return None

        if len(snapshot.candles) < 30:
            return None

        closes = [c.close for c in snapshot.candles]
        last_close = closes[-1]
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # ── GATE 2: VWAP drift — price below VWAP ───────────────
        vwap = self._calculate_vwap(snapshot)
        if vwap is None:
            return None

        if last_close >= vwap:
            return None  # Price above VWAP — no fade confirmed

        # ── GATE 3: EMA momentum declining ───────────────────────
        ema_fast = self._ema(closes, self.EMA_FAST)
        ema_slow = self._ema(closes, self.EMA_SLOW)

        if ema_fast >= ema_slow:
            return None  # Short-term momentum not declining

        # ── GATE 4: No volume surge (thin liquidity = fade) ──────
        recent_vols = [c.volume for c in snapshot.candles[-20:-1] if c.volume > 0]
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1.0
        curr_vol = snapshot.candles[-1].volume if snapshot.candles[-1].volume > 0 else 0

        if curr_vol > avg_vol * 2.5:
            return None  # Volume surge = potential breakout, not fade

        # ── ENTRY: Short — Friday fade confirmed ─────────────────
        vwap_dist = abs(vwap - last_close)
        stop_dist = atr * 1.2 + vwap_dist  # Above VWAP + ATR buffer
        stop_loss = last_close + stop_dist
        take_profit=None  # 2:1 R:R

        logger.info(
            f"[WIND_DOWN] {snapshot.symbol}: Friday fade SHORT "
            f"@ {last_close:.5f} (VWAP={vwap:.5f}, "
            f"EMA8={ema_fast:.5f} < EMA21={ema_slow:.5f})"
        )

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias="short",
            phase="trend",
            action="enter_short",
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=None,
            risk_per_trade_pct=self.get_risk_pct(fallback=0.01),
            structure_summary=(
                f"Wind Down Truffle: Friday fade "
                f"(VWAP drift={vwap_dist/atr:.1f}R, "
                f"EMA8<21)"
            ),
            invalidation_conditions="Price returns above VWAP",
            management_instructions="Target 2R. SAR handles spikes.",
            notes="Friday wind-down fade — short-biased",
            urgency="medium",
        )

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """Close at 5PM ET Friday — the weekly forex close."""
        if not snapshot.candles:
            return None

        ts = snapshot.candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("UTC"))

        et = ts.astimezone(ZoneInfo("America/New_York"))

        # Only relevant on Fridays at or past 5PM ET
        if et.weekday() == 4 and et.hour >= 17:
            from tradebot_sci.strategy.decisions import close_position_decision
            logger.info(
                f"[WIND_DOWN] {snapshot.symbol}: Friday close @ 5PM ET — "
                f"closing wind-down trade"
            )
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                reason="Wind Down Truffle: Friday 5PM Close"
            )

        return None
