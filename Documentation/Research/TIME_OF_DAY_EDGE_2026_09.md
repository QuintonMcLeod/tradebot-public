# The time-of-day edge — the first result that survives

This document records the first configuration in the entire programme that is
positive after real costs, reproduces on data that was never examined, and has a
mechanism. It came from the operator's coaching, not from the machine's search, and
the credit belongs there.

The coaching, and what the data said to each part:

| claim | verdict |
|---|---|
| "Oanda widens spreads at certain times, around 5-6pm — their way of telling you not to trade" | **confirmed, exactly.** Spread goes 1.60 → **4.30 pips at 21:00 UTC (17:00 ET)** |
| "You are not correlating WHEN the wins and losses are" | **confirmed, and it is the whole finding.** The edge ramps from ~0 in Asia to +2.5 in the NY afternoon |
| "Follow price action; indicators lag" | **confirmed at the working window** — price-action entry beats the indicator 3× there (+0.91 vs +0.28) |
| "Set your SL early, usually around break even" | **contradicted.** It halves the win rate and turns gross expectancy negative |
| "Scrap in all sessions, not just London/NY" | **refined.** The edge is *not* in all sessions — it is concentrated in the last hours of New York |

---

## 1. When the wins and losses are (claim 2)

Fade entry, all 24 hours, gross expectancy per trade:

| UTC | ET | gross pips |
|---|---|---|
| 00–09 | 20:00–05:00 | −0.54 to +0.29 (Asia: nothing) |
| 10–16 | 06:00–12:00 | −0.10 to +1.22 |
| 17–19 | 13:00–15:00 | +0.89 to +1.49 |
| **20** | **16:00** | **+1.81 to +2.51** |
| **21** | **17:00** | **+2.81 to +4.34** |

A monotone ramp through the day. The swing from the worst hour to the best is about
**3.7 pips — larger than the entire spread.** This is the single biggest effect
found anywhere in this programme, and it was invisible to every earlier test because
they pooled all hours together.

## 2. The rollover trap (claim 1)

The hour with the largest gross edge is also the hour with the largest markup:

| hour | gross edge | OANDA spread | net |
|---|---|---|---|
| 20:00 UTC (16:00 ET) | +2.51 | 1.60–2.20 | **+0.3 to +0.9** |
| 21:00 UTC (17:00 ET) | **+4.34** | **4.30** | **+0.04** |

The broker's spread at 5pm New York takes back almost precisely the whole of the
best edge in the day. The operator's reading of that spread widening — "their way of
telling you do not trade during this time" — is as close to literally true as a
market statement gets.

## 3. The configurable part (claims 4 and the geometry)

Entry style at the working window, everything else equal:

| entry | gross | net @1.6 | pairs + |
|---|---|---|---|
| **price action: fade a 20-bar range break** | **+2.51** | **+0.91** | 12/15 |
| price action: 3 consecutive closes | +0.29 | — | — |
| price action: prior-day extreme | +0.21 | — | — |
| **indicator: SMA z-score** | +1.88 | +0.28 | 7/15 |

Price action beats the lagging indicator at the window that matters, which is the
operator's point. Geometry is robust rather than knife-edge — every one of six
target/stop combinations was positive over three years (net +0.41 to +0.87 at flat
1.6-pip cost, t from 2.9 to 7.8).

## 4. The break-even stop, contradicted (claim 3)

Tested fairly, with a target that leaves room for the stop to matter:

| geometry | TP-win | gross |
|---|---|---|
| TP20/SL20, no break-even stop | 23% | **+0.309** |
| TP20/SL20, stop to break-even at +5 | **8%** | **−0.871** |
| TP20/SL20, stop to break-even at +10 | 16% | −0.282 |
| TP10/SL20, no break-even stop | 49% | **+0.378** |
| TP10/SL20, stop to break-even at +5 | **23%** | **−0.808** |

Moving the stop early halves the win rate and destroys the expectancy. The
mechanism is not subtle: in a whipsawing market the break-even level sits exactly
where price returns on its way to the target, so the trades that would have won are
scratched out at zero while the ones that go straight to the stop still lose in
full. You keep every loss and surrender the winners.

## 5. The honest number, and the out-of-sample test

The flat-cost figures above charge every pair 1.6 pips, which undercharges the
crosses that carry most of the edge. Charging each pair its own measured spread cuts
the result roughly in half:

| group | gross | **net at own spread** | t | pairs + |
|---|---|---|---|---|
| all 15 pairs | +2.47 | **+0.32** | 4.17 | 7/15 |
| majors (1.3–1.9 pip spreads) | +1.65 | +0.01 | 2.80 | 2/6 |
| crosses (2.1–4.1 pip spreads) | +3.10 | +0.51 | 5.36 | 4/8 |

And on 24 months of data that had **never been examined** before this session:

| period | gross | net | t | pairs + |
|---|---|---|---|---|
| **holdout 2023-09 → 2025-09** | +2.45 | **+0.41** | **3.42** | 9/15 |
| fitted 2025-09 → 2026-09 | +2.51 | +0.22 | 2.68 | 10/15 |
| year to 2024-09 | +2.01 | +0.12 | 1.81 | 7/15 |
| year to 2025-09 | +2.77 | +0.59 | 2.66 | 11/15 |
| year to 2026-09 | +2.57 | +0.28 | 2.94 | 10/15 |

**Positive in the holdout, positive in the fitted year, and positive in all three
individual years.** The holdout was not merely the same sign — it was the same
magnitude at slightly better significance than the sample the rule was chosen on.

## 6. What the rule actually is, and what it is worth

**Trade 20:00–21:00 UTC only (16:00–17:00 New York). Fade a break of the prior
20-bar range — pure price action, no indicators. Target ~10 pips, stop ~20 pips,
maximum hold four hours. Avoid the 21:00 hour entirely, where the broker's spread
takes the whole edge.**

Expectancy: **+0.3 pips per trade net** at this account's real spreads, but only on
pairs whose round trip is below about 2.5 pips (break-even sits at ~2.5; at a 1.0-pip
venue the same rule earns +1.47 with t=10). On the tight majors alone it is worth
approximately nothing (+0.01), because their gross edge is small. The value is in
the crosses with moderate spreads, and in cheap execution.

## 7. Caveats, stated plainly

- The rule was chosen by looking at 12 months, across a large space (24 hours × 5
  entries × 12 geometries). The holdout reproduction is therefore the strongest
  evidence here, but the search itself means the true significance is lower than
  t=3.42 suggests.
- Three years is one regime. EURUSD spent it in a range; a sustained trending regime
  could behave differently.
- +0.3 pips per trade is small. In R terms it is about 0.016R, so this is not a
  money printer — it is a modest, real, repeatable edge that requires cheap
  execution and volume to matter.
- It is untested in the live engine. The simulation charges the measured spread and
  assumes fills at the bar close, which is optimistic for a stop-driven rule.

**This supersedes the negative verdict** in `FINAL_VERDICT_2026_09.md` as it applies
to intraday FX. That verdict was correct for every rule tested there — but every one
of those rules pooled the trading day, and the effect they missed is a function of
the hour.
