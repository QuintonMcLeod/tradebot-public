# Final verdict: the edge search

Research programme covering foreign exchange spot, interest-rate carry, speculative
positioning, execution mechanics and multi-asset trend following. Roughly fifty
rules tested against up to a century of data, with cost accounting, clustered
inference, era splits and a pre-registered significance bar.

**Verdict: no validated edge was found. Nothing was shipped, because nothing
survived out of sample.** This document states what was done, what was found, and
what would have to change for the answer to be different.

---

## 1. What was asked, and what was built

| deliverable | status |
|---|---|
| 12+ months of OANDA candle history | 12 months of M5 across 26 pairs with the spread quoted on every candle (237 MB); 23 years of daily (17 MB) |
| Walk-forward harness with multiple-testing control | `edge_research.py`, `edge_daily.py`, `edge_reach.py`, `edge_flow.py`, `edge_tsmom.py` — temporal clustering, era splits, family-wise bars, non-overlapping sampling |
| Classic and human-style FX hypotheses on held-out data | trend, momentum, cross-sectional momentum, carry, reversal, calendar, session, levels, payoff asymmetry, positioning, execution |
| Ship only what survives out of sample | nothing survived; the two unproven additions made earlier in the programme (an MFE floor lock and a stop cap) were measured, found harmful, and deleted |
| Documented, honest verdict | three research documents, all deployed |

Additional data acquired for the programme: 23 years of daily FX, 20 years of CFTC
positioning, 20 years of short-term interest rates, and 100 years of multi-asset
daily bars across 34 markets.

## 2. The complete rule inventory

| hypothesis | data | result |
|---|---|---|
| Intraday mean reversion (fade a 2σ stretch) | 26 pairs × 12m M5, 257k events | **real** (+0.25 to +0.52 pips, t 3.4–5.7, positive on 89–100% of pairs, stable across halves) but 3–6× smaller than the spread |
| Mean reversion conditioned on strength, session, volatility | 86 cells, per-pair matched costs | best cell −0.45 pips net; 0 of 26 pairs positive at 3σ/1h; gross edge tracks the spread (ratio 0.1–0.5) |
| Trend following / momentum | 26 pairs × 13y daily, 4h | **negative** (−5 to −7 bps per period, t −2.5 to −6.9), both halves |
| Cross-sectional momentum | same | **negative** |
| Carry, with real OECD rates | 26 pairs × 13y | flat (+2.5 bps/mo, t=0.21); quintile ladder non-monotonic; spot leg negative, accrual merely offsets |
| Short-term reversal | 13y, then 23y | +2.2 to +3.2%/yr on 13 years (t≈2.4), **evaporates on 23 years** |
| Calendar (weekday, turn-of-month, month) | 13y daily, ~676 obs per weekday | all negative once the round trip is charged |
| Session effects | 12m M5 | real but 0.07–0.36 pips against a 1.6-pip spread, and the spread is flat all day |
| Level effects (round numbers, prior-day extremes) | 12m M5 | insignificant |
| Payoff asymmetry ("let winners run") | 12m M5 hourly | **none** — gross forward move is zero in every bucket of unrealised profit |
| Maker entry instead of taker | 6 limit offsets | adverse selection eats 94% of the price improvement; still negative |
| Speculative positioning (CFTC) | 20 years, 8 currencies, 54 cells | right sign (fade the crowd +2%/yr, follow it −2%) but t 1.0–1.3; not established |
| Multi-asset trend following | 14 markets, then 34, 1986–2026 | promising on the narrow basket (Sharpe 0.89/0.82 vs 0.67/0.43), **collapses to a tie on the wider one** (0.52 vs 0.52); paired difference +1.3–1.6%/yr, t 1.1–1.3 |

## 3. The live bot corroborates the finding

The paper account's own record, 101 closed trades:

| measure | value |
|---|---|
| net P&L | **−$692.55** |
| the bot's own estimated round-trip friction | $750.51 |
| **pre-friction P&L** | **+$57.95** |
| win rate | 17.8% (18W / 83L) |
| profit factor | 0.24 |
| median holding time | **12 minutes** |

Read the first three rows together. The modelled friction is **108% of the entire
net loss**. Before costs the bot was essentially flat — it had no edge to lose, and
it paid about $7.43 per trade on average to discover that. A median hold of twelve
minutes is the worst possible structure for this: the average twelve-minute move is
a fraction of a pip while the round trip costs 1.6–2.5.

This is the research conclusion reproduced on live data, from the inside.

## 4. Why: the arithmetic

The account pays 1.6–2.5 pips per round trip, flat across every session (only the
21:00–23:00 rollover widens). The one effect that is unambiguously real — fading a
2σ stretch, t=5.7, positive on 100% of pairs — is worth 0.25–0.52 pips at the
horizons the bot trades. **The toll is three to six times the edge.**

At longer horizons the move grows and the toll does not, which is the one
constructive result: a 4σ stretch over a day is worth ~13 pips gross against a
1.6-pip cost. But those events are rare (98 independent observations in 26 pairs
over 12 months), and when the sample was widened the edge did not hold.

## 5. The methodological finding, which may be the most useful output

Every single candidate in this programme looked real on the sample that suggested
it, and dissolved on a wider one:

- short-term reversal: convincing on 13 years, gone on 23
- the 4σ fade: +13.8 pips, then not significant once clustered properly
- multi-asset trend: Sharpe 0.89/0.82 on 14 markets, 0.52 vs 0.52 on 34
- my own two "fixes" (MFE floor lock, stop cap): both measured worse and were deleted

Two of the near-misses reached t≈2.4 on hundreds of observations. Had the bar been
"t>2 on the data I happen to have", both would have been shipped and both would have
lost money. The multiple-testing bar is not bureaucracy; it is the whole difference
between a strategy and a story.

## 6. What would change the answer

1. **A cheaper venue.** The gap is mostly absent edge, not cost — a lower spread
   closes only a fraction of it — but at 0.1–0.3 pips round trip the measured
   intraday effects on the tightest pairs move from clearly negative to marginally
   positive. This is the only route by which the one real effect becomes tradable,
   and it requires an institutional or raw-spread account, not a retail one.
2. **A different objective.** Accept market returns, minimise turnover and cost, and
   manage drawdown. Every attempt to add return beyond that, tested here, failed to
   survive out of sample.
3. **More data for the rare-event effects**, if anyone wants to pursue the 4σ
   reversal or positioning seriously. Both need several hundred independent events,
   not the 50–100 available.

## 7. Recommendation for the running bot

The live configuration trades a twelve-minute median hold on an account whose round
trip costs 1.6–2.5 pips, with no measured edge. On this evidence it should not be
pointed at real money, and it will continue to bleed the spread on paper at roughly
the observed rate. Either it moves to a materially cheaper venue and a horizon where
the move can exceed the toll, or it stops.
