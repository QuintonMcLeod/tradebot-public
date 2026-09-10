# The scrape hypothesis, tested

Put forward by the operator, not by me: *foreign exchange does not trend, it
whipsaws; trend rules are the wrong tool; the way to win is to scrape — many small
takes, in all sessions, not just London and New York.*

This is a falsifiable claim about market structure and trade geometry, and it is
the first hypothesis in this programme that was **not** proposed by the machine. It
deserves a direct test rather than a dismissal, and it gets one here.

Tool: `tools/edge_scrape.py`.

---

## What was tested

The claim is about *brackets*, and none of the earlier work tested brackets. Every
prior measurement was a forward return over a fixed horizon, which is a different
object from "enter, take a few pips if they come, give back more if they do not".

So the bracket was simulated directly across all 15 pairs and **all 24 hours**:

- enter at the close of a bar, take profit T pips away, stop loss S pips away;
- whichever level is reached first decides the trade; if neither is reached inside
  the holding window, exit at the market;
- charge each pair's measured round-trip spread to every trade, win or lose;
- **if one bar touches both levels, the stop wins** — optimistic tie-breaking is how
  a backtest invents a scraper that does not exist;
- entries sampled every `hold` bars so forward windows never overlap;
- inference clustered in time, across 2.2 million simulated brackets per grid.

## Part 1: the geometry does not matter, and this is the whole point

Direction-less brackets — no view, just enter and manage — holding up to 48 bars:

| TP | SL | TP hit rate | avg win | avg loss | **gross pips** | net after cost |
|---|---|---|---|---|---|---|
| 2 | 20 | **88%** | +2.0 | −13.6 | **+0.07** | −2.19 |
| 3 | 20 | 75% | +3.0 | −8.9 | **+0.03** | −2.23 |
| 5 | 20 | 70% | +5.0 | −11.4 | **+0.09** | −2.13 |
| 5 | 10 | 62% | +5.0 | −8.2 | **+0.04** | −2.22 |
| 8 | 15 | 53% | +8.0 | −8.8 | **+0.08** | −2.19 |

Read the win rate column against the gross column. **The win rate can be dialled to
88%, and gross expectancy stays at zero.** The 12% of trades that lose hand back
13.6 pips each and cancel the 88% that take 2.0. That is the arithmetic identity of
a bracket on a near-random walk: any take-profit and stop-loss pair is expectancy
neutral before costs. Net is then simply minus the spread, and **0 of 15 pairs were
positive in every one of the 48 geometries tested.**

This is why "small takes, high win rate" cannot work by itself. A high win rate is
not an edge; it is a *shape*, and the shape is symmetric by construction.

## Part 2: the underlying idea is right — fading is the correct family

The claim also says the market whipsaws, which is a directional statement, and here
the operator is correct. Fading a stretch rather than entering blind, with the same
bracket machinery:

| TP | SL | TP hit rate | **gross pips** | t | pairs positive |
|---|---|---|---|---|---|
| 5 | 20 | 71% | **+0.24** | **5.56** | **15/15** |
| 5 | 15 | 69% | +0.24 | 6.42 | 14/15 |
| 8 | 15 | 54% | +0.23 | 5.34 | 15/15 |
| 3 | 20 | 82% | +0.19 | 5.90 | 15/15 |
| 3 | 15 | 80% | +0.18 | 6.59 | 14/15 |

Fading turns a zero into **+0.24 pips per trade, t=5.56, positive on all 15 pairs**.
That is a real effect, and it is consistent with every earlier result in this
programme: momentum and trend were negative, mean reversion was positive.

So the operator's diagnosis is **confirmed**: foreign exchange whipsaws, trend rules
lose, and fading is the right side. The friction is not the concept.

## Part 3: the friction is the magnitude

| round-trip cost | net pips per trade | t | pairs positive |
|---|---|---|---|
| ~2.2 pips (this account, measured) | **−2.02** | −41 | 0/15 |
| 1.0 pip | −0.76 | — | — |
| 0.5 pip | −0.26 | — | — |
| **0.24 pips (break-even)** | 0.00 | — | — |
| 0.2 pips (institutional) | **+0.04** | 1.42 | 11/15 |

The break-even cost is **0.24 pips**. The account charges roughly 2.2. That is a
gap of about nine times, and it is why 2.2 million simulated scraps lose 2 pips
each regardless of how the bracket is set.

Even at a hypothetical 0.2-pip institutional venue, the residual is +0.04 pips per
trade with t=1.42 — inside the noise, and short of the bar applied to every other
candidate here. A cheaper venue is necessary but not sufficient.

## Verdict

**The concept is right; the magnitude is not there.**

1. Foreign exchange whipsaws rather than trends — confirmed on 13 years, 23 years,
   and in this bracket test. Trend rules lose. The operator is right and the
   machine's earlier tests agree.
2. Scraping is the correct *family*: fading a stretch with a small take-profit
   produces a real, broad edge (t=5.56, 15 of 15 pairs).
3. Scraping is not the correct *magnitude*: the edge is 0.24 pips gross, and the
   account charges ~2.2 pips to cross. Nine times too expensive.
4. The win rate is a red herring in both directions. It can be pushed to 88% with
   zero expectancy, and the best gross edge here comes from a 71% win rate, not the
   82% one.

What would have to change for scraping to pay: either a venue at or below roughly
0.2 pips round trip **and** an entry better than the 1σ fade tested here, or a
larger gross edge per trade. The bracket itself cannot supply it — only the entry
can, and every entry tested in this programme has been worth less than a pip.
