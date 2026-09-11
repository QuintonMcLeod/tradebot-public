"""ForexScrapeFade — the time-of-day scrape, as validated on three years of data.

Full write-up: Documentation/Research/TIME_OF_DAY_EDGE_2026_09.md

The rule
--------
1. **Trade only inside one hour of the day** (default 20:00-21:00 UTC, which is
   16:00-17:00 in New York). Outside it, stand aside. Gross expectancy ramps
   monotonically through the session — roughly nothing in Asia, about +1.5 pips in
   the mid-afternoon and +2.5 in the last New York hour — and the swing from worst
   hour to best is larger than the entire spread. This is the effect that every
   pooled-all-hours test in this project missed.

2. **Fade a range break, price action only.** Long when price closes below the
   lowest low of the prior 20 bars; short when it closes above the highest high.
   No indicators: at the working window the price-action version earned three times
   what the SMA z-score version did, because an indicator lags the break it is
   meant to catch.

3. **Stop 20 pips, target 10 pips, time stop after 4 hours.** The asymmetry is
   deliberate and load-bearing: a 50% win rate against a 2:1 reward-to-risk in the
   wrong direction would lose money, so the target sits closer than the stop and the
   measured hit rate of about 52% carries it.

4. **No break-even stop.** Measured and rejected: moving the stop to break-even
   after +5 pips cut the win rate from 49% to 23% and turned gross expectancy from
   +0.378 to -0.808 per trade. In a whipsawing market the break-even level sits
   exactly where price returns on the way to the target, so it scratches out winners
   while the full-size losers still lose.

5. **Avoid the rollover hour.** The following hour (21:00 UTC) has the largest gross
   edge of the entire day, +4.34 pips, and OANDA's spread there is 4.30 pips. The
   markup takes back the whole opportunity, so the window ends before it.

Validated result: +0.32 pips per trade net of each pair's measured spread, t=4.17,
positive on 7 of 15 pairs over three years, and — the part that matters — reproduced
on 24 months of data that had never been examined (+0.41 pips, t=3.42) at the same
magnitude as the year the rule was chosen on.

Pair selection matters: break-even sits at roughly 2.5 pips of round-trip cost, so
this belongs on pairs whose spread is below that. On the tightest majors alone it is
worth approximately nothing, and on the widest crosses the spread eats it.
"""
from __future__ import annotations

import logging
from datetime import timezone
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

_PIP = {"JPY": 0.01}
_DEFAULT_PIP = 0.0001


class ForexScrapeFade(BaseStrategy):
    """Fades range breaks during a configured hour of the day."""

    # No session-name gating: the entry window is an explicit UTC hour range so it
    # does not depend on how sessions happen to be named in the config.
    SESSION_PROFILE = None

    def __init__(self, **kwargs):
        super().__init__("ForexScrapeFade")

        # Entry window in UTC hours, inclusive start, exclusive end.
        window = kwargs.get("scrape_hours", "20-21")
        try:
            start_s, end_s = str(window).split("-")
            self.entry_hour_start = int(start_s)
            self.entry_hour_end = int(end_s)
        except (ValueError, AttributeError):
            self.entry_hour_start, self.entry_hour_end = 20, 21

        self.range_lookback = int(kwargs.get("scrape_range_lookback", 20))
        self.stop_pips = float(kwargs.get("scrape_stop_pips", 20.0))
        self.target_pips = float(kwargs.get("scrape_target_pips", 10.0))
        self.max_hold_bars = int(kwargs.get("scrape_max_hold_bars", 48))
        # symbol -> timestamp of the last entry, for the spacing rule above
        self._last_entry_bar: dict = {}

        logger.info(
            f"[SCRAPE_INIT] window={self.entry_hour_start:02d}:00-{self.entry_hour_end:02d}:00 UTC, "
            f"lookback={self.range_lookback}, stop={self.stop_pips}p, "
            f"target={self.target_pips}p, max_hold={self.max_hold_bars} bars"
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _pip_size(symbol: str) -> float:
        s = (symbol or "").upper()
        return _PIP.get(s[-3:], _DEFAULT_PIP)

    @staticmethod
    def _pip_value_usd(symbol: str, price: float) -> float:
        """Approximate value of one pip for one unit, in USD."""
        s = (symbol or "").upper()
        pip = ForexScrapeFade._pip_size(s)
        if s.endswith("USD"):
            return pip
        if s.startswith("USD") and price > 0:
            return pip / price
        return pip  # cross: treated at par, sizing is normalised by risk anyway

    def _in_window(self, snapshot: MarketSnapshot) -> bool:
        if not snapshot.candles:
            return False
        ts = snapshot.candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour = ts.astimezone(timezone.utc).hour
        return self.entry_hour_start <= hour < self.entry_hour_end

    # ── scoring (for logging only; this strategy is not score-gated) ─────────
    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        if not self._in_window(snapshot):
            return 0.0, "-", "ScrapeFade: outside entry window"
        return 60.0, "C", "ScrapeFade: inside entry window"

    # ── entry ────────────────────────────────────────────────────────────────
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           current_capital: Optional[float] = None,
                           trade_history: Optional[list] = None):
        if open_position:
            return None
        if gates.get("is_synthetic_override") is True:
            return None

        candles = snapshot.candles
        if len(candles) < self.range_lookback + 2:
            return None
        if not self._in_window(snapshot):
            return None

        # Range over the prior N bars, including the one just closed — exactly the
        # rule that was validated on three years of data. An earlier version moved
        # the window back two bars to make breaks "fresh", which made entries about
        # forty times rarer than the rule being tested; the de-duplication that the
        # research applied is handled below by a spacing rule instead, so the
        # strategy and the validation measure the same thing.
        if len(candles) < self.range_lookback + 2:
            return None
        prior = candles[-self.range_lookback - 1:-1]
        range_high = max(c.high for c in prior)
        range_low = min(c.low for c in prior)

        last = candles[-1]
        entry = float(last.close)
        pip = self._pip_size(snapshot.symbol)

        # Do not re-enter while a break episode is still live: one entry per
        # holding period per symbol, which is how the research de-clustered its
        # events instead of counting every bar of a persisting break.
        last_entry = self._last_entry_bar.get(snapshot.symbol)
        if last_entry is not None:
            try:
                elapsed_bars = int((last.timestamp - last_entry).total_seconds() // 300)
                if elapsed_bars < self.max_hold_bars:
                    return None
            except Exception:
                pass

        if last.close < range_low:
            stop = entry - (self.stop_pips * pip)      # 20 pips against
            target = entry + (self.target_pips * pip)  # 10 pips for
            self._last_entry_bar[snapshot.symbol] = last.timestamp
            logger.info(
                f"[SCRAPE] {snapshot.symbol} LONG fade: close {entry:.5f} broke below "
                f"{self.range_lookback}-bar low {range_low:.5f} "
                f"(stop {self.stop_pips:.0f}p, target {self.target_pips:.0f}p)"
            )
            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="long",
                phase="correction",
                action="enter_long",
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=(
                    f"ScrapeFade Long: {self.range_lookback}-bar low violated "
                    f"({range_low:.5f}), fading back inside the range"
                ),
                invalidation_conditions=f"Close below {stop:.5f}",
                management_instructions=(
                    f"Target {self.target_pips:.0f}p, stop {self.stop_pips:.0f}p, "
                    f"time stop {self.max_hold_bars} bars. No break-even move."
                ),
                urgency="high",
                max_hold_bars=self.max_hold_bars,
                self_managed_risk=True,
                strategy_name=self.name,
                regime="range",
            )

        if last.close > range_high:
            stop = entry + (self.stop_pips * pip)
            target = entry - (self.target_pips * pip)
            self._last_entry_bar[snapshot.symbol] = last.timestamp
            logger.info(
                f"[SCRAPE] {snapshot.symbol} SHORT fade: close {entry:.5f} broke above "
                f"{self.range_lookback}-bar high {range_high:.5f} "
                f"(stop {self.stop_pips:.0f}p, target {self.target_pips:.0f}p)"
            )
            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="short",
                phase="correction",
                action="enter_short",
                entry_price=entry,
                stop_loss=stop,
                take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=(
                    f"ScrapeFade Short: {self.range_lookback}-bar high violated "
                    f"({range_high:.5f}), fading back inside the range"
                ),
                invalidation_conditions=f"Close above {stop:.5f}",
                management_instructions=(
                    f"Target {self.target_pips:.0f}p, stop {self.stop_pips:.0f}p, "
                    f"time stop {self.max_hold_bars} bars. No break-even move."
                ),
                urgency="high",
                max_hold_bars=self.max_hold_bars,
                self_managed_risk=True,
                strategy_name=self.name,
                regime="range",
            )

        return None

    # ── exit ─────────────────────────────────────────────────────────────────
    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, current_capital: Optional[float] = None,
                          trade_history: Optional[list] = None):
        """Only the time stop. Stop and target are held by the broker."""
        if not open_position or not snapshot.candles:
            return None

        bars_held = open_position.get("bars_held") or 0
        if not bars_held:
            entry_ts = open_position.get("entry_time")
            if entry_ts:
                try:
                    from datetime import datetime
                    entry_dt = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
                    if entry_dt.tzinfo is None:
                        entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                    now_dt = snapshot.candles[-1].timestamp
                    if now_dt.tzinfo is None:
                        now_dt = now_dt.replace(tzinfo=timezone.utc)
                    tf = (snapshot.timeframe or "5m").lower()
                    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30,
                               "1h": 60, "4h": 240}.get(tf, 5)
                    bars_held = int((now_dt - entry_dt).total_seconds() // (minutes * 60))
                except Exception:
                    bars_held = 0

        if bars_held >= self.max_hold_bars:
            logger.info(
                f"[SCRAPE] {snapshot.symbol} time stop at {bars_held} bars "
                f"(limit {self.max_hold_bars})"
            )
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Scrape time stop ({bars_held} bars)",
            )
        return None
