# Large targets in FX: does a bigger target survive the spread?

Date: 2026-09-13
Data: `candle_history_36m` (15 pairs, 2023-09-26 to 2026-09-10, M5), cross-checked on
`candle_history_12m` (26 pairs, last 12 months).
Harnesses: `tools/edge_targets.py`, `tools/edge_targets_pairs.py` (both new).

## The question

The scrape experiment died on a cost ratio, not on a bad signal. A 10-pip target
against a 1.6-pip round trip hands away 16% of the trade before the signal does
anything. The obvious escape is a larger target: at 40 pips the same toll is 4%.
This document asks whether that escape actually works.

## Method

For each candidate entry, walk the forward path with no exit applied and record the
running best and worst excursion. Because those extremes are monotone in bar index,
the bar at which any target or stop would have filled is a binary search, so a
49-cell target/stop grid is evaluated on the same paths for free. Each trade is
charged the spread really quoted at its own entry bar (the data carries it), and
when both barriers fall inside one bar the stop is assumed to fill first.

Entries tested, all price action, no indicators: prior-day range break, 5-day range
break, 12-hour volatility-compression break, pullback in trend, the validated hour-20
scrape as a control, and the direction-flipped mirror of three of them.

## Result 1: the cost ratio does improve with target size

Mechanically, as expected. Charging each trade its own quoted spread:

| Pair | median spread | hour-20 spread |
|---|---|---|
| EURUSD | 1.60 | 1.55 |
| USDJPY | 1.70 | 1.80 |
| EURAUD | 2.70 | 2.80 |
| GBPJPY | 3.30 | 3.15 |
| CHFJPY | 3.40 | 3.35 |

A correction to earlier work: 1.6 pips is the EURUSD number, not the portfolio
number. Across the 15 pairs the median is 2.45 pips and at hour 20 it is 2.96. Every
earlier cost sweep that assumed a flat 1.6 was optimistic for everything except
EURUSD.

## Result 2: trend and breakout entries have no edge at any target size

Across 32 rule/horizon configurations, **27 had zero profitable cells out of 49**.
Following a breakout does not merely fail to clear the spread; its gross expectancy
is indistinguishable from zero. For prior-day breaks at a 1-day horizon the gross is
-0.44 pips, against roughly -0.46 pips attributable to the conservative intrabar
assumption and a spread of 2.45. Nothing is left over.

| rule | horizon | profitable cells | mean net |
|---|---|---|---|
| donchian_prevday | 1d | 0/49 | -6.79 |
| pullback_trend | 1d | 0/49 | -6.84 |
| donchian_5day | 1d | 0/49 | -6.64 |
| compression_break | 1d | 0/49 | -7.20 |
| fade_prevday | 1d | 0/49 | -6.71 |
| fade_compression | 1d | 0/49 | -7.57 |

Taking the other side of the same break does not help either: every mirrored fade
rule was also 0/49 at every horizon. The signal carries no exploitable directional
information in either direction. This is the whipsaw thesis, confirmed and quantified.

Never trust the best cell of a 49-cell grid. With 49 brackets and 32 configurations,
1,568 hypotheses were examined. The largest t anywhere in the unrestricted sweep was
1.63; the 2.20 quoted below comes from a pair subset chosen after seeing the results,
which is exactly the kind of selection this method has to survive rather than reward.

## Result 3: the one positive family decays

The hour-20 fade of a fresh range break was the only entry whose whole target grid
stayed positive, and only with a multi-day hold. Restricting to the six cheapest
pairs (spread <= 2.2 pips) at a 40-pip target and 40-pip stop over 5 days:

| set | n | spread | gross | net | hit | t |
|---|---|---|---|---|---|---|
| 6 cheap pairs | 359 | 1.98 | +6.57 | **+4.59** | 58.2% | **2.20** |
| first half | 180 | 1.85 | +10.67 | +8.81 | 63.3% | 3.06 |
| second half | 179 | 2.11 | +2.46 | +0.35 | 53.1% | 0.12 |

The pooled t of 2.20 looks like a finding. The temporal split kills it: the entire
effect lives in the first half and has decayed to nothing in the last 18 months.
Gross falls from +10.67 to +2.46 while spread only widens from 1.85 to 2.11, so this
is a collapse in edge, not a rise in cost.

A scan of 35 configurations across horizons 1-10 days and brackets 20-60 pips found
the same shape everywhere: the large brackets look strong in the full sample purely
because of the first half. The configurations that are positive in **both** halves
are the small brackets, at only +1.3 to +1.6 pips net with t around 1.5.

## Result 4: the multi-day hold pays financing the bracket sweep never charged

Read live from the account's own instrument list. Adverse side only (never a credit),
annualized rate applied as level x rate / 365, seven charged days covering a
Wednesday triple:

| pair | adverse/day | 5-day hold |
|---|---|---|
| GBPJPY | 0.932 | 6.52 |
| GBPCHF | 0.827 | 5.79 |
| USDJPY | 0.719 | 5.03 |
| AUDJPY | 0.632 | 4.42 |
| USDCHF | 0.612 | 4.28 |
| EURUSD | 0.128 | 0.89 |
| NZDUSD, AUDUSD, GBPUSD, CHFJPY | 0.000 | 0.00 |

Median across the 15 pairs is about 1.1 pips over a 5-day hold, up to 6.5 for the
carry pairs. Against a +4.59 pip edge this is material, and it is enough to turn the
recent-period +0.35 negative. These are current rates; over the 2023-2026 backtest
the differentials differed, so this is an order-of-magnitude correction rather than a
precise historical charge.

## Conclusion

A larger target does fix the spread ratio, but it does not produce a durable edge,
and the reason is not cost. The entries that can reach a large target are
trend/breakout entries, and those carry no directional information in FX at any
horizon from 1 to 10 days. The one mean-reverting entry that did have an edge has
stopped working. Buying time to let a target fill introduces financing of the same
order as the spread that was saved, so the toll is not removed by holding longer —
it changes shape.

The bottleneck is the entry signal, not the cost and not the target size.

## Where to point the effort next

Screen entries on **gross** expectancy first, with cost switched off. That separates
"no signal" from "signal killed by cost", which is the distinction every result above
turns on. The scrape rule had about +5 pips gross and that was not enough; a signal
worth trading needs a gross edge several times the toll, and finding one is the only
remaining question. `tools/edge_targets.py` answers it in minutes per candidate,
which makes it cheap to reject ideas.

## Corrections made during this work

- Reported first that breakout entries lose significantly (t of -16, n ~8000). That
  overstated it: the conservative stop-wins-ties rule penalises both a trade and its
  mirror, so part of that -2.89 is the assumption, not the market. The defensible
  claim is that gross expectancy is near zero, not that the signal is actively bad.
- Reported a between-pair t of 18.8 on 4 pairs. That is not a valid test; a
  between-pair t needs far more clusters. The within-trade pooled t of 2.20 on 359
  trades is the honest figure.
- Reported a 5-day financing cost of 5-14 pips by charging the credit side as a cost.
  Corrected above.
