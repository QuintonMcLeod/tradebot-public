# Platform interference with a validated rule

Three platform behaviours were found to be rewriting a rule that had already been
validated on three years of data. Each was measured, each is now bypassable by a
strategy that declares it owns its own risk, and this document records what they
were doing and what they cost.

## 1. Stops were being ignored for the first 45 minutes

The replay and live paper brokers suppress a mechanical stop when the position is
young and underwater: `negative_hold_seconds = 2700`. The intent is anti-churn —
do not let noise take you out seconds after entry. For a rule validated with an
exact 20-pip stop it is disastrous on the tail, because the position is not
protected at all during that window.

Measured over 12 months across 15 pairs, most stop-outs landed at −1.1R as
intended, but five did not:

| pair | intended risk | actual loss | R |
|---|---|---|---|
| EURAUD | ~$57 | −$315.02 | **−5.53** |
| CADJPY | ~$57 | −$192.65 | −3.38 |
| CADJPY | ~$57 | −$171.09 | −3.00 |
| AUDJPY | ~$57 | −$161.87 | −2.84 |
| CADJPY | ~$57 | −$157.47 | −2.76 |

All five show `mfe_r = 0.00` — they never went favourable, the stop was passed, and
the position kept running for another 40 to 90 pips. In several cases the entry and
stop were exactly 20 pips apart, so the risk was defined correctly and simply not
enforced.

**Fix:** a position created with `self_managed_risk = True` has the negative-hold
guard disabled, so its stop is honoured from the first tick.

## 2. The Day Enforcer closed 48% of the trades

`SafetyGuard.augment_exit_decision` runs a guard that takes profit after roughly
1.4–1.9 hours in the green, tightens stops, and force-closes losers
("Emergency"). Over the same 12 months it closed **936 of 1,948 trades**:

| exit | n | net |
|---|---|---|
| rule's own exits (target, stop, time stop) | 1,012 | **+$7,075** |
| Day Enforcer guards | 936 | **−$1,377** |

It is not part of the validated rule, and it was a net drag of $1,377 against a
rule that made $7,075 with its own exits.

**Fix:** a `self_managed_risk` position returns from the guard untouched.

## 3. One spread figure for every pair

The paper broker's friction came from a single configured number (1 bp spread plus
0.5 bp slippage), while measured round trips run from **1.12 bps** on USDJPY to
**2.53 bps** on NZDUSD. Since this rule trades the crosses — CHFJPY, GBPCHF, EURAUD
— a uniform figure flatters the result by up to a factor of two on the pairs that
matter most.

**Fix:** `measured_spreads.json` is generated from quoted candle data and the broker
prices each fill with the spread measured for that pair. Without the file the
configured value is used unchanged, so live behaviour is unaffected until the table
is generated.

## What this says about the platform

None of these three are bugs in isolation; each is a sensible default for a strategy
whose exits are unproven. Together they meant the engine was running a *different
rule* from the one that had been validated: a wider stop in the first 45 minutes, a
forced exit at 1.4 hours, and a cost model that undercharged the crosses.

The pattern worth remembering: measurement in research is not evidence about the
engine, and equivalence between the two has to be demonstrated rather than assumed.
The cadence fault in `tools/paper_replay.py` was the same lesson in a different
place — a day-per-record store made the replay advance one tick per day, so it had
been evaluating stops against daily ranges and reporting 6 trades where the rule
generates about 100 per pair per year.
