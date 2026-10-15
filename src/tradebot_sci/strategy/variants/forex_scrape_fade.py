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
   meant to catch. IT IS A CLOSE AND NOT A POKE, and the live engine hands over the
   bar still being formed, so the strategy drops that bar itself before testing the
   rule (see _closed_candles). Measured 2026-10-12: the running bot reported EURNZD
   at a 1.2-pip break depth mid-bar, and that bar went on to close 2.60 pips beyond
   its prior range, which is an entry by the rule as written and one the live path
   could not see.

3. **Stop 20 pips, target 15 pips, time stop after 24 hours.** The hold is the
   load-bearing parameter, and it was originally set too short. Measured on fifteen
   pairs over three years, net of each trade's own quoted spread: -3.19 pips per
   trade at a four-hour hold, against +1.15 at 288 bars with the 15-pip target. At
   288 bars the whole target/stop grid is profitable rather than a single cell. The
   fade needs roughly a day for the overextension to revert.

3b. **The 24-hour time stop is a decision, not a wall** (Steven's order, 2026-10-10).
   The live desk held its winners eighteen to nineteen hours and one trade
   forty-three, so the bot was given the same call on each trade: at the written
   horizon, a position still open and standing in profit is carried for up to one
   further horizon, re-decided every bar, and everything else closes as before. The
   measurement behind it, scratch/overnight_carry.py, is de-clustered at the deployed
   288 bars so these are the trades the bot actually takes: the trades still open at
   the horizon are 12 of 1,983 on the fifteen-pair set (0.61 percent) and 11 of 1,028
   on the twenty-six-pair set (1.07 percent). Carrying those trades one more day is
   worth +3.68 pips a trade on the first set (paired t +1.11) and +2.47 on the second
   (t +0.72); carrying only the ones already in profit is +2.97 (t +2.07) and +1.61
   (t +1.92). Eleven trades is not a sample, so the honest description is that this
   is not measured to lose and the trades it carries are the ones the desk would have
   held; the gain is a candidate, not a verdict. Financing is far below the
   break-even: carrying stops paying above +5.78 and +6.48 pips a night, and a night
   of financing on a 6-percent risk unit at retail rates is well under one pip. The
   paper broker charges no financing at all, so the paper record is optimistic by
   that same fraction of a pip on the roughly one trade in a hundred this affects.

4. **No break-even stop.** Measured and rejected: moving the stop to break-even
   after +5 pips cut the win rate from 49% to 23% and turned gross expectancy from
   +0.378 to -0.808 per trade. In a whipsawing market the break-even level sits
   exactly where price returns on the way to the target, so it scratches out winners
   while the full-size losers still lose.

5. **Avoid the rollover hour.** The following hour (21:00 UTC) has the largest gross
   edge of the entire day, +4.34 pips, and OANDA's spread there is 4.30 pips. The
   markup takes back the whole opportunity, so the window ends before it.

Validated result: +1.15 pips per trade over 2,052 trades on fifteen pairs and
three years (t=3.17, 67% win rate), and +1.31 on a 26-pair set covering the most
recent twelve months (t=2.64). Both datasets show the entire target/stop grid
profitable at the 288-bar hold, which is a stronger signal than any single
bracket. The effect lives in the recent eighteen months and is flat to negative
before that, so treat it as a forward paper test, not a settled edge.

CORRECTION 2026-09-16: those two net figures are too optimistic. They charge a
single flat cost per trade - 2.30 pips on the fifteen-pair set and 3.10 on the
twenty-six-pair set, which are the medians of the respective event subsets -
while claiming to be net of each trade's own quoted spread. The spread
distribution across these pairs is strongly right-skewed, so the mean cost per
trade is well above the median, and the mean is what a per-trade charge has to
use. Re-costed on each trade's own quoted spread with tools/edge_cost_check.py,
which reproduces the gross figures exactly:

  fifteen pairs, target 15 / stop 20:    gross +3.53, net +0.51 (t=+1.38)
  twenty-six pairs, target 15 / stop 25: gross +4.62, net -0.22 (t=-0.38)
  twenty-six pairs, target 15 / stop 20: gross +4.46, net -0.38 (t=-0.73)

The subset mean spread is 3.02 pips for the fifteen-pair set and 4.84 for the
twenty-six-pair set. Trimming the top percentile leaves 2.82 and 4.55, so this
is a shifted distribution rather than a few outliers; in the twenty-six-pair
set 28.2% of trades were quoted above 5 pips and they account for 60.6% of the
total cost. The twenty-six-pair set was the independent cross-sectional
confirmation, and it is negative at both brackets. Nothing here clears the
pre-registered bar of |t|>3. The gross edge is real and reproduces; the net was
overstated by the cost assumption.

Method, and the corrections that produced these numbers:
Documentation/Research/SCRAPE_ENTRY_2026_09_13.md

Pair selection matters: break-even sits at roughly 2.5 pips of round-trip cost, so
this belongs on pairs whose spread is below that. On the tightest majors alone it is
worth approximately nothing, and on the widest crosses the spread eats it.

The cost ceiling, re-measured 2026-10-10
----------------------------------------
`scrape_max_spread_pips` (1.9) has always been enforced against `measured_spreads.json`,
which holds ONE number per pair and 15 pairs in total. That is an average, and the cost
this trade pays is the quote at its own entry bar. Measured over the same pools: of the
entries the table admits, 25.0 percent on the fifteen-pair set and 26.8 on the
twenty-six-pair set are quoted above the ceiling at their own entry bar, and those
entries carry 40.8 and 44.0 percent of the admitted cost. Worse, a pair absent from the
table returns None, the guard only refuses when the value is not None, and so every
entry on an uncovered pair passed unchecked: 11 of the 26 pairs are uncovered, they are
40.5 percent of the entries, and their mean quoted cost is 6.74 pips a round trip
against a 15-pip target.

The engine already fetches the live bid/ask each cycle and hands it over as
`gates["current_spread"]`; until now nothing read it. It is read on every candidate that
reaches the guard and reported at INFO as the entry toll in pips and as the share of the
risk unit, before any refusal, and `scrape_live_spread_gate` (default True) ENFORCES the
same ceiling on that quote. Enforcing it measures +2.32 pips per trade at t=+3.80 on the
fifteen-pair set and +3.90 at t=+3.49 on the twenty-six-pair set, holding in both
halves, against +0.62 and -0.20 as deployed, at the cost of 65 percent of the trades.

The ceiling refuses the trade; it does not only report it. Asked on 2026-10-10 which of
the two this should be, this lane answered the question rather than handing it back
(decision 28). The short form: the ceiling is the strategy's own declaration and it was
being checked against a per-pair average rather than the price this trade pays; the
filter reads only the quote at the moment of the decision and never the outcome, so it
cannot select on the result; and the alternative is taking the entries already measured
as the expensive ones while writing down that they were expensive. An entry whose cost is
neither quoted nor in the table is refused too, because a ceiling cannot be claimed over
a number that does not exist. The caveat travels with it: the filtered pool has not had
the walk-forward split the project's acceptance bar asks for, and the two pools disagree
on the level, so the forward paper record is the test of this and one flag reverses it.
Facts 178, 179 and 187; decision 28.

Not part of the Meta-SCI ensemble
--------------------------------
Deliberately absent from meta_sci.py. The ensemble picks among regime-matched
strategies on every bar, whereas this rule is defined by one fixed hour of the day;
handing it to a per-bar regime selector would fire it outside the only window it was
measured in. It is selected directly by profile config instead, and registering it
would need the hour gate to travel with it.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
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
        self.target_pips = float(kwargs.get("scrape_target_pips", 15.0))

        # The 48-bar hold was the losing setting. Measured on fifteen pairs over three
        # years, net of each trade's quoted spread: -3.19 pips per trade at 48 bars
        # against +1.15 at 288 bars with a 15-pip target, and the whole target/stop
        # grid profitable at 288. The entry is unchanged; the fade needs a day for the
        # overextension to revert instead of four hours.
        self.max_hold_bars = int(kwargs.get("scrape_max_hold_bars", 288))

        # Only fade a *deep* break. This is the single filter that makes the fade
        # work. Fading every fresh break at the 20:00 UTC hour measured -5.21 pips
        # gross per trade over three years on fifteen pairs; restricting to breaks of
        # 1 pip or more gives -2.62, 2 pips or more -0.75, and 3 pips or more +0.48.
        # The relationship is monotonic, so the threshold is the strategy: a marginal
        # break is noise and a deep one is an overextension that reverts.
        self.min_break_pips = float(kwargs.get("scrape_min_break_pips", 2.0))

        # Skip pairs whose measured round trip is too wide for the edge to survive:
        # the toll is charged in pips, so a 4-pip spread on a 10-pip target is not a
        # trade worth taking no matter how good the signal looks.
        self.max_spread_pips = float(kwargs.get("scrape_max_spread_pips", 1.9))

        # Whether the ceiling above is enforced on the LIVE bid/ask as well as on the
        # per-pair table. Default True since 2026-10-10: the readout-or-gate question was
        # answered by this lane instead of being handed back, and the answer is the
        # refusal (decision 28). THE MEASURED CASE. The live quote is the number the
        # trade pays, and the table is an average it may not resemble: of the entries the
        # table admits, 25 to 27 percent are quoted above the ceiling at their own entry
        # bar, and those carry 41 to 44 percent of the admitted cost. Enforcing the
        # ceiling on the entry bar's own quote measures +2.32 pips per trade at t=+3.80
        # on 15 pairs over 3 years and +3.90 pips at t=+3.49 on 26 pairs over 12 months,
        # holding in both halves of both windows, against +0.62 and -0.20 as deployed. It
        # also costs 65 percent of the trades. NOT YET PROVEN, and written here so it is
        # not lost: the filtered pool has not had the walk-forward train/validate split
        # the acceptance bar asks for, and the two pools disagree on the level, so the
        # forward paper record is the test and this flag is the way to reverse it.
        self.live_spread_gate = bool(kwargs.get("scrape_live_spread_gate", True))

        # ── THE OVERNIGHT CARRY DECISION ─────────────────────────────────────────
        # Steven's order, 2026-10-10: the bot decides per trade whether to hold past
        # its written 24-hour horizon, the way the live desk did, instead of being
        # walled off at it. The decision is taken at the horizon and not guessed at
        # entry, because the fact that decides it is how the trade stands by then.
        # Carried only while it is in profit, only once, and re-decided every bar, so
        # a carried trade that stops working is closed on the next bar rather than
        # being given a second 24 hours to fail. Default on, per the order; one flag
        # reverses it. The measurement and its (thin) sample are in the module
        # docstring at 3b and in scratch/overnight_carry.py.
        self.carry_enabled = bool(kwargs.get("scrape_carry_enabled", True))
        self.carry_bars = int(kwargs.get("scrape_carry_bars", 288))
        self.carry_min_profit_r = float(kwargs.get("scrape_carry_min_profit_r", 0.05))
        # symbol -> timestamp of the last entry, for the spacing rule above
        self._last_entry_bar: dict = {}
        # Set by score_signal on every evaluation: whether the bar the strategy
        # was looking at fell inside its own entry hour.  Structured rather than
        # parsed back out of the summary string, because the replay throughput
        # count depends on it and a count built by string matching would break
        # silently.
        self.last_in_entry_window: Optional[bool] = None

        logger.info(
            f"[SCRAPE_INIT] window={self.entry_hour_start:02d}:00-{self.entry_hour_end:02d}:00 UTC, "
            f"lookback={self.range_lookback}, stop={self.stop_pips}p, "
            f"target={self.target_pips}p, max_hold={self.max_hold_bars} bars, "
            # Printed so the journal says which mode the bot is in. A ceiling that
            # refuses and a ceiling that only reports leave the same trace otherwise.
            f"spread_ceiling={self.max_spread_pips}p "
            f"({'enforced' if self.live_spread_gate else 'reported only'}), "
            # Printed for the same reason: a carry rule that is on and one that is off
            # would otherwise leave the same journal behind.
            f"overnight_carry={'on' if self.carry_enabled else 'off'} "
            f"(to {self.max_hold_bars + self.carry_bars} bars, "
            f"from {self.carry_min_profit_r:+.2f}R)"
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

    def _entry_toll(self, symbol: str, gates: dict, pip: float, reference_price):
        """What this entry costs to get into, in pips, and where the number came from.

        Preference order matters. gates["current_spread"] is the live bid/ask the engine
        has already fetched for this cycle, so it is the toll this entry would actually
        pay. The measured table is one number per pair and is only a fallback for paths
        with no live quote (replay and backtest). When neither is available the cost is
        unknown, and the caller says so rather than treating unknown as cheap.

        Returns (pips, source) with pips None when unmeasured.
        """
        live = gates.get("current_spread") if isinstance(gates, dict) else None
        try:
            if live:
                live_pips = float(live) / pip
                if live_pips > 0:
                    return live_pips, "live bid/ask"
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        try:
            from tradebot_sci.broker.paper_broker import _measured_spread_bps
            bps = _measured_spread_bps(symbol)
            if bps is not None and reference_price:
                return (float(bps) / 10000.0) * float(reference_price) / pip, "measured table"
        except Exception:
            pass
        return None, None

    def _closed_candles(self, candles: list, timeframe: str) -> list:
        """Drop the still-forming bar, so the signal is a bar CLOSE and not a poke.

        The rule this strategy validates is a close beyond the prior range, and the
        backtest and the replay both feed it closed bars only. The live engine does not:
        runtime/cycle.py builds the snapshot from the raw provider list on purpose, so
        that the engine's own trend cache sees tick-by-tick movement, which means
        `candles[-1]` at decision time is the bar still being formed and `last.close`
        is the price right now rather than a close.

        What that cost, measured rather than reasoned about: at 2026-10-12 20:48:55Z the
        running bot reported EURNZD "break depth 1.2p below the 2.0p minimum" — the
        20:45Z bar, part formed. That bar closed at 20:50Z 2.60 pips beyond its prior
        twenty-bar range, which is an entry by the rule as written, and the next poll at
        20:55:07Z said "no fresh break of the prior range" because by then the 20:50Z bar
        was newest and the qualifying close had moved into the range window. The live
        path could therefore only ever see breaks that happened to be at least at the
        minimum depth at the instant of a poll; over the two entry windows since the
        runner restarted, the deepest break it ever saw was 1.8 pips while the closed
        bars of those same windows contain a 2.6-pip one it never evaluated.

        Replay and backtest are unaffected: their bars are historical, so the last one
        has long since closed and nothing is dropped.
        """
        if not candles:
            return candles
        bar_secs = self._bar_seconds(timeframe)
        last = candles[-1]
        ts = last.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        closes_at = ts + timedelta(seconds=bar_secs)
        now = datetime.now(timezone.utc)
        if (now - closes_at).total_seconds() > 86400:
            return candles          # replay: every bar here is already closed history
        if closes_at > now:
            return candles[:-1]     # the bar that has not closed yet is not a signal
        return candles

    @staticmethod
    def _bar_seconds(timeframe: str) -> int:
        m = re.match(r"^\s*(\d+)\s*(m|min|mins|h|hour|hours|d|day|days)\s*$",
                     str(timeframe or "5m").lower())
        if not m:
            return 300
        value, unit = int(m.group(1)), m.group(2)
        if unit.startswith("m"):
            return value * 60
        if unit.startswith("h"):
            return value * 3600
        return value * 86400

    def _in_window(self, snapshot: MarketSnapshot) -> bool:
        candles = self._closed_candles(snapshot.candles, snapshot.timeframe)
        if not candles:
            return False
        ts = candles[-1].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour = ts.astimezone(timezone.utc).hour
        return self.entry_hour_start <= hour < self.entry_hour_end

    # ── scoring (for logging only; this strategy is not score-gated) ─────────
    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        inside = self._in_window(snapshot)
        self.last_in_entry_window = inside
        if not inside:
            return 0.0, "-", "ScrapeFade: outside entry window"
        return 60.0, "C", "ScrapeFade: inside entry window"

    # ── skip reporting ───────────────────────────────────────────────────────
    def _decline(self, snapshot: MarketSnapshot, reason: str):
        """Log why a candidate was refused, and return None for the caller.

        The silent declines were the reason a HOLD line could not explain itself:
        measured 2026-10-10, 5 of the 7 ways this strategy declines left no trace
        at all, and the other 2 logged at DEBUG, which the journal does not keep.

        Logged at INFO only while the strategy is inside its own entry hour, which
        is when the information is worth having. Outside the hour every symbol
        declines on every cycle, so logging there would add about 300 lines a day
        saying nothing but "wrong hour". The journal already holds a separate
        flood incident, so the throttle is deliberate rather than an oversight.
        """
        try:
            if self._in_window(snapshot):
                logger.info(f"[SCRAPE] {snapshot.symbol}: declined, {reason}")
        except Exception:
            pass
        return None

    # ── entry ────────────────────────────────────────────────────────────────
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           current_capital: Optional[float] = None,
                           trade_history: Optional[list] = None):
        if open_position:
            return None
        if gates.get("is_synthetic_override") is True:
            return self._decline(snapshot, "synthetic override is set")

        raw = snapshot.candles
        if len(raw) < self.range_lookback + 2:
            return self._decline(
                snapshot, f"only {len(raw)} candles, needs {self.range_lookback + 2}")
        if not self._in_window(snapshot):
            return None

        # A bar CLOSE is the signal, so the bar still being formed is not one: it is
        # the price right now, and a poke that happens to be deep at the instant of a
        # poll is not a close beyond the range. See _closed_candles for what the
        # difference cost the live path.
        candles = self._closed_candles(raw, snapshot.timeframe)

        # Range over the prior N bars, including the one just closed — exactly the
        # rule that was validated on three years of data. An earlier version moved
        # the window back two bars to make breaks "fresh", which made entries about
        # forty times rarer than the rule being tested; the de-duplication that the
        # research applied is handled below by a spacing rule instead, so the
        # strategy and the validation measure the same thing.
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
                    return self._decline(
                        snapshot,
                        f"still inside the spacing rule, {elapsed_bars} of "
                        f"{self.max_hold_bars} bars since the last entry")
            except Exception:
                pass

        # Break depth: how far past the violated level price has closed, in pips.
        long_break = last.close < range_low
        short_break = last.close > range_high
        if not (long_break or short_break):
            return self._decline(snapshot, "no fresh break of the prior range")
        depth_pips = (range_low - last.close) / pip if long_break else (last.close - range_high) / pip
        if depth_pips < self.min_break_pips:
            return self._decline(
                snapshot,
                f"break depth {depth_pips:.1f}p below the {self.min_break_pips:.1f}p minimum")

        # ── Entry toll: what this entry actually costs, in pips and in R ──────
        # The engine already fetches the live bid/ask every cycle and hands it over as
        # gates["current_spread"], and until now nothing read it. The ceiling below was
        # tested against a per-pair AVERAGE from a table instead, which is a different
        # number from the one this trade will pay: measured 2026-10-10, 25 to 27 percent
        # of the entries the table admits are quoted above the ceiling at their own entry
        # bar, and those entries carry 41 to 44 percent of the admitted cost. Pairs the
        # table does not cover at all passed unchecked, and on the 26-pair universe that
        # was 40.5 percent of trades at a mean 6.74 pips a round trip. Facts 178 and 179.
        toll_pips, toll_source = self._entry_toll(snapshot.symbol, gates, pip, last.close)
        toll_r = (toll_pips / self.stop_pips) if toll_pips else None

        # The readout Steven asked for in commitment 15: the toll at the moment of the
        # decision, in pips and as the share of the risk unit it eats. Logged before any
        # refusal below, so the journal carries the number for every candidate rather
        # than only for the ones that got through.
        if toll_pips is not None:
            _over = " ABOVE CEILING" if toll_pips > self.max_spread_pips else ""
            logger.info(
                f"[SCRAPE] {snapshot.symbol}: entry toll {toll_pips:.2f}p "
                f"({100.0 * (toll_r or 0.0):.1f}% of the {self.stop_pips:.0f}p risk unit) "
                f"from {toll_source}, ceiling {self.max_spread_pips:.1f}p{_over}"
            )

        # Spread guard: the per-pair measured round trip, on the same ceiling.
        _table_known = False
        try:
            from tradebot_sci.broker.paper_broker import _measured_spread_bps
            _bps = _measured_spread_bps(snapshot.symbol)
            if _bps is not None and last.close:
                _table_known = True
                _spread_pips = (_bps / 10000.0) * last.close / pip
                if _spread_pips > self.max_spread_pips:
                    return self._decline(
                        snapshot,
                        f"spread {_spread_pips:.2f}p above the {self.max_spread_pips:.1f}p ceiling")
        except Exception:
            pass

        # Neither the table nor a live quote can price this entry, so the ceiling cannot
        # be tested against anything. Refused rather than admitted: the uncovered pairs
        # are 40.5 percent of the twenty-six-pair pool at a mean 6.74 pips a round trip,
        # and "not measured" was reading as "cheap". Refusing costs the trade and says
        # why; admitting it spends up to 45 percent of a 15-pip target on the toll blind.
        if toll_pips is None and not _table_known:
            return self._decline(
                snapshot,
                f"entry cost unknown: {snapshot.symbol} is absent from the measured "
                f"spread table and no live quote is available, so the "
                f"{self.max_spread_pips:.1f}p ceiling cannot be checked")

        # The gate: the same ceiling, on the quote this trade actually pays rather than
        # on the pair's average. On by default since 2026-10-10 (decision 28).
        if self.live_spread_gate and toll_pips is not None and toll_pips > self.max_spread_pips:
            return self._decline(
                snapshot,
                f"live spread {toll_pips:.2f}p above the {self.max_spread_pips:.1f}p "
                f"ceiling (from {toll_source})")

        if long_break:
            stop = entry - (self.stop_pips * pip)      # 20 pips against
            target = entry + (self.target_pips * pip)  # 15 pips for
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

        if short_break:
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

    # ── the overnight carry decision ─────────────────────────────────────────
    def _position_r(self, open_position: dict, snapshot: MarketSnapshot) -> Optional[float]:
        """How the open trade stands, in risk units, at the current close.

        Preferred source is the broker's own floating P&L against the risk the trade
        was sized to, because that is already in one currency and needs no pip maths.
        The fallback reads the price against the stop the position carries, and the
        configured stop only if the position does not carry one. Returns None rather
        than a guess when neither is available: a carry decision made on a number the
        code invented is worse than closing the trade.
        """
        pnl = open_position.get("unrealized_pnl")
        risk = open_position.get("risk_usd") or open_position.get("initial_risk")
        if pnl is not None and risk:
            try:
                if float(risk) > 0:
                    return float(pnl) / float(risk)
            except (TypeError, ValueError):
                pass

        entry = open_position.get("entry_price") or open_position.get("avg_price")
        if entry is None or not snapshot.candles:
            return None
        stop = open_position.get("stop_price") or open_position.get("stop_loss")
        if stop:
            risk_px = abs(float(entry) - float(stop))
        else:
            risk_px = self.stop_pips * self._pip_size(snapshot.symbol)
        if risk_px <= 0:
            return None
        move = float(snapshot.candles[-1].close) - float(entry)
        direction = str(open_position.get("direction") or open_position.get("side") or "").lower()
        if direction in ("short", "sell", "enter_short"):
            move = -move
        return move / risk_px

    def _carry_decision(self, open_position: dict, snapshot: MarketSnapshot,
                        bars_held: int) -> Optional[float]:
        """Whether to carry this trade past the written horizon, and its standing in R.

        Returns the position's R when the trade is carried, None when it is not. Every
        branch logs, including the refusals, because "held past 24 hours" and "closed
        at the horizon" have to be distinguishable in the journal afterwards.
        """
        if not self.carry_enabled:
            return None
        limit = self.max_hold_bars + self.carry_bars
        if bars_held >= limit:
            logger.info(
                f"[SCRAPE] {snapshot.symbol} carry declined: {bars_held} bars is the "
                f"second horizon (limit {limit})"
            )
            return None
        r = self._position_r(open_position, snapshot)
        if r is None:
            logger.info(
                f"[SCRAPE] {snapshot.symbol} carry declined: the trade's standing in "
                f"risk units cannot be read"
            )
            return None
        if r < self.carry_min_profit_r:
            logger.info(
                f"[SCRAPE] {snapshot.symbol} carry declined at the {bars_held}-bar "
                f"horizon: {r:+.2f}R is below the {self.carry_min_profit_r:+.2f}R the "
                f"carry asks for"
            )
            return None
        return r

    # ── exit ─────────────────────────────────────────────────────────────────
    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, current_capital: Optional[float] = None,
                          trade_history: Optional[list] = None):
        """Only the time stop, and the overnight carry decision at it.

        Stop and target are held by the broker. The time stop is the written horizon
        unless the carry asks for, and gets, one more horizon.
        """
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
            carried_r = self._carry_decision(open_position, snapshot, bars_held)
            if carried_r is not None:
                logger.info(
                    f"[SCRAPE] {snapshot.symbol} OVERNIGHT CARRY at {bars_held} bars: "
                    f"{carried_r:+.2f}R, held to at most "
                    f"{self.max_hold_bars + self.carry_bars} bars, re-decided every bar"
                )
                return None
            logger.info(
                f"[SCRAPE] {snapshot.symbol} time stop at {bars_held} bars "
                f"(limit {self.max_hold_bars})"
            )
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"Scrape time stop ({bars_held} bars)",
            )
        return None
