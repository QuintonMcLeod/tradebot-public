# Deriving exits from MFE/MAE, as the operator asked

The critique: MFE and MAE are the data that tell you where the target and stop
belong. A human watches a trade go up, sees price give ground, and bails out keeping
something. A bot holds a fixed target, watches the trade turn negative, and keeps
nothing. The configuration should be read off the distribution.

That is a fair test and it had not been run. `tools/edge_exits.py` does it.

## Method

For the validated entry (fade a fresh 20-bar range break, 20:00 UTC), record each
trade's **entire path** — best favourable and worst adverse excursion at every bar —
with **no exit rules applied**, so the distribution is not shaped by the exits being
tested. Then evaluate exit schemes against those same recorded paths, net of each
pair's measured spread. 6,567 trades, 48-bar window.

## The distribution

| percentile | MFE (pips) | MAE (pips) |
|---|---|---|
| p25 | 5.6 | −14.6 |
| **p50** | **10.1** | **−7.4** |
| p60 | 12.5 | −5.7 |
| p70 | 15.8 | −4.1 |
| p80 | 21.0 | −2.8 |
| p90 | 31.4 | −1.5 |

Median ATR 2.7 pips, median spread 1.90 pips. **99 % of trades go positive at some
point**, and the adverse side is smaller than the favourable side — the median trade
reaches +10.1 pips and only ever goes −7.4.

That distribution is the argument for the current configuration: **the fixed target
already sits at the median MFE (10.1 pips)**. It is not an arbitrary number; it is
where most trades actually reach.

## Every exit scheme tested, net of measured spread

| scheme | gross | net | t | share closing green |
|---|---|---|---|---|
| **current fixed 10/20** | **2.00** | **−0.15** | 0.05 | **61 %** |
| no exit at all (hold to window end) | 1.68 | −0.47 | −1.34 | 48 % |
| distribution p60/p60 (13/6) | 0.77 | −1.38 | −7.95 | 38 % |
| bail 0.3 ATR after +0.3 ATR | 0.59 | −1.56 | −17.31 | 25 % |
| bail 0.2 ATR + TP p80, SL20 | 0.52 | −1.63 | −21.41 | 22 % |
| bail 0.2 ATR after +0.2 ATR | 0.46 | −1.69 | −22.98 | 22 % |
| bail 0.2 ATR after +0.1 ATR | 0.34 | −1.81 | −25.84 | 19 % |
| bail 0.2 ATR from breakeven | 0.16 | −1.99 | −31.05 | 17 % |

## What this says

**The human bail loses, and the reason is arithmetic rather than judgement.** A 0.2
ATR give-back threshold is ~0.5 pips, while the round trip costs 1.9 pips. Bailing
"to keep something" keeps less than the toll: the scheme closes green only 17–22 % of
the time against 61 % for the fixed bracket. It converts trades that would have
reached the target into scratches that do not pay for themselves.

**Brackets read off the distribution also lose**, because the MAE side is small: a
p60 stop of 6 pips is tighter than the noise, so trades are stopped before the move
they were entered for. Reading a stop off the MAE distribution is only sound if the
MAE is caused by the market rather than by the spread, and here p90 MAE is just
−1.5 pips — inside the spread.

**The existing fixed 10/20 bracket is the best of every scheme tested**, and it sits
at break-even (net −0.15 pips, t = 0.05) rather than losing. The configuration is
not the problem, and neither is the exit logic.

**The gap is cost, quantified.** Across the live paper record, 43 % of trades went
positive and closed negative: median MFE $10.99, median realised −$6.90, a gap of
$21.99 of which $14.36 is the modelled round trip. MFE is measured from the entry
*fill* as a mid-price excursion; it does not include the cost of getting out. So the
dashboard genuinely does overstate what a trade could have captured — a reporting
defect worth fixing, separate from the strategy question.

## Conclusion

Gross expectancy is +2.00 pips per trade. The round trip costs 2.15. Exits only
*redistribute* that gross edge; they cannot create one. Every scheme above, including
the human-style bail, is a different way of arriving at the same arithmetic, and the
current configuration already captures the largest share of it. What is missing is
not a better exit — it is a gross edge larger than the toll, which means a cheaper
venue or a different instrument.
