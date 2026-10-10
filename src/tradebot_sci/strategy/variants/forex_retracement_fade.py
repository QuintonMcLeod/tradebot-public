"""ForexRetracementFade: fade a deep retracement of a fresh impulse, at a level.

Rule
----
Wait for a fresh directional impulse, wait for price to give back between half and
three quarters of it, require that the give-back lands on a structural level, require
the last closed candle to close back out of the retracement zone in the impulse
direction, then trade with the impulse, targeting the extreme the give-back started
from. The stop goes *beyond* the far edge of the zone rather than on it. Reject the
setup when the round trip cost is too large a share of the target.

Seven live trades on this desk produced the shape of the rule. That is the entire
live sample. n=7 is not an edge, it is a hint, and nothing in this file should be
read as evidence that the rule works. The backtest is what decides, and the docstring
records what it said. The parameter values below are the ones the live record
suggested, kept at those values rather than tuned, so that the backtest is a test of
a fixed rule instead of a search.

One deliberate correction to the written rule, stated here so nobody has to rediscover
it: the target is the far end of the impulse, the extreme the retracement began from,
NOT the impulse's starting extreme. Both directions of the trade run WITH the impulse,
so the entry always sits between the two extremes; a target at the starting extreme is
therefore behind the entry in both directions, which makes the reward negative for
every possible input and makes the MIN_R gate unsatisfiable. Target equals the extreme
the retracement began from is the only reading under which the rule can fire at all.

Why each parameter has the value it has
---------------------------------------
MIN_IMPULSE_ATR = 2.5 (``min_impulse_atr``)
    The leg being faded has to be a real move, not the ordinary breathing of the
    pair. 2.5 times ATR(14) is roughly the smallest leg that still had an origin
    worth targeting in the live record, and the same logic that made the deep-break
    threshold load-bearing in ``forex_scrape_fade``: a marginal leg is noise and
    noise does not revert.

RETRACE_MIN = 0.50, RETRACE_MAX = 0.764 (``retrace_min``, ``retrace_max``)
    0.50 is the point where the give-back stops being a pullback and starts being a
    reversal candidate. 0.764 is the last Fibonacci level before the leg is
    effectively gone. Fading a shallower dip buys a worse price for the same
    invalidation; fading a deeper one is no longer trading with the impulse.

SWING_LOOKBACK = 5 (``swing_lookback``)
    A fractal needs 5 bars either side to be a swing rather than a single spike.
    That is the shortest lookback in the GUI settings that still produced levels the
    live trades were visibly reacting to, and it is the standard value in this
    codebase's structural strategies.

STOP_BUFFER_ATR = 0.25 (``stop_buffer_atr``)
    This is the single unambiguous lesson from the first live trade. The stop was
    placed AT the consolidation high, exactly where every other participant could
    see it, it was swept, and price then ran the way the trade expected. A stop on a
    level is a stop the market can reach without invalidating anything. 0.25 ATR is
    far enough beyond the level that a sweep of the level does not take the stop, and
    near enough that it does not wreck the R multiple.

MIN_R = 1.5 (``min_r``)
    Below 1.5 the rule needs a high hit rate to break even, and the live sample is
    too small to claim one. The target is fixed at the far end of the impulse and the
    stop is fixed at the far edge of the zone, so this gate is really a gate on how
    large the impulse was and how deep into the zone the entry sat. Because the entry
    is a close back out of the zone, the achievable R is capped at roughly 1.9 and
    this gate is the tightest geometric constraint in the file.

COST_MODEL_PIPS = 2.45 (``cost_model_pips``)
    The measured portfolio median round trip cost. This desk's paper record is
    pre-cost flat and net -692.55 USD over 101 trades, so the toll is what kills the
    book, not the picking. 2.45 against 101 trades is the best available estimate of
    what a round trip actually costs here.

FINANCING_PIPS_PER_DAY = 0.9 (``financing_pips_per_day``)
    One measured rollover charge, 0.88 pips, rounded to 0.9. Charged per day of
    expected holding, because a fade that holds through a rollover pays for it.

MAX_COST_FRACTION = 0.15 (``max_cost_fraction``)
    Reject when the estimated round trip cost exceeds 15 percent of the target
    distance. A rule that gives away more than about a sixth of its target to the
    broker needs an edge far larger than seven trades can demonstrate. This gate is
    deliberately the strictest in the file: it is the one that encodes the portfolio's
    measured cause of death.

HORIZON_HOURS = 24 (``horizon_hours``)
    The impulse being faded is a fresh one, so the reversion is expected within a
    day. The same value ``forex_scrape_fade`` needed for its fade to work, and the
    expected hold used for the financing charge.

Measured result
---------------
Backtested at the defaults above, unmodified, on every cached series available here:
EURUSD, GBPUSD, USDJPY, AUDUSD and EURJPY, on 5m, 15m, 1h and 4h. The cached history
is one month at the widest (EURUSD 5m, 2026-01-30 to 2026-03-06, 7,203 bars) and
under three weeks for the four cross-checked pairs, so this is a small sample and it
is reported as one.

  timeframe   trades   net pips   gross pips   win rate   expectancy   profit factor   max DD
  5m              50     -62.1        +69.5      40.0%      -0.097R          0.90     206.9p
  15m             39      -7.4       +105.2      46.2%      +0.030R          0.99     176.2p
  1h              13     +38.0        +76.5      53.8%      +0.117R          1.14     220.0p
  4h               2      +0.1         +8.0      50.0%      -0.040R          1.01      12.1p
  pooled         104     -31.4       +259.2      44.2%      -0.022R          0.98     418.0p

Pooled gross was +259.2 pips and the cost charged took 290.5 pips, so the rule is
gross positive and net negative. That is the same mechanism that killed the paper
book: +2.49 pips per trade gross does not survive a 2.79-pip average toll. The
pooled t statistic is -0.10 on trades, +0.56 on 24 entry-day clusters and -0.41 on 58
symbol-day clusters. The sample splits +203.3 pips on the first half and -234.7 on the
second, so the sign does not hold out of sample either, and the pooled sign flips if
GBPUSD alone is removed (77 trades, -173.8 pips).

Verdict: this does NOT clear the pre-registered bar of |t| > 3 on independent clusters,
the same sign out of sample, and a positive result after real quoted costs. It fails
all three. It is kept as a registered, selectable strategy under observation, not as an
edge, and it should not be enabled on a live profile on this evidence. The n=7 live
record remains a hint, not support.

Timeframe
---------
SESSION_PROFILE is None: the rule is selected by profile config, not gated to a named
session. It is deliberately absent from the Meta-SCI ensemble, because the ensemble
picks a strategy per bar by regime and this rule depends on its own multi-gate
structure surviving intact.

Not part of the Meta-SCI ensemble
---------------------------------
Do not add it to ``meta_sci.py``.

The cost model is the desk's measured 2.45-pip median round trip, not a per-pair
quoted spread: no per-pair quoted spread table exists in this checkout, so the toll is
the best available estimate rather than the quoted truth.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import (
    AITradeDecision,
    close_position_decision,
    stand_aside_decision,
)
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

_PIP = {"JPY": 0.01}
_DEFAULT_PIP = 0.0001

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


class ForexRetracementFade(BaseStrategy):
    """Fades a 0.50 to 0.764 retracement of a fresh impulse, at a structural level."""

    # None means "selected by config, not gated to a named session".
    SESSION_PROFILE = None

    def __init__(self, **kwargs):
        super().__init__("ForexRetracementFade")

        self.min_impulse_atr = float(kwargs.get("min_impulse_atr", 2.5))
        self.retrace_min = float(kwargs.get("retrace_min", 0.50))
        self.retrace_max = float(kwargs.get("retrace_max", 0.764))
        self.swing_lookback = int(kwargs.get("swing_lookback", 5))
        self.stop_buffer_atr = float(kwargs.get("stop_buffer_atr", 0.25))
        self.min_r = float(kwargs.get("min_r", 1.5))
        self.cost_model_pips = float(kwargs.get("cost_model_pips", 2.45))
        self.financing_pips_per_day = float(kwargs.get("financing_pips_per_day", 0.9))
        self.max_cost_fraction = float(kwargs.get("max_cost_fraction", 0.15))
        self.horizon_hours = float(kwargs.get("horizon_hours", 24.0))

        # How far back the impulse search runs, in structure bars, and how stale a leg
        # may be before it no longer counts as fresh. A 2.5 ATR leg older than this is
        # no longer a fresh impulse; the depth gate would rarely catch that on its own,
        # because price can wander back into the 0.50 to 0.764 band much later.
        self.impulse_lookback = int(kwargs.get("impulse_lookback", 120))
        self.impulse_max_age_bars = int(kwargs.get("impulse_max_age_bars", 40))
        # How many candidate impulse legs to test against the full gate chain, most
        # recent first. Bounded so the per-bar cost stays flat.
        self.max_leg_candidates = int(kwargs.get("max_leg_candidates", 8))

        # Structural level matching: how far a level may sit from the zone edge and
        # still count as confluence. 0.10 ATR avoids a pixel-perfect miss on a level
        # the eye would call a touch.
        self.level_tolerance_atr = float(kwargs.get("level_tolerance_atr", 0.10))

        # Broken-consolidation detection: a run of at least this many bars whose whole
        # range fits inside this many ATRs is a consolidation, and its two edges are
        # levels. Both edges are collected; the overlap test decides relevance.
        self.consolidation_bars = int(kwargs.get("consolidation_bars", 12))
        self.consolidation_max_atr = float(kwargs.get("consolidation_max_atr", 1.0))

        # ATR period for the impulse threshold and the stop buffer.
        self.atr_period = int(kwargs.get("atr_period", 14))

        # Expected holding used to charge financing. Defaults to the time stop, which
        # is the honest worst case for a rule whose exit is either the bracket or the
        # horizon.
        self.expected_hold_hours = float(
            kwargs.get("expected_hold_hours", self.horizon_hours)
        )

        logger.info(
            f"[RETRFADE_INIT] impulse>={self.min_impulse_atr:.2f}xATR, "
            f"retrace {self.retrace_min:.3f}-{self.retrace_max:.3f}, "
            f"swing={self.swing_lookback}, stop_buffer={self.stop_buffer_atr:.2f}xATR, "
            f"min_r={self.min_r:.2f}, cost={self.cost_model_pips:.2f}p+"
            f"{self.financing_pips_per_day:.2f}p/day, "
            f"max_cost_fraction={self.max_cost_fraction:.2f}, "
            f"horizon={self.horizon_hours:.0f}h"
        )

    # helpers
    @staticmethod
    def _pip_size(symbol: str) -> float:
        s = (symbol or "").upper()
        return _PIP.get(s[-3:], _DEFAULT_PIP)

    def _timeframe_minutes(self, timeframe: Optional[str]) -> int:
        return _TF_MINUTES.get((timeframe or "5m").lower(), 5)

    def _structure_candles(self, snapshot: MarketSnapshot, gates: dict) -> list:
        """Candles used for impulse, levels and the rejection check.

        Prefers higher timeframe candles when the caller supplies them, because a
        leg worth fading is a structural object and reads better on a slower series.
        Falls back to the snapshot series, which is what a single timeframe backtest
        and the paper bot both provide.
        """
        for key in ("htf_candles", "higher_tf_candles", "candles_htf", "candles_1h"):
            series = (gates or {}).get(key)
            if series and len(series) > 0:
                return list(series)
        series = getattr(snapshot, "htf_candles", None)
        if series and len(series) > 0:
            return list(series)
        return list(snapshot.candles or [])

    def _pivots(self, series: list, lookback: int) -> list:
        """Fractal swings as (index, kind, price), collapsed to alternate kinds."""
        if len(series) < (2 * lookback + 1):
            return []
        raw = []
        for i in range(lookback, len(series) - lookback):
            window = series[i - lookback: i + lookback + 1]
            hi = series[i].high
            lo = series[i].low
            if all(hi >= c.high for c in window):
                raw.append((i, "high", float(hi)))
            if all(lo <= c.low for c in window):
                raw.append((i, "low", float(lo)))
        raw.sort(key=lambda t: t[0])

        # Collapse runs of the same kind, keeping the most extreme of the run. Without
        # this a flat top reports several "swings" that are one level.
        out = []
        for idx, kind, price in raw:
            if out and out[-1][1] == kind:
                prev_idx, _, prev_price = out[-1]
                better = price >= prev_price if kind == "high" else price <= prev_price
                if better:
                    out[-1] = (idx, kind, price)
                continue
            out.append((idx, kind, price))
        return out

    def _consolidation_levels(self, series: list, end_index: int, atr: float) -> list:
        """Edges of the most recent tight block that ends before ``end_index``."""
        n = self.consolidation_bars
        if atr <= 0 or end_index < n:
            return []
        start = max(n, end_index - self.impulse_lookback)
        for stop in range(end_index, start - 1, -1):
            block = series[stop - n: stop]
            if len(block) < n:
                continue
            hi = max(c.high for c in block)
            lo = min(c.low for c in block)
            if (hi - lo) <= self.consolidation_max_atr * atr:
                return [float(hi), float(lo)]
        return []

    def _candidate_legs(self, series: list, atr: float) -> list:
        """Directional legs of at least MIN_IMPULSE_ATR ATRs, most recent first.

        A leg is only reported once it has at least one closed bar after it, because
        a leg with nothing after it has no retracement to fade.
        """
        pivots = self._pivots(series, self.swing_lookback)
        if len(pivots) < 2 or atr <= 0:
            return []
        last_closed = len(series) - 1
        legs = []
        for (i_a, k_a, p_a), (i_b, k_b, p_b) in zip(pivots, pivots[1:]):
            if k_a == k_b or i_a >= i_b:
                continue
            rng = abs(p_b - p_a)
            if rng < self.min_impulse_atr * atr:
                continue
            if last_closed - i_b > self.impulse_max_age_bars:
                continue
            if i_b >= last_closed:
                continue
            legs.append({
                "start_index": i_a,
                "end_index": i_b,
                "direction": "up" if k_b == "high" else "down",
                "start_price": float(p_a),
                "end_price": float(p_b),
                "range": float(rng),
            })
        legs.reverse()
        return legs

    def _setup_for_leg(self, snapshot: MarketSnapshot, series: list, leg: dict,
                       atr: float) -> tuple:
        """Gates 2 to 5 for one candidate leg. Returns (setup or None, reason)."""
        leg_range = leg["range"]
        end_px = leg["end_price"]
        after = series[leg["end_index"] + 1:]
        if not after:
            return None, "RetrFade: impulse ends on the last closed bar, nothing to fade"

        direction = leg["direction"]
        if direction == "up":
            zone_hi = end_px - self.retrace_min * leg_range   # shallow edge, 0.500 level
            zone_lo = end_px - self.retrace_max * leg_range   # far edge, 0.764 level
            deepest = min(float(c.low) for c in after)
            retrace = (end_px - deepest) / leg_range
        else:
            zone_lo = end_px + self.retrace_min * leg_range
            zone_hi = end_px + self.retrace_max * leg_range
            deepest = max(float(c.high) for c in after)
            retrace = (deepest - end_px) / leg_range

        # Gate 2: retracement depth, measured on the deepest excursion into the leg.
        # Measuring it on the last close instead would contradict gate 4, which wants
        # that close already back out of the zone.
        if retrace < self.retrace_min or retrace > self.retrace_max:
            return None, (
                f"RetrFade: retracement {retrace:.3f} of the leg is outside "
                f"{self.retrace_min:.3f}-{self.retrace_max:.3f}"
            )

        # Gate 3: confluence. The zone has to land on something the market can see.
        levels = [
            float(price)
            for idx, _kind, price in self._pivots(series, self.swing_lookback)
            if idx <= leg["end_index"]
        ]
        levels.extend(self._consolidation_levels(series, leg["end_index"], atr))
        tol = self.level_tolerance_atr * atr
        hits = [lv for lv in levels if (zone_lo - tol) <= lv <= (zone_hi + tol)]
        if not hits:
            return None, (
                f"RetrFade: retracement zone {zone_lo:.5f}-{zone_hi:.5f} overlaps no "
                f"swing (lookback {self.swing_lookback}) and no consolidation edge"
            )

        # Gate 4: rejection. The last closed structure candle has to close back out of
        # the zone, in the direction the impulse was travelling.
        last = after[-1]
        close = float(last.close)
        if direction == "up" and close <= zone_hi:
            return None, (
                f"RetrFade: last closed candle {close:.5f} did not close back above "
                f"the zone top {zone_hi:.5f}"
            )
        if direction == "down" and close >= zone_lo:
            return None, (
                f"RetrFade: last closed candle {close:.5f} did not close back below "
                f"the zone bottom {zone_lo:.5f}"
            )

        # Gate 5: honest R. Stop beyond the far edge of the zone, never on it.
        #
        # The target is the extreme the retracement started from, which is the far end
        # of the impulse. Taking the impulse's *starting* extreme instead would put the
        # target behind the entry in both directions, because the trade goes WITH the
        # impulse: for an up leg the entry sits in a zone above the leg low, and for a
        # down leg it sits in a zone below the leg high. A target behind the entry makes
        # the reward negative for every possible input, so the R gate could never be
        # satisfied and the rule could never fire. The extreme the retracement started
        # from is the only level that is ahead of the entry in both directions, and it
        # is also the level the instrument actually has to reclaim to resume the impulse.
        entry = float(snapshot.candles[-1].close) if snapshot.candles else close
        if self.stop_buffer_atr <= 0:
            return None, (
                "RetrFade: stop_buffer_atr is not positive, so the stop would sit on "
                "the level itself, which is the one placement the live record rules out"
            )
        target = leg["end_price"]
        if direction == "up":
            stop = zone_lo - (self.stop_buffer_atr * atr)
            risk = entry - stop
            reward = target - entry
        else:
            stop = zone_hi + (self.stop_buffer_atr * atr)
            risk = stop - entry
            reward = entry - target

        if risk <= 0 or reward <= 0:
            return None, (
                f"RetrFade: entry {entry:.5f} leaves no room to the target "
                f"{target:.5f} with the stop at {stop:.5f}"
            )

        r_multiple = reward / risk
        if r_multiple < self.min_r:
            return None, (
                f"RetrFade: realised R {r_multiple:.2f} is below the {self.min_r:.2f} "
                f"minimum (reward {reward:.5f}, risk {risk:.5f})"
            )

        return {
            "direction": direction,
            "atr": float(atr),
            "entry": entry,
            "stop": float(stop),
            "target": float(target),
            "risk": float(risk),
            "reward": float(reward),
            "r_multiple": float(r_multiple),
            "retrace": float(retrace),
            "zone_lo": float(zone_lo),
            "zone_hi": float(zone_hi),
            "level": float(min(hits, key=lambda lv: abs(lv - entry))),
            "leg_range": float(leg_range),
            "leg_start": float(leg["start_price"]),
            "leg_end": float(end_px),
        }, "ok"

    def _evaluate_setup(self, snapshot: MarketSnapshot, gates: dict) -> tuple:
        """Gates 1 to 5. Returns (setup_dict or None, reason string).

        Candidate legs are tried most recent first and each is tested against the full
        retracement geometry, not just the size threshold. That matters: the retracement
        of a 3 ATR impulse is itself a large leg, so testing only the size gate would
        nominate the retracement as the impulse, measure its own (tiny) retracement, and
        reject the very setup the rule is looking for. Taking the first leg that
        survives the whole chain is the reading under which the rule can fire.

        The reason string is always populated, so callers can log or stand aside with
        the specific gate that failed rather than a generic no-signal message.
        """
        series = self._structure_candles(snapshot, gates)
        minimum = (2 * self.swing_lookback) + self.atr_period + 2
        if len(series) < minimum:
            return None, (
                f"RetrFade: only {len(series)} structure bars, need {minimum}"
            )
        # Bound the work per call: nothing older than the impulse search window can
        # matter to the rule, and an unbounded scan is quadratic on a long series.
        span = self.impulse_lookback + minimum
        if len(series) > span:
            series = series[-span:]

        atr = calculate_atr(series, period=self.atr_period)
        if atr is None or atr <= 0:
            return None, "RetrFade: ATR unavailable on the structure series"

        # Gate 1: a fresh impulse, then gates 2 to 5 read against that leg.
        legs = self._candidate_legs(series, atr)
        if not legs:
            return None, (
                f"RetrFade: no fresh impulse leg of >= {self.min_impulse_atr:.2f} ATR "
                f"within the last {self.impulse_max_age_bars} bars"
            )

        first_reason = None
        for leg in legs[:self.max_leg_candidates]:
            setup, reason = self._setup_for_leg(snapshot, series, leg, atr)
            if setup is not None:
                return setup, "ok"
            # Keep the most recent candidate's reason: it is the one that describes
            # what the market was actually doing.
            if first_reason is None:
                first_reason = reason
        return None, first_reason

    def _cost_gate(self, setup: dict, symbol: str) -> tuple:
        """Gate 6. Returns (cost_pips, target_pips, passes, reason)."""
        pip = self._pip_size(symbol)
        target_pips = setup["reward"] / pip
        hold_days = self.expected_hold_hours / 24.0
        cost_pips = self.cost_model_pips + (self.financing_pips_per_day * hold_days)
        if target_pips <= 0:
            return cost_pips, target_pips, False, "RetrFade: target distance is zero"
        if cost_pips > self.max_cost_fraction * target_pips:
            return cost_pips, target_pips, False, (
                f"RetrFade: round trip cost {cost_pips:.2f}p is "
                f"{cost_pips / target_pips:.2f} of the {target_pips:.1f}p target, "
                f"above the {self.max_cost_fraction:.2f} ceiling"
            )
        return cost_pips, target_pips, True, "ok"

    # scoring
    def score_signal(self, snapshot: MarketSnapshot, gates: dict):
        """(score, grade, reason). Logging only: this rule is not score-gated."""
        setup, reason = self._evaluate_setup(snapshot, gates)
        if setup is None:
            if reason.startswith("RetrFade: no fresh impulse"):
                score = 20.0
            elif "retracement" in reason and "outside" in reason:
                score = 40.0
            elif "overlaps no" in reason:
                score = 55.0
            elif "did not close back" in reason:
                score = 62.0
            elif "realised R" in reason:
                score = 68.0
            else:
                score = 30.0
            return score, self.grade_from_score_100(score), reason

        cost_pips, target_pips, ok, cost_reason = self._cost_gate(setup, snapshot.symbol)
        if not ok:
            score = 70.0
            return score, self.grade_from_score_100(score), cost_reason

        # Every gate passed. R above the minimum adds conviction, and the depth of the
        # retracement adds a little more, because a fade that reached further into the
        # leg buys a better price for the same invalidation.
        score = 76.0
        score += min(6.0, max(0.0, (setup["r_multiple"] - self.min_r) * 4.0))
        score += min(4.0, max(0.0, (setup["retrace"] - self.retrace_min) * 16.0))
        score = min(score, 92.0)
        return score, self.grade_from_score_100(score), (
            f"RetrFade {setup['direction']} at {setup['retrace']:.3f} retrace, "
            f"R {setup['r_multiple']:.2f}, cost {cost_pips:.2f}p of {target_pips:.1f}p"
        )

    # entry
    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict,
                           open_position: Optional[dict] = None,
                           current_capital: Optional[float] = None,
                           trade_history: Optional[list] = None):
        if open_position:
            return None
        if gates.get("is_synthetic_override") is True:
            return None
        if not snapshot or not snapshot.candles:
            return None

        setup, reason = self._evaluate_setup(snapshot, gates)
        if setup is None:
            logger.debug(f"[RETRFADE] {snapshot.symbol}: {reason}")
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, reason)

        cost_pips, target_pips, ok, cost_reason = self._cost_gate(setup, snapshot.symbol)
        if not ok:
            logger.info(f"[RETRFADE] {snapshot.symbol}: {cost_reason}")
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, cost_reason)

        pip = self._pip_size(snapshot.symbol)
        hold_bars = max(
            1,
            int(round(self.horizon_hours * 60.0 / self._timeframe_minutes(snapshot.timeframe))),
        )
        long_side = setup["direction"] == "up"
        action = "enter_long" if long_side else "enter_short"
        bias = "long" if long_side else "short"
        side_word = "LONG" if long_side else "SHORT"

        logger.info(
            f"[RETRFADE] {snapshot.symbol} {side_word}: {setup['retrace']:.3f} retrace of a "
            f"{setup['leg_range'] / pip:.1f}p leg, into level {setup['level']:.5f}, "
            f"entry {setup['entry']:.5f}, stop {setup['stop']:.5f} "
            f"(beyond the {setup['zone_lo'] if long_side else setup['zone_hi']:.5f} zone edge), "
            f"target {setup['target']:.5f}, R {setup['r_multiple']:.2f}, "
            f"cost {cost_pips:.2f}p of {target_pips:.1f}p"
        )

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=bias,
            phase="correction",
            action=action,
            entry_price=setup["entry"],
            stop_loss=setup["stop"],
            take_profit=setup["target"],
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=(
                f"RetrFade {side_word}: {setup['retrace']:.3f} retrace of a "
                f"{setup['leg_range'] / pip:.1f}p impulse into structural level "
                f"{setup['level']:.5f}, rejection close back out of the zone"
            ),
            invalidation_conditions=(
                f"Close beyond the zone edge at "
                f"{setup['zone_lo'] if long_side else setup['zone_hi']:.5f} plus "
                f"{self.stop_buffer_atr:.2f} ATR, i.e. {setup['stop']:.5f}"
            ),
            management_instructions=(
                f"Target {setup['target']:.5f} (the extreme the retracement started "
                f"from, i.e. the far end of the impulse), stop "
                f"{setup['stop']:.5f} placed beyond the level rather than on it, "
                f"time stop {self.horizon_hours:.0f}h. Do not move the stop onto the level."
            ),
            urgency="high",
            max_hold_bars=hold_bars,
            self_managed_risk=True,
            strategy_name=self.name,
            regime="trend",
        )

    # exit
    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict,
                          gates: dict, current_capital: Optional[float] = None,
                          trade_history: Optional[list] = None):
        """Time stop only.

        The stop and the target are held by the broker, so reaching this method means
        neither has been filled. All that is left is the horizon.
        """
        if not open_position or not snapshot or not snapshot.candles:
            return None

        last_bar = snapshot.candles[-1]
        stop = open_position.get("stop_loss") or open_position.get("stop")
        target = open_position.get("take_profit") or open_position.get("target")
        if stop is not None:
            try:
                stop = float(stop)
                if last_bar.low <= stop <= last_bar.high:
                    logger.debug(
                        f"[RETRFADE] {snapshot.symbol}: stop {stop:.5f} traded this bar, "
                        f"the bracket resolves the exit"
                    )
                    return None
            except (TypeError, ValueError):
                pass
        if target is not None:
            try:
                target = float(target)
                if last_bar.low <= target <= last_bar.high:
                    logger.debug(
                        f"[RETRFADE] {snapshot.symbol}: target {target:.5f} traded this bar, "
                        f"the bracket resolves the exit"
                    )
                    return None
            except (TypeError, ValueError):
                pass

        entry_dt = self._entry_datetime(open_position)
        if entry_dt is None:
            logger.info(
                f"[RETRFADE] {snapshot.symbol}: open position carries no usable entry "
                f"timestamp, so the {self.horizon_hours:.0f}h time stop cannot be "
                f"evaluated; holding rather than guessing the age"
            )
            return None

        now_dt = last_bar.timestamp
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        age_hours = (now_dt - entry_dt).total_seconds() / 3600.0
        if age_hours >= self.horizon_hours:
            logger.info(
                f"[RETRFADE] {snapshot.symbol}: time stop at {age_hours:.1f}h "
                f"(horizon {self.horizon_hours:.0f}h), neither bracket filled"
            )
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"RetrFade time stop ({age_hours:.1f}h with neither stop nor target filled)",
            )
        return None

    @staticmethod
    def _entry_datetime(open_position: dict) -> Optional[datetime]:
        """Parse the entry timestamp from whichever key the caller populated."""
        for key in ("entry_time", "entry_timestamp", "opened_at", "open_time", "timestamp"):
            raw = open_position.get(key)
            if raw is None:
                continue
            if isinstance(raw, datetime):
                dt = raw
            else:
                try:
                    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        return None
