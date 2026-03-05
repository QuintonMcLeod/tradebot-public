from __future__ import annotations
import logging
from datetime import time, datetime
from zoneinfo import ZoneInfo
from typing import Optional
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class SessionMomentumStrategy(BaseStrategy):
    """
    Session Momentum: VWAP + Volume Surge at Market Open.

    Captures the initial directional move during the highest-volume
    period of the trading day. Active only in the first 30 minutes
    of London or NY session.

    Entry criteria:
    - Within active session window (London 08:00-08:30 GMT or NY 09:30-10:00 ET)
    - Price breaks above/below VWAP
    - Volume of current candle > 2× average volume (surge)
    - Direction aligns with gap/bias

    R:R: Always 2:1 minimum.
    """

    # Session windows (start, end) in respective timezones
    LONDON_WINDOW = (time(8, 0), time(8, 30))
    NY_WINDOW = (time(9, 30), time(10, 0))

    def __init__(self, volume_surge_mult=2.0):
        super().__init__("Session Momentum")
        self.volume_surge_mult = volume_surge_mult

    def _is_session_open(self, snapshot: MarketSnapshot) -> str | None:
        """Return 'london' or 'ny' if within an active session window, else None."""
        if not snapshot.candles:
            return None

        ts = snapshot.candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("UTC"))

        # Check London window (UTC)
        utc_time = ts.astimezone(ZoneInfo("UTC")).time()
        if self.LONDON_WINDOW[0] <= utc_time < self.LONDON_WINDOW[1]:
            return "london"

        # Check NY window (Eastern)
        et_time = ts.astimezone(ZoneInfo("America/New_York")).time()
        if self.NY_WINDOW[0] <= et_time < self.NY_WINDOW[1]:
            return "ny"

        return None

    def _calculate_vwap(self, snapshot: MarketSnapshot) -> float | None:
        """Calculate session VWAP from available candles."""
        if not snapshot.candles or len(snapshot.candles) < 5:
            return None

        total_vol = 0.0
        total_pv = 0.0
        for c in snapshot.candles[-30:]:  # Use last 30 candles (session context)
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

        session = self._is_session_open(snapshot)
        if session is None:
            return None

        if len(snapshot.candles) < 30:
            return None

        vwap = self._calculate_vwap(snapshot)
        if vwap is None:
            return None

        last_candle = snapshot.candles[-1]
        last_close = last_candle.close
        prev_close = snapshot.candles[-2].close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # Volume surge check
        recent_volumes = [c.volume for c in snapshot.candles[-20:-1] if c.volume > 0]
        avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1.0
        current_volume = last_candle.volume if last_candle.volume > 0 else 0

        if current_volume < avg_volume * self.volume_surge_mult:
            return None  # No volume surge

        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        session_label = session.upper()

        # --- BULLISH: Price breaks ABOVE VWAP with volume (only when trend allows) ---
        if htf_dir in ("long", "neutral") and prev_close <= vwap and last_close > vwap:
            # Proven ORB: stop near VWAP (the structural pivot) + small buffer
            stop_loss = vwap - (atr * 0.3)
            risk_dist = last_close - stop_loss
            take_profit = last_close + (risk_dist * 2.5)  # 2.5:1 R:R (proven ORB)

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="long",
                phase="trend",
                action="enter_long",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Session Momentum: {session_label} Open VWAP Break (Vol={current_volume:.0f}/{avg_volume:.0f})",
                invalidation_conditions="Price returns below VWAP",
                management_instructions="Target 2R. Move to BE after 1R.",
                notes=f"{session_label} session open momentum trade",
                urgency="high",
            )

        # --- BEARISH: Price breaks BELOW VWAP with volume (only when trend allows) ---
        if htf_dir in ("short", "neutral") and prev_close >= vwap and last_close < vwap:
            # Proven ORB: stop near VWAP (the structural pivot) + small buffer
            stop_loss = vwap + (atr * 0.3)
            risk_dist = stop_loss - last_close
            take_profit = last_close - (risk_dist * 2.5)  # 2.5:1 R:R (proven ORB)

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="short",
                phase="trend",
                action="enter_short",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Session Momentum: {session_label} Open VWAP Break (Vol={current_volume:.0f}/{avg_volume:.0f})",
                invalidation_conditions="Price returns above VWAP",
                management_instructions="Target 2R. Move to BE after 1R.",
                notes=f"{session_label} session open momentum trade",
                urgency="high",
            )

        return None

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        """
        Proven ORB exit management:
        1. Time-based exit: close if > 8 bars and losing (stalled momentum)
        2. At 1R: move to breakeven
        3. After 1R: trail 0.5× ATR behind price
        """
        if not snapshot.candles or not open_position:
            return None

        entry_price = float(open_position.get("entry_price", 0))
        stop_price = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0))
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction", "long")

        if entry_price <= 0 or stop_price <= 0:
            return None

        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0:
            return None

        atr = calculate_atr(snapshot.candles, period=14) or (current_price * 0.001)

        if direction == "long":
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        r_multiple = profit / initial_risk

        # TIME-BASED EXIT: If open > 8 bars and meaningfully losing, close
        # (proven ORB technique — stalled momentum rarely recovers)
        # Only exit if at -0.3R or worse — trades near breakeven deserve a chance.
        entry_time = open_position.get("entry_time")
        if entry_time and r_multiple < -0.3:
            # OANDA returns entry_time as ISO string — parse it
            if isinstance(entry_time, str):
                try:
                    entry_time = datetime.fromisoformat(
                        entry_time.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    entry_time = None
            if entry_time:
                # Count bars since entry using candle timestamps
                bars_since = 0
                for c in reversed(snapshot.candles):
                    c_ts = c.timestamp
                    if c_ts.tzinfo is None:
                        c_ts = c_ts.replace(tzinfo=ZoneInfo("UTC"))
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=ZoneInfo("UTC"))
                    if c_ts <= entry_time:
                        break
                    bars_since += 1
            if bars_since >= 8:
                return close_position_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Session Momentum: Time exit ({bars_since} bars, {r_multiple:.1f}R)",
                    emergency_exit=True,
                )

        # At 1R: move to breakeven (proven ORB technique)
        if r_multiple >= 1.0:
            already_at_be = (direction == "long" and stop_price >= entry_price) or \
                            (direction == "short" and stop_price <= entry_price)

            if not already_at_be:
                from tradebot_sci.strategy.decisions import hold_decision
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    reason=f"Session Momentum: Move to BE at {r_multiple:.1f}R",
                    stop_loss=entry_price,
                )

            # After BE: trail 0.5× ATR behind price (tight for momentum)
            trail_distance = atr * 0.5
            from tradebot_sci.strategy.decisions import hold_decision
            if direction == "long":
                new_stop = current_price - trail_distance
                if new_stop > stop_price:
                    return hold_decision(
                        snapshot.symbol, snapshot.timeframe,
                        reason=f"Session Momentum: Trail {new_stop:.5f} ({r_multiple:.1f}R)",
                        stop_loss=new_stop,
                    )
            else:
                new_stop = current_price + trail_distance
                if new_stop < stop_price:
                    return hold_decision(
                        snapshot.symbol, snapshot.timeframe,
                        reason=f"Session Momentum: Trail {new_stop:.5f} ({r_multiple:.1f}R)",
                        stop_loss=new_stop,
                    )

        return None
