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

## The rule tested

The most-documented systematic strategy in existence: hold markets that have risen
over the past 12 months, stand aside from (or short) those that have fallen, size
each position to a volatility target, rebalance monthly, spread across many
markets. Canonical parameters — 250-day lookback, 21-day rebalance, 10% volatility
target — chosen from the literature before any results were seen.

## Results

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

## Verdict

**This is not a fix for the current bot.** It requires a multi-asset, low-cost,
margin-capable account. The bot trades 26 FX pairs on a retail spot account where
the spread is flat all day and equal to the average daily move, and no
configuration of any tested signal overcame that.

What the evidence now supports, after three rounds and roughly forty tested rules:

1. Foreign exchange spot, at retail cost, contains no edge this harness can find —
   in price history, in interest-rate carry, or in speculative positioning.
2. Systematic trend following across a diversified basket does improve risk-adjusted
   returns out of sample, mainly by halving drawdowns, but its added return does not
   clear the statistical bar on forty years of data.
3. Therefore the honest answer to "make the bot win" is not a better signal. It is a
   different instrument universe and a different objective — a portfolio that
   compounds with smaller drawdowns, rather than a bot that wins individual trades.

Next, if pursued: extend the multi-asset sample backwards (S&P from 1927 is
available) and add markets, to give the paired difference enough power to be
judged properly rather than merely noted.
