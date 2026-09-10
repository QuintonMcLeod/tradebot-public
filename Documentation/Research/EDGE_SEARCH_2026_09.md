# Edge search — findings, September 2026

Question this answers: **is there a pattern in the price data that survives real
trading costs, and if so why has the bot never found it?**

Short version: the patterns are real, the robot finds them fine, and **cost is
what kills them**. At the horizons the bot was trading, the measured edge is
smaller than the spread — by a factor of three to six. That is a structural
result, not a tuning problem.

Tooling produced for this work:

- `tools/backfill_m5_history.py` — 12 months of M5 for 26 pairs, with the spread
  actually quoted on each candle.
- `tools/backfill_daily_history.py` — 13 years of daily and 4h candles.
- `tools/edge_research.py` — intraday signal panel with clustered inference.
- `tools/edge_daily.py` — daily panel: calendar, trend, reversal, cross-sectional
  and carry tests.

---

## 1. The cost floor

Measured from live account quotes, median round-trip cost across the 26 pairs:

| pair | median quoted spread |
|---|---|
| EURUSD | 1.6 pips |
| GBPUSD | 1.9 pips |
| USDJPY | 1.6 pips |
| **median across all 26 pairs** | **2.25 pips** |

Every result below is a *gross* move minus this cost. A rule that earns less than
the spread per trade is not a strategy, however significant its t-statistic.

---

## 2. Intraday (M5, 12 months, 26 pairs, ~257k de-clustered events)

Pooled panel, **clustered by time** so that nine correlated pairs on the same day
count as roughly one observation rather than nine. Without that correction the
same table produced t-statistics about three times too large — a trap worth
remembering.

Horizon 1h, 9 pairs at full history:

| signal | mean move | × spread | t | pairs positive | net |
|---|---|---|---|---|---|
| fade 2σ stretch in low volatility | +0.52 | 0.32 | 5.7 | 100% | −1.08 |
| long Monday (drift) | +1.41 | 0.88 | 4.2 | 89% | −0.19 |
| fade 2σ stretch | +0.25 | 0.16 | 3.4 | 89% | −1.35 |
| fade 1.5σ stretch | +0.19 | 0.12 | 3.3 | 89% | −1.41 |
| follow the last hour | −0.08 | −0.05 | −2.0 | 0% | −1.68 |

Read the second column against the third. These are **statistically robust and
broad** — mean reversion after a 2σ stretch is positive on 89% of pairs and
consistent in both halves of the sample — and every one of them is worth less
than the spread it must cross.

As the horizon lengthens the move grows while the cost does not:

| horizon | strongest rule | mean move | net after cost | clusters | t |
|---|---|---|---|---|---|
| 1h | fade 2σ (low vol) | +0.52 | −1.08 | 1,585 | 5.7 |
| 4h | fade 4σ | +5.37 | +3.77 | 113 | 0.95 |
| 1d | fade 4σ | +13.80 | +12.20 | 98 | 1.61 |

So the direction of the fix is clear: **trade less often and hold longer**, because
the edge scales with the horizon while the spread does not. The 1-day 4σ fade
would be worth ~12 pips net per trade — but with only 98 independent events it is
not yet established, and it is one of ~40 rules examined.

---

## 3. Daily (13 years, 26 pairs, 3,385 sessions per pair)

Non-overlapping periods, clustered, net of the measured spread. 5-day hold:

| rule | bps per period | t | annualised | both halves |
|---|---|---|---|---|
| trend: follow past 60d | −5.66 | −2.91 | −2.8% | yes (both negative) |
| trend: follow past 120d | −5.29 | −2.66 | −2.6% | yes |
| XSMOM: long strong / short weak | −7.82 | −2.51 | −3.9% | yes |
| reversal: fade past 1d | +3.56 | +1.82 | +1.8% | yes (both positive) |

20-day hold — the reversal family strengthens:

| rule | bps per period | t | annualised | both halves |
|---|---|---|---|---|
| trend: fade past 20d | +18.39 | +2.43 | +2.2% | yes (17.9 / 18.9) |
| XSMOM: reversed 20d | +27.01 | +2.33 | +3.2% | yes (30.0 / 24.1) |
| trend: follow past 20d | −22.86 | −3.02 | −2.7% | yes (both negative) |

Two conclusions, both uncomfortable:

1. **Trend following lost money** over 2013–2026 on these pairs at 5–20 day
   horizons, after costs. So did cross-sectional momentum. The folklore rule with
   the best pedigree did not survive this sample.
2. The only consistently positive family is **short-term reversal** — fade what
   just moved. Its t-statistic is 2.3–2.4 across ~170 independent periods, and it
   is the best of roughly forty rules tried. With forty chances, a t of 2.4 is
   indistinguishable from luck. **It is not established.**

Also tested and found wanting: turn-of-month flows (−3.96 bps), a static
high-yield/low-yield carry basket (−17.45 bps at 60d, i.e. the 2013–2026 carry
trade on these legs was a loser), monthly seasonality (best: April +9.09, October
+8.10, both t<1.6), and trend applied only in low volatility (−0.70).

---

## 4. What this means

**Why the bot loses is not a missing pattern.** Mean reversion after a stretch is
real, broad and stable; the robot detects it without difficulty. It is worth
0.25–0.85 pips at intraday horizons, and the account pays 1.6–2.25 pips to
cross the spread. The strategy is not blind. It is **paying more tolls than the
journey is worth.**

That reframes the work in three ways:

1. **Trade the horizon, not the pattern.** Edge grows with holding period, cost
   does not. A 1-day hold needs roughly a tenth of the trade count of a 5-minute
   hold for the same exposure. The current bot trades 5-minute bars; most of the
   toll is self-inflicted.

2. **The one lever that changes the arithmetic is not paying the spread.**
   Earning it instead of paying it (resting limit orders rather than taking
   liquidity) is the only change that could make a 0.5-pip intraday edge viable.
   That is an execution change, not a signal change, and it is testable.

3. **Anything claimed must clear a high bar.** The measured effects sit exactly
   where noise sits. The honest bar is |t|>3 on independent clusters, positive in
   both halves, and positive after cost. Under that bar, nothing tested so far
   qualifies.

## 5. Next steps, in order of expected value

1. **Real carry data.** Carry is the best-documented FX factor and the crude
   proxy here was not a fair test. Needs interest-rate or forward-point history.
2. **Maker-vs-taker simulation.** Quantify the cost reduction from limit entry and
   whether the measured 0.5-pip intraday edge survives at maker costs.
3. **Extend the daily sample** so the 4σ reversal and weekday effects reach a few
   hundred independent events instead of a few dozen.
4. **Do not tune the current variants further.** Entry parameters cannot create an
   edge larger than the spread that the data does not contain.
