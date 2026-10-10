# Improving the scrape entry

> **CORRECTION, 2026-09-16 — the net figures below are too optimistic.**
>
> Results 2 and 3 charge a single flat cost per trade and describe it as "net of
> each trade's own quoted spread". Those are not the same thing, and the
> difference is large. `tools/edge_entry.py` takes one `--cost` value; the flat
> values used here were 2.30 pips (15 pairs) and 3.10 (26 pairs), which are the
> *medians* of the respective event subsets. The spread distribution across
> these pairs is strongly right-skewed, so the *mean* cost per trade is well
> above the median, and the mean is what a per-trade charge must use.
>
> Re-costed on each trade's own quoted spread with `tools/edge_cost_check.py`,
> which reproduces the gross figures and the flat-cost net figures below almost
> exactly (n=1984 against 2052, and n=1029 against 1051; the small count
> differences are data vintage):
>
> | set | bracket | gross | net @ flat (as below) | **net @ own spread** |
> |---|---|---|---|---|
> | 15 pairs, 3 years | T15/S20 | +3.53 | +1.23 (t=+3.34) | **+0.51 (t=+1.38)** |
> | 26 pairs, 12 months | T15/S25 | +4.62 | +1.52 (t=+2.78) | **−0.22 (t=−0.38)** |
> | 26 pairs, 12 months | T15/S20 | +4.46 | +1.36 (t=+2.71) | **−0.38 (t=−0.73)** |
>
> The subset mean spread is 3.02 pips for the 15-pair set (median 2.30) and 4.84
> for the 26-pair set (median 3.10). This is not a few outliers: trimming at the
> 99th percentile leaves mean costs of 2.82 and 4.55, and in the 26-pair set
> 28.2% of trades were quoted above 5 pips, accounting for 60.6% of total cost.
>
> The consequences are material. The 15-pair headline falls from +1.15 (t=3.17)
> to +0.51 (t=1.38), which is below the pre-registered bar of |t|>3. The
> 26-pair set, which was the independent cross-sectional confirmation that made
> this the only surviving strategy, goes **negative** at both brackets.
>
> The gross edge is real and reproduces. What does not survive is the cost
> assumption. The recommendation to move from a 4-hour to a 24-hour hold still
> stands — the horizon effect is genuine — but the resulting expectancy does not
> clear the bar, and the forward paper test should be read with that in mind.
>
> The text below is left as written so the reasoning that led to these runs
> stays visible.

Date: 2026-09-13
Data: `candle_history_36m` (15 pairs, 2023-09-26 to 2026-09-10, M5) and
`candle_history_12m` (26 pairs, last 12 months, 11 of them not in the 36m set).
Harness: `tools/edge_entry.py` (new). Feature work reuses `edge_targets.py`.

## What was asked

Keep scraping and keep the small targets; improve the entry instead. Costs were
switched off for the search so the signal would be visible rather than buried under
a 2.3-pip toll.

## What was tested

Every fresh break of a prior 20-bar range, with the conditions around it recorded so
one event pool could be read through any filter: hour, day of week, break depth in
pips and in ATR, whether the break bar expanded, how far price had stretched from its
mean, the width of the range that broke, the volatility regime, and how many bars had
already run in the break direction. Two entry types: fade the break as it happens, and
wait for it to fail before entering.

## Result 1: of every feature tested, only break depth matters

Fading a fresh break at a 10/20 bracket, hour 20, as the break depth increases:

| break depth past the range | n | gross | hit% |
|---|---|---|---|
| any break | 2069 | **-5.21** | 49.3 |
| >= 1 pip | 827 | -2.62 | 57.9 |
| >= 2 pips | 399 | -0.75 | 64.2 |
| >= 3 pips | 230 | **+0.48** | 68.3 |

Monotonic and coherent: a marginal break is noise, a deep break is an overextension
and reverts. Nothing else moved the number. Hour of day was negative in all 24 hours
before the depth filter, and no hour rescued it. Day of week, bar expansion,
overextension, range width, volatility regime and bar-count exhaustion were all
negative in every bucket. **Waiting for the break to fail before entering was worse
than fading it immediately** (-5.09 against -4.36 gross), so the confirmation entry
was dropped.

## Result 2: the hold time, not the entry, was the real problem

Same entry (hour 20, depth >= 2 pips), varying only how long the trade is allowed.
Net of each trade's own quoted spread, best bracket in each case:

**15 pairs, 3 years**

| hold | trades | best bracket | gross | net | t | halves |
|---|---|---|---|---|---|---|
| 4h | 2187 | T8/S20 | +0.27 | **-2.03** | -7.59 | -3.12 / -0.92 |
| 8h | 2187 | T8/S20 | +2.15 | -0.15 | -0.62 | -1.32 / +1.04 |
| 12h | 2187 | T8/S20 | +2.71 | +0.41 | +1.76 | -0.66 / +1.51 |
| 16h | 2187 | T12/S20 | +2.94 | +0.64 | +2.09 | -0.75 / +2.07 |
| **24h** | 2052 | **T15/S20** | **+3.45** | **+1.15** | **+3.17** | -0.26 / +2.60 |
| 36h | 1852 | T15/S20 | +3.76 | +1.56 | +4.09 | +0.02 / +3.09 |

**26 pairs, last 12 months**

| hold | trades | best bracket | gross | net | t | halves |
|---|---|---|---|---|---|---|
| 4h | 1115 | T8/S20 | +1.22 | **-1.88** | -5.23 | -2.53 / -1.21 |
| 12h | 1115 | T10/S20 | +3.38 | +0.28 | +0.75 | -0.91 / +1.50 |
| **24h** | 1051 | **T15/S25** | **+4.61** | **+1.51** | **+2.79** | -0.19 / +3.21 |
| 36h | 957 | T15/S25 | +4.76 | +1.66 | +2.94 | -0.41 / +3.75 |

At a one-day hold the whole bracket grid is profitable - 7 of 7 cells positive on
both datasets - and it holds even on the 26-pair set whose median spread is 3.10
pips, because the gross has grown to +4.6.

The live variant currently runs a 4-hour hold. That row is the one that loses money.

## Result 3: the honest caveat

The one-day hold is positive in the **second** half of the 36-month sample and flat to
negative in the first (-0.26 against +2.60). So the filter-selection test that was
planned could not run as designed: selecting on the first half yields nothing. What
stands instead is cross-sectional confirmation - the 26-pair set, 11 pairs of which
are not in the 15-pair set, independently shows the same result with t = 2.79 and
7/7 cells positive.

Two readings are possible and the data does not separate them: this is a real effect
that appeared in the last 18 months, or it is a regime that will fade again. It has
earned a forward paper test, not a live allocation.

## Recommended change to the variant

`forex_scrape_fade` as it stands: target 10, stop 20, `max_hold_bars` 48.
What the measurement supports: **target 15, stop 20, `max_hold_bars` 288.**

The entry itself needs no change - the depth rule already in the variant is the one
filter that mattered. The change that carries the result is giving the trade a day
instead of four hours.

## A bug found and fixed during this work

The first run of this harness thinned events on the pooled timestamps of all pairs.
Because every pair breaks at hour 20 simultaneously, that collapsed 26 pairs into a
single trade per day and reported n = 43 instead of 1100. De-clustering now runs
inside each symbol. Two earlier intermediate results in this session - a horizon
comparison showing 12h as best, and a between-pair t of 18.8 - were produced before
that fix and are withdrawn.
