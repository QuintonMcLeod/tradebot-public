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

## 4b. Round two: carry, execution, and payoff asymmetry

### Carry, with real interest rates

`tools/fetch_rates.py` pulls OECD three-month interbank rates for all eight
currencies from FRED (no key needed, history back to the 1950s). Carry is then the
rate differential between the two legs, lagged a month so nothing uses an
unpublished figure. `tools/edge_carry.py`:

| portfolio (monthly rebalance, net of spread) | bps/mo | t | annualised | pre-2020 | 2020+ |
|---|---|---|---|---|---|
| cross-sectional carry, with accrual | +2.5 | 0.21 | +0.4% | +3.8 | +1.3 |
| cross-sectional carry, spot only | −10.3 | −0.84 | −1.7% | −9.5 | −10.9 |
| time-series carry, with accrual | +1.2 | 0.16 | +0.2% | −4.8 | +7.0 |

The quintile ladder — the test that separates factors from accidents — is **not
monotonic**: 0.5, 7.8, 7.0, 3.3, 7.0 bps from the lowest-carry quintile to the
highest. There is no monotone relationship between carry and return here, so this
is not a factor result. Worth noting what the split shows: the high-yielders
appreciated *less* than the low-yielders on spot over this sample, and the accrual
merely offset that. Carry is not a free lunch; it is compensation for exactly that
risk, and in 2013–2026 the compensation was roughly break-even.

### Maker execution: does a better entry price rescue the real pattern?

The best-measured intraday effect was fading a 2σ stretch in low volatility
(+0.52 pips, t=5.7, positive on 100% of pairs). `tools/edge_maker.py` rests a limit
order D pips better than the signal close and measures what actually happens:

| limit offset | fill rate | net pips per signal | net pips per fill |
|---|---|---|---|
| 0.00 (market) | 99% | −0.46 | −0.47 |
| 0.50 | 89% | −0.41 | −0.46 |
| 1.00 | 81% | −0.32 | −0.40 |
| 2.00 | 65% | −0.23 | −0.35 |
| 3.00 | 52% | −0.16 | −0.30 |

A three-pip better entry improves the outcome by only 0.30 pips. **Adverse
selection consumes about 94% of the price improvement**: the limit fills when
price keeps coming, which is the case where the signal was wrong. This is the
quantitative death of the "just use limit orders" fix — the edge was smaller than
the spread to begin with, and the maker route cannot recover it.

### Payoff asymmetry: does a winner keep running?

`tools/edge_asymmetry.py` buckets every bar by how far price has already travelled
(in ATR) and measures the next move in the same direction, net of cost:

| travel bucket | n | net pips | t | reading |
|---|---|---|---|---|
| −3 ATR or worse | 54,688 | −2.02 | −25.97 | gives it back |
| −1 to −2 ATR | 92,028 | −2.08 | −21.97 | gives it back |
| +0.5 to +1 ATR | 57,900 | −1.88 | −20.26 | gives it back |
| +2 to +3 ATR | 65,572 | −2.09 | −24.74 | gives it back |

Every bucket lands at roughly minus the spread, which means the **gross forward
move is zero in both directions at every level of unrealised profit**. There is no
asymmetry to exploit: being up does not make the position more likely to continue,
and being down does not make it more likely to revert. "Cut losers, let winners
run" is not supported by this data at the hourly horizon — the only thing the test
detects is the cost of acting.

*(An earlier version of this test reported t-statistics of ±60 with a perfect
split between winners and losers. That was a bug: `copysign(fwd, n)` keeps the
forward move's magnitude and takes the *bucket's* sign, so the result was trivially
nonzero by construction. The fix is `sign(n) * fwd`. Recorded because a spectacular
result is exactly when to look for the error.)*

### Calendar effects, with enough power to judge them

Thirteen years gives ~676 independent observations per weekday. Earlier, a
mis-labelled weekday mask (marking the bar whose forward return realises on the
*next* session) plus an uncharged round trip produced a fake "Thursday drift"
candidate. With the label corrected and the spread charged, every weekday is
negative — Wednesday −4.63 bps (t=−4.79), Thursday −4.40 (t=−4.97), Monday
−1.00 — which is what holding a zero-drift asset while paying two basis points of
spread per day looks like. Turn-of-month is −0.55 bps. The best month of the year
is October at +1.98 bps (t=1.70), which is noise.

---

## 4c. The reversal candidate, tested on 23 years

The one family with a persistent positive sign was short-term reversal (+2.2 to
+3.2%/yr net on 2013–2026, t≈2.4–2.7). It was the only thing worth a second look,
so the sample was extended back to 2003 — 6,703 sessions per pair, 26 pairs:

| rule (2003–2026, net of spread) | hold 5 | hold 20 |
|---|---|---|
| reversal: fade past 5d | −1.46 bps (t=−0.86) | −3.96 (t=−0.63) |
| reversal: fade past 1d | +0.45 bps (t=0.27) | −3.64 (t=−0.63) |
| XSMOM: reversed 20d | −1.89 bps (t=−0.73) | +0.51 (t=0.06) |
| trend: follow past 60d | −3.57 bps (t=−1.99) | −4.84 (t=−0.70) |

**It disappears.** At a 20-day hold the two halves of the extended sample have
opposite signs (−23.70 bps then +16.42), which is what a sample-specific artifact
looks like. Trend following also stops being significant once the sample is not
the specific 2013–2026 window.

This is the most useful lesson in the whole exercise: an effect that looked
credible on thirteen years, with a consistent sign in both halves *of that
thirteen years*, evaporated on twenty-three. Had the bar been "t>2 on the data I
happened to have", it would have been shipped, and it would have lost money. The
multiple-testing bar is not bureaucracy; it is the difference between a strategy
and a story.



Every rule named in the research plan, tested with cost accounting, clustering and
a held-out era check:

| hypothesis | data | verdict |
|---|---|---|
| Intraday mean reversion | 26 pairs × 12m M5, 257k events | **real** (+0.25 to +0.52 pips, t 3.4–5.7, 89–100% of pairs) but 3–6× smaller than the spread |
| Trend following / momentum | 26 pairs × 13y daily, +4h | **negative** (−5 to −7 bps per period, t −2.5 to −6.9), both halves |
| Cross-sectional momentum | same | **negative** |
| Carry | 26 pairs × 13y, real rates | flat (+2.5 bps/mo, t=0.21) and non-monotonic |
| Calendar (weekday, turn-of-month, month) | 13y daily, ~676 obs per weekday | all negative once the round trip is charged |
| Session effects | 12m M5 | real but 0.07–0.36 pips vs a 1.6-pip spread |
| Level effects (round numbers, prior-day extremes) | 12m M5 | insignificant |
| Payoff asymmetry | 12m M5, hourly | **no asymmetry at all** — gross forward move is zero in every bucket |
| Maker execution instead of taker | 12m M5, six offsets | adverse selection eats 94% of the improvement; still negative |
| Short-term reversal | 13y daily + 4h, then 23y | positive on 13y (t≈2.4–2.7) but **evaporates on 23 years** — the 13-year result was sample-specific |

**Nothing clears the pre-registered bar** (|t|>3 on independent clusters, same sign
out of sample, positive after cost), and the one thread that came closest —
short-term reversal — dissolved when the sample was extended to 23 years. On the
evidence available, **price history alone does not contain an edge, for this
instrument set, at these costs.**

The one result that is not ambiguous is the cost structure: the account pays
1.6–2.25 pips per round trip, and the measurable patterns are worth a fraction of
that. Any strategy that trades frequently on this account is donating the spread,
which is precisely what the live variant has been doing.

## 6. Next steps, in order of expected value

Items 1 and 2 from the previous list are now done and are reported above. What
remains:

1. **Re-examine the cost assumption, because it decides everything.** The spreads
   measured here (1.6–2.25 pips round trip) are retail quotes with a markup.
   The one genuinely real effect found — mean reversion after a 2σ stretch, t=5.7,
   positive on 100% of pairs — is worth +0.52 pips. It is unprofitable at 1.6 pips
   and profitable at institutional costs (~0.2–0.3 pips). So the honest question
   for the account is not "which pattern" but "what spread can this account
   actually achieve", and the answer determines whether the real edge is
   reachable at all.
2. **Positioning data.** Speculative positioning (COT reports) is the one major
   input not yet in the panel, and it is genuinely orthogonal to price history.
   It is public, weekly, and goes back decades.
3. **Accept the cost conclusion for the current bot.** With a 1.6–2.25 pip round
   trip and patterns worth a fraction of a pip, no entry parameter can fix the
   live variant. Either trade a horizon where the move dwarfs the cost, or stop
   trading this instrument on this account.
4. **Do not tune the current variants further.** Entry parameters cannot create an
   edge larger than the spread that the data does not contain.
