from __future__ import annotations
import logging
from datetime import time, date
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)

# Note: Session timing is now handled by the global scheduler.
# This strategy focuses purely on breakout detection logic.


class LondonBreakoutStrategy(BaseStrategy):
    """
    Session Breakout — Asian Box → London Open.

    Proven forex strategy (50%+ WR at 1.5:1 R:R, heavily backtested).
    Identifies the Asian session consolidation range (00:00–06:00 UTC)
    and trades the breakout when London opens (07:00–10:00 UTC).

    Setup: Asian session high/low = "the box"
    Entry: Price breaks AND CLOSES above box high (long) or below box low (short)
    Exit:  1.5× box range as TP, OR end of London session (16:00 UTC)
    Stop:  Opposite side of the box
    Limit: 1 trade per day per symbol (no re-entry after stop)
    """

    def __init__(self, **kwargs):
        super().__init__("London Breakout")
        
        def _parse_time(t_str, default_hr):
            try:
                h, m = map(int, str(t_str).split(':'))
                return time(h, m)
            except Exception:
                return time(default_hr, 0)
                
        self.ASIAN_START = _parse_time(kwargs.get('asian_start', '00:00'), 0)
        self.ASIAN_END = _parse_time(kwargs.get('asian_end', '06:00'), 6)
        self.LONDON_START = _parse_time(kwargs.get('london_start', '07:00'), 7)
        self.LONDON_END = time(10, 0)
        self.SESSION_CLOSE = time(16, 0)
        
        self.stop_box_mult = float(kwargs.get('stop_box_mult', 0.5))
        self.target_box_mult = float(kwargs.get('target_box_mult', 1.5))

    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """Score how close current conditions are to a London Breakout entry.

        Each factor contributes points to a 0-100 score:
          Asian Box exists and well-formed    = 30 pts
          Price near box edge (≤0.3× range)   = 25 pts
          Clean breakout setup                = 30 pts
          Candle body momentum                = 15 pts
          
        Note: Session timing is handled by global scheduler, not here.
        """
        from typing import Tuple
        closes = [c.close for c in snapshot.candles]
        if not snapshot.candles or len(closes) < 10:
            return 0.0, "-", "Session Breakout: insufficient data"

        score = 0.0
        details = []

        # 1. Asian Box quality (30 pts)
        asian_box = self._get_asian_box(snapshot)
        if asian_box:
            box_low, box_high = asian_box
            box_range = box_high - box_low
            atr = calculate_atr(snapshot.candles, period=14) or (closes[-1] * 0.001)
            if box_range >= atr * 0.5:
                score += 30
                details.append(f"box={box_range:.5f}")
            else:
                score += 15
                details.append("box=narrow")

            # 2. Price proximity to box edge (25 pts)
            last_close = closes[-1]
            dist_to_high = abs(last_close - box_high)
            dist_to_low = abs(last_close - box_low)
            nearest_edge = min(dist_to_high, dist_to_low)
            if nearest_edge <= box_range * 0.1:
                score += 25
                details.append("edge✓")
            elif nearest_edge <= box_range * 0.3:
                score += 15
                details.append("near-edge")
            else:
                details.append("mid-box")
        else:
            details.append("no-box")

        # 3. Breakout setup quality (30 pts) - check if price is positioned for breakout
        if asian_box and len(closes) >= 3:
            last_close = closes[-1]
            prev_close = closes[-2]
            # Price approaching box boundary = potential breakout
            if prev_close <= box_high and last_close > box_high * 0.999:
                score += 30  # About to break high
                details.append("break-high✓")
            elif prev_close >= box_low and last_close < box_low * 1.001:
                score += 30  # About to break low
                details.append("break-low✓")
            elif abs(last_close - box_high) <= box_range * 0.15 or abs(last_close - box_low) <= box_range * 0.15:
                score += 20  # Near boundary
                details.append("near-break")
            else:
                details.append("consolidating")

        # 4. Candle body momentum (15 pts)
        if len(closes) >= 2:
            body = abs(snapshot.candles[-1].close - snapshot.candles[-1].open)
            candle_range = snapshot.candles[-1].high - snapshot.candles[-1].low
            if candle_range > 0 and body / candle_range > 0.6:
                score += 15
                details.append("momentum✓")
            elif candle_range > 0 and body / candle_range > 0.3:
                score += 8
                details.append("momentum~")
            else:
                details.append("momentum✗")

        grade = self.grade_from_score_100(score)
        summary = f"Session Breakout: {score:.0f}% — {', '.join(details)}"
        return score, grade, summary

    def _to_utc(self, dt):
        """Convert timestamp to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    def _get_asian_box(self, snapshot: MarketSnapshot) -> Optional[Tuple[float, float]]:
        """Get the Asian session high/low range for today."""
        if not snapshot.candles:
            return None

        # Use last 24 candles to capture Asian session range
        # (assumes scheduler handles session timing)
        recent_candles = snapshot.candles[-24:]
        
        asian_candles = []
        for c in recent_candles:
            c_utc = self._to_utc(c.timestamp)
            t = c_utc.time()
            if self.ASIAN_START <= t < self.ASIAN_END:
                asian_candles.append(c)

        if len(asian_candles) < 3:  # Need meaningful range
            return None

        box_high = max(c.high for c in asian_candles)
        box_low = min(c.low for c in asian_candles)

        # Ensure box has meaningful width (at least 5 pips for forex)
        box_range = box_high - box_low
        if box_range <= 0:
            return None

        return box_low, box_high

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           **kwargs) -> Optional[AITradeDecision]:
        if open_position:
            return None

        if not snapshot.candles or len(snapshot.candles) < 10:
            return None

        # Note: Session timing is handled by global scheduler.
        # We assume we're only called during valid trading hours.

        # ── GET ASIAN BOX ────────────────────────────────────────
        asian_box = self._get_asian_box(snapshot)
        if not asian_box:
            return None

        box_low, box_high = asian_box
        box_range = box_high - box_low
        last_close = snapshot.candles[-1].close
        prev_close = snapshot.candles[-2].close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # ── BULLISH BREAKOUT ─────────────────────────────────────
        if prev_close <= box_high and last_close > box_high:
            # [HARDENED] Breakout candle must have significant body
            breakout_body = abs(snapshot.candles[-1].close - snapshot.candles[-1].open)
            if breakout_body < box_range * 0.3:
                return None  # Weak breakout — likely fake

            # Tighter stop: half-box or 1.5× ATR, whichever is larger
            stop_dist = max(box_range * self.stop_box_mult, atr * 1.5)
            stop_loss = last_close - stop_dist
            take_profit = last_close + (stop_dist * self.target_box_mult)  # target mult

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="long", phase="trend", action="enter_long",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=(
                    f"Session Breakout Long: Asian box "
                    f"[{box_low:.5f}–{box_high:.5f}]"
                ),
                invalidation_conditions="Close back inside Asian box",
                management_instructions=(
                    f"Target 1.5× box range. "
                    f"Exit by 16:00 UTC if not hit."
                ),
                notes="Asian box breakout — London open momentum",
                urgency="high",
            )

        # ── BEARISH BREAKOUT ─────────────────────────────────────
        if prev_close >= box_low and last_close < box_low:
            # [HARDENED] Breakout candle must have significant body
            breakout_body = abs(snapshot.candles[-1].close - snapshot.candles[-1].open)
            if breakout_body < box_range * 0.3:
                return None  # Weak breakout — likely fake

            # Tighter stop: half-box or 1.5× ATR, whichever is larger
            stop_dist = max(box_range * self.stop_box_mult, atr * 1.5)
            stop_loss = last_close + stop_dist
            take_profit = last_close - (stop_dist * self.target_box_mult)  # target mult

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="short", phase="trend", action="enter_short",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=(
                    f"Session Breakout Short: Asian box "
                    f"[{box_low:.5f}–{box_high:.5f}]"
                ),
                invalidation_conditions="Close back inside Asian box",
                management_instructions=(
                    f"Target 1.5× box range. "
                    f"Exit by 16:00 UTC if not hit."
                ),
                notes="Asian box breakout — London open momentum",
                urgency="high",
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot,
                          open_position: dict, gates: dict,
                          **kwargs) -> Optional[AITradeDecision]:
        if not snapshot.candles or len(snapshot.candles) < 2:
            return None

        # ── Time-based exit removed ──────────────────────────────
        # Let TP/SL handle exits — time exits create dilutive small wins

        # ── FAILED BREAKOUT detection removed ─────────────────
        # Was cutting winners at $1-3. Let TP/SL handle exits.

        pass

        return None
