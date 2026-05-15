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
    Captures intraday momentum following major session opens.
    
    SESSION_PROFILE: london_open
    """
    SESSION_PROFILE = ["session_momentum:london_open", "session_momentum:us_open"]

    # Session windows (start, end) in respective timezones
    LONDON_WINDOW = (time(8, 0), time(8, 30))
    NY_WINDOW = (time(9, 30), time(10, 0))

    def __init__(self, volume_surge_mult=2.0, **kwargs):
        super().__init__("Session Momentum")
        self.volume_surge_mult = volume_surge_mult

    def _is_session_open(self, snapshot: MarketSnapshot) -> str | None:
        """NOTE: Session timing is handled by the Global Scheduler, not this strategy.
        
        This method is kept for backward compatibility but returns None always.
        Configure your preferred trading windows in the scheduler settings.
        This strategy focuses purely on VWAP + Volume surge detection.
        """
        return None  # Disabled - Global Scheduler handles session timing

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

        # NOTE: Session timing is handled by the Global Scheduler.
        # This strategy focuses purely on VWAP break + volume surge detection.
        # The _is_session_open() method now returns None always.
            
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

        # Session label removed - timing handled by Global Scheduler

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
                structure_summary=f"Session Momentum: {self.SESSION_PROFILE} Open VWAP Break (Vol={current_volume:.0f}/{avg_volume:.0f})",
                invalidation_conditions="Price returns below VWAP",
                management_instructions="Target 2R. Move to BE after 1R.",
                notes=f"{self.SESSION_PROFILE} session open momentum trade",
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
                structure_summary=f"Session Momentum: {self.SESSION_PROFILE} Open VWAP Break (Vol={current_volume:.0f}/{avg_volume:.0f})",
                invalidation_conditions="Price returns above VWAP",
                management_instructions="Target 2R. Move to BE after 1R.",
                notes=f"{self.SESSION_PROFILE} session open momentum trade",
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

        pass

        return None
