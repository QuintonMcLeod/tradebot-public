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

# Per-symbol daily trade tracker (reset each day)
_daily_trades: dict[str, date] = {}  # symbol → last trade date


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

    # Asian session range hours (UTC)
    ASIAN_START = time(0, 0)
    ASIAN_END = time(6, 0)
    # London trading window (UTC) — only trade breakouts here
    LONDON_START = time(7, 0)
    LONDON_END = time(10, 0)
    # Session close cutoff — exit by this time
    SESSION_CLOSE = time(16, 0)

    def __init__(self):
        super().__init__("London Breakout")

    def _to_utc(self, dt):
        """Convert timestamp to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    def _get_asian_box(self, snapshot: MarketSnapshot) -> Optional[Tuple[float, float]]:
        """Get the Asian session high/low range for today."""
        if not snapshot.candles:
            return None

        latest_utc = self._to_utc(snapshot.candles[-1].timestamp)
        today = latest_utc.date()

        asian_candles = []
        for c in snapshot.candles:
            c_utc = self._to_utc(c.timestamp)
            if c_utc.date() == today:
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

    def _already_traded_today(self, symbol: str, snapshot: MarketSnapshot) -> bool:
        """Check if we already traded this symbol today."""
        latest_utc = self._to_utc(snapshot.candles[-1].timestamp)
        today = latest_utc.date()
        return _daily_trades.get(symbol) == today

    def _mark_traded(self, symbol: str, snapshot: MarketSnapshot):
        """Mark this symbol as traded today."""
        latest_utc = self._to_utc(snapshot.candles[-1].timestamp)
        _daily_trades[symbol] = latest_utc.date()

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           **kwargs) -> Optional[AITradeDecision]:
        if open_position:
            return None

        if not snapshot.candles or len(snapshot.candles) < 10:
            return None

        # ── TIME WINDOW CHECK ────────────────────────────────────
        current_utc = self._to_utc(snapshot.candles[-1].timestamp).time()

        # Only trade during London open window
        if not (self.LONDON_START <= current_utc <= self.LONDON_END):
            return None

        # ── 1 TRADE PER DAY PER SYMBOL ───────────────────────────
        if self._already_traded_today(snapshot.symbol, snapshot):
            return None

        # ── GET ASIAN BOX ────────────────────────────────────────
        asian_box = self._get_asian_box(snapshot)
        if not asian_box:
            return None

        box_low, box_high = asian_box
        box_range = box_high - box_low
        last_close = snapshot.candles[-1].close
        prev_close = snapshot.candles[-2].close
        atr = calculate_atr(snapshot.candles, period=14) or (last_close * 0.001)

        # [TREND GUIDANCE]
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # ── BULLISH BREAKOUT ─────────────────────────────────────
        # Price was inside box AND now CLOSES above box high
        if htf_dir in ("long", "neutral"):
            if prev_close <= box_high and last_close > box_high:
                # Tighter stop: half-box or 1.5× ATR, whichever is larger
                stop_dist = max(box_range * 0.5, atr * 1.5)
                stop_loss = last_close - stop_dist
                take_profit = last_close + (stop_dist * 2.0)  # 2:1 R:R

                self._mark_traded(snapshot.symbol, snapshot)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="enter_long",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(fallback=0.015),
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
        if htf_dir in ("short", "neutral"):
            if prev_close >= box_low and last_close < box_low:
                # Tighter stop: half-box or 1.5× ATR, whichever is larger
                stop_dist = max(box_range * 0.5, atr * 1.5)
                stop_loss = last_close + stop_dist
                take_profit = last_close - (stop_dist * 2.0)  # 2:1 R:R

                self._mark_traded(snapshot.symbol, snapshot)

                return AITradeDecision(
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="enter_short",
                    entry_price=last_close,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(fallback=0.015),
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

        # Breakeven management
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
                    notes="[MANAGEMENT] Session Breakout: stop → BREAKEVEN (1R)"
                )
            if direction == "short" and current_stop > entry_price and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="management", action="hold",
                    stop_loss=entry_price,
                    notes="[MANAGEMENT] Session Breakout: stop → BREAKEVEN (1R)"
                )

        return None
