# Multi-asset test — is it foreign exchange, or systematic trading?

Follow-up to `EDGE_SEARCH_2026_09.md`. That study ended on a structural point
rather than a signal: on the bot's account the round trip costs about as much as
the average daily move, and nothing in the tested families beat it. The open
question was whether that is a fact about foreign exchange or about systematic
trading in general.

So the same harness was pointed at markets with a century of documented risk
premia: equity indices, commodities, bonds, and the dollar index.

Tooling: `tools/fetch_multi.py` (14 markets, daily bars from 1986 for the indices),
`tools/edge_tsmom.py` (volatility-targeted time-series momentum with a buy-and-hold
benchmark).

---

> **Consolidated verdict:** the conclusions of this document, together with the
> live account's own record, are summarised in
> [`FINAL_VERDICT_2026_09.md`](FINAL_VERDICT_2026_09.md).


## The rule tested

The most-documented systematic strategy in existence: hold markets that have risen
over the past 12 months, stand aside from (or short) those that have fallen, size
each position to a volatility target, rebalance monthly, spread across many
markets. Canonical parameters — 250-day lookback, 21-day rebalance, 10% volatility
target — chosen from the literature before any results were seen.

## Results (14-market basket — superseded below)

**Superseded:** the test was later repeated on 34 markets and the advantage largely
disappeared. Read the "Round two of this test" section before drawing conclusions
from the tables in this section.

14 markets, 1986–2026, 5 basis points cost per unit turnover, sample split in half
so the second half is genuinely out of sample.

| strategy | era | CAGR | vol | Sharpe | max DD | t (monthly) |
|---|---|---|---|---|---|---|
| trend long-only | 1986–2006 | 10.4% | 11.8% | **0.89** | **−24.3%** | 3.65 |
| trend long-only | 2006–2026 | 9.7% | 12.3% | **0.82** | **−19.7%** | 3.92 |
| trend long/short | 1986–2006 | 8.8% | 12.7% | 0.73 | −31.0% | 3.01 |
| trend long/short | 2006–2026 | 5.7% | 12.8% | 0.50 | −31.4% | 2.27 |
| buy and hold | 1986–2006 | 7.1% | 11.1% | 0.67 | −45.7% | 2.78 |
| buy and hold | 2006–2026 | 4.5% | 11.9% | 0.43 | −37.6% | 2.06 |
| reversal (control) | both halves | negative | — | −0.80 / −0.59 | −90% | −3.2 / −2.7 |

Three things to note. The trend overlay beats buy-and-hold on Sharpe in **both**
twenty-year halves. It does so at essentially the same volatility, so this is not
merely owning less risk. And the drawdown is roughly **halved**. The reversal
control is solidly negative, confirming the sign matters rather than the machinery.

## The test that matters, and it does not pass

The strategy's own return series is significant. That is not the same as the
*overlay* adding value, because buy-and-hold also made money. The honest test is the
paired difference between the two, month by month:

| era | strategy | benchmark | difference | t (difference) |
|---|---|---|---|---|
| 1986–2006 | 10.4% | 7.1% | +3.2%/yr | **1.54** |
| 2006–2026 | 9.7% | 4.5% | +5.0%/yr | **1.96** |
| full sample | — | — | +2.7%/yr | 1.77 |

Positive in both halves, larger in the recent one, and **short of the |t|>3 bar**.
By the standard applied to every other candidate in this investigation, this one is
not established either.

## Why it is nonetheless the most credible thing found

Everything else in this study was noise; this has a mechanism and it matches a
century of published results. Trend following's documented value is not extra
return — it is **avoiding the worst of the declines**. That is exactly the pattern
here: the added return is modest and statistically soft, while the drawdown
reduction is large, consistent, and structural (being flat during a downtrend
cannot lose money in that downtrend). The +2.7%/yr is a by-product; the halved
drawdown is the product.

## Robustness checks

| check | result |
|---|---|
| Parameter grid (lookback 60/120/250 × rebalance 5/21/63) | long-only Sharpe 0.38–1.04, positive in all nine cells, no knife-edge |
| Cost sensitivity | survives to 20 bps turnover (long/short Sharpe 0.56 → 0.41) |
| Futures roll artifact ruled out | excluding all futures: long-only Sharpe 0.83 / 0.76, t 3.36 / 3.77 |
| Equity premium alone? | equities-only is weaker (0.88 then 0.60, drawdown −40%), so diversification across bonds, gold and the dollar is doing work |
| Non-overlapping significance | t computed on 21-day periods, not daily returns (233–248 independent periods per half) |
| Leverage | average gross exposure 1.3–1.6×, capped at 2× |

## Round two of this test: the result does not survive a broader basket

The table above was produced on a 14-market basket. That basket was itself a choice,
and choices of that kind are exactly what this investigation has been punishing
elsewhere, so the test was repeated on 34 markets — adding the Dow, Russell, CAC,
Euro Stoxx, Hang Seng, ASX, TSX, two more Treasury contracts, two bond ETFs,
platinum, natural gas, corn, wheat, sugar, coffee, three FX pairs and bitcoin. The
S&P series now reaches back to 1927.

The advantage largely disappears.

| strategy | era | CAGR | Sharpe | max DD | benchmark Sharpe | benchmark DD |
|---|---|---|---|---|---|---|
| trend long-only | 1986–2006 | 7.1% | 0.59 | −42.7% | 0.54 | −27.0% |
| trend long-only | 2006–2026 | 6.7% | 0.78 | −42.7% | 0.75 | −73.6% |
| trend long/short | 1986–2006 | 4.7% | 0.44 | −44.6% | 0.54 | −27.0% |
| trend long/short | 2006–2026 | 6.9% | 0.69 | −38.9% | 0.75 | −73.6% |

Long-only now merely matches the benchmark on Sharpe (0.59 vs 0.54, then 0.78 vs
0.75). Long/short is **worse** than the benchmark in the first half and worse in the
second. The drawdown advantage also shrinks to nothing in the first half (−42.7%
against the benchmark's −27.0%).

Measured the same way across four different baskets, the paired difference is
consistent in sign but never close to significant:

| basket | long-only Sharpe | benchmark | difference | t (difference) |
|---|---|---|---|---|
| all 34 markets | 0.52 | 0.52 | +1.4%/yr | 1.22 |
| excluding bitcoin | 0.49 | 0.46 | +1.5%/yr | 1.30 |
| excluding crypto and the FX legs | 0.54 | 0.51 | +1.6%/yr | 1.34 |
| the 14-market basket above | 0.59 | 0.54 | +1.3%/yr | 1.11 |

Long/short is negative on every basket (−1.1% to −1.4%/yr, t ≈ −0.7 to −0.8).

Costs also bite much harder once the universe widens: 34 markets means more
positions to turn over, and the long/short Sharpe falls from 0.36 at zero cost to
0.28 at 5 bps and 0.06 at 20 bps, against 0.52 at 5 bps on the narrower basket.

**Correction to the section above.** The +2.7%/yr with t=1.77 reported earlier was
measured on the 14-market basket over a particular effective date window. Computed
consistently across baskets and windows, the advantage is +1.3% to +1.6%/yr with t
between 1.1 and 1.3, and the Sharpe advantage is between nothing and +0.05. The
earlier figure was an artifact of the choice of universe, which is the same failure
mode this study has documented in every other candidate.

## Verdict

**Nothing here is a fix for the current bot, and the multi-asset trend lead does not
survive scrutiny either.** Trend following across a diversified basket does not
deliver a statistically established improvement over simply owning the basket. What
it reliably does is change the shape of the ride — on the wide basket it halved the
drawdown in the second half (−38.9% against −73.6%) — which is a risk-preference
choice, not an edge, and it costs turnover to maintain.

Across three rounds and roughly fifty tested rules, the evidence says:

1. Foreign exchange spot, at retail cost, contains no edge this harness can find —
   not in price history, not in interest-rate carry, not in speculative positioning.
2. Multi-asset trend following does not beat buy-and-hold by a margin that survives
   changes of basket, era, or cost assumption.
3. The recurring pattern is that every candidate looks real on the sample that
   suggested it and dissolves on a wider one. That is the single most important
   result of this work, and it is the reason the bar was set where it was.

If there is an honest path to a bot that wins, it is not a better pattern. It is a
different objective: accept market returns, minimise cost and turnover, and manage
drawdown — because every attempt to add return beyond that, tested here, has failed
to survive out of sample.

