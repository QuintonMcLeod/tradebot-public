# Bracket economics of the deployed scrape fade

Date: 2026-10-10
Author: measurement pass requested by the user. No bot source, bot config, service or
order was touched. Analysis scripts are new files under `scratch/`. Findings live
here.

## Verdict

**The bracket is not the disease; it is the scoreboard. The disease, in the deployed
configuration, is the toll.** Every cell of the grid was measured with each trade
charged the spread quoted at its own entry bar, and no flat cost anywhere. The
deployed 15 target / 20 stop bracket at a 24 hour hold, on the whole event pool,
returns **+0.62 pips per trade over 1,984 trades (t = +1.69, clustered t = +1.18) on
15 pairs over 3 years**, and **-0.20 pips per trade over 1,029 trades from 26 pairs
over the last 12 months**, which is the independent confirmation set. On that grid,
as deployed, **no cell clears the pre-registered |t| > 3 bar**, before or after
clustering; the largest plain t is +2.58 (15/20 at a 48 hour hold, 1,643 trades,
+1.04 pips) with a clustered t of +1.87.

**One variant does clear it, and it is the only thing in this study that does: refuse
the trade when the quote at its own entry bar is wider than 1.9 pips.** Charged the
same way, that gate measures **+2.32 pips per trade at t = +3.80 (clustered t =
+3.12) over 703 trades on 15 pairs at the deployed 24 hour hold**, and **+3.01 pips at
t = +4.62 (clustered t = +3.72) over 604 trades at a 48 hour hold**, positive in both
halves of the three year sample. The mechanism is arithmetic, not a better signal:
the gate barely changes the hit rate (67.2 percent ungated to 67.7 percent gated at
24 hours) and cuts the mean charged cost from 3.02 to 1.62 pips. The deployed rule
already contains such a ceiling and it is set to 1.9 pips, but it is tested against a
one number per pair table rather than against the trade's own quote, so it does not
actually bind on the trades that pay the wide spreads. See the gate addendum below
for why this is a candidate and not a settled edge, including its weakness on the
independent 26 pair set.

Raising the target relative to the stop does **not** move the net per trade up: on the
whole pool at a 24 hour hold the net goes +0.62 at 15/20, +0.48 at 20/20, +0.20 at
30/20, +0.43 at 40/20, +1.11 at 60/32, +0.64 at 55/30, which is noise about a small
positive mean, not a trend. The deployed bracket's shortfall is the size of the toll
relative to the hit rate, not the width of the target or the stop: at the deployed
settings the signal wins 67.2 percent of trades and needs 65.8 percent to break even,
a margin of +1.4 percentage points, and on the independent 12 month set it wins 69.9
percent and needs 71.0 percent, a margin of -1.1 points.

## What was measured, and how each number was produced

Runs behind every figure in this document:

| file | what it produced |
|---|---|
| `scratch/bracket_economics_grid.py` | event builders (`build_paths`) and the first grid pass |
| `scratch/bracket_economics_final.py` | the corrected grid, run as `python3 scratch/bracket_economics_final.py` and written to `scratch/bracket_economics_final.json` |
| `scratch/bracket_economics_table.py` | run as `python3 scratch/bracket_economics_table.py`, wrote `scratch/bracket_economics_table.json` and printed `scratch/bracket_table.out`, which is the source of both grid tables below |
| `scratch/bracket_economics_clustered_t.py` | `scratch/bracket_clustered.out`, the calendar day clustered t column |
| `scratch/bracket_economics_randomwalk.py` | `scratch/bracket_rw.out`, the driftless and Monte Carlo hit rates |
| `scratch/bracket_economics_hold_and_rw.py` | `scratch/bracket_hold_rw.out`, the same pool read at three holds |
| `scratch/bracket_economics_open_adjusted.py` | `scratch/bracket_adj.out`, the open adjusted hurdle discussion |
| `scratch/bracket_economics_pathcheck.py` | `scratch/bracket_pathcheck.out`, the event definition and path convention check |
| `scratch/bracket_economics_diag.py` | `scratch/bracket_diag.out`, the pool identity check against the published harness |
| `scratch/bracket_economics_crosscheck.py` | independent second event builder |
| `scratch/bracket_economics_groups.py` | `scratch/bracket_groups.out`, the win, loss and open group decomposition |
| `scratch/bracket_economics_gate.py` | `scratch/bracket_gate.out`, the own quote gate variant, run as `python3 scratch/bracket_economics_gate.py` |
| `scratch/bracket_economics_gate_stats.py` | `scratch/bracket_gate_stats.out`, the gate's split half and clustered statistics, run as `python3 scratch/bracket_economics_gate_stats.py` |

Script revisions used for the numbers in this document, first 12 hex characters of
`sha256sum`:

| file | hash |
|---|---|
| `scratch/bracket_economics_grid.py` | 7edd93fb0f59 |
| `scratch/bracket_economics_final.py` | 4d8994cb7dae |
| `scratch/bracket_economics_table.py` | cf8d4811cf98 |
| `scratch/bracket_economics_clustered_t.py` | 21fd9f06b4ba |
| `scratch/bracket_economics_randomwalk.py` | dc4a42a655f4 |
| `scratch/bracket_economics_hold_and_rw.py` | 8f8bf6d4c9e2 |
| `scratch/bracket_economics_open_adjusted.py` | 8e413074a79d |
| `scratch/bracket_economics_groups.py` | de5b82425392 |
| `scratch/bracket_economics_pathcheck.py` | a97d0b596df8 |
| `scratch/bracket_economics_gate.py` | f32f092deaaa |
| `scratch/bracket_economics_gate_stats.py` | ef7e36f88df1 |
| `tools/edge_cost_check.py` | 3ebe22e84cf0 |
| `tools/edge_entry.py` | 127f881ce138 |

External inputs, read only:

* Candle history: `/home/qchan/.config/tradebot-sci-gui/local/data/candle_history_36m`
  (15 pairs, 2023-09-26 to 2026-09-10, M5, 220,339 to 220,586 bars per pair) and
  `/home/qchan/.config/tradebot-sci-gui/local/data/candle_history_12m` (26 pairs,
  2025-09-15 to 2026-09-10, M5, 73,516 to 73,727 bars per pair). Enumerated by
  `python3 -c` over `edge_research.load_series`, printed in the first tool call of
  this session and reproducible with `scratch/bracket_economics_diag.py`.
* Spread guard table: `/home/qchan/.config/tradebot-sci-gui/local/data/measured_spreads.json`,
  15 entries, read by `scratch/bracket_economics_final.py`.
* Prior art read before measuring: `Documentation/Research/SCRAPE_ENTRY_2026_09_13.md`,
  `Documentation/Research/LARGE_TARGETS_2026_09_13.md`,
  `Documentation/Research/EDGE_SEARCH_2026_09.md`,
  `Documentation/Research/FINAL_VERDICT_2026_09.md`,
  `Documentation/Research/TIME_OF_DAY_EDGE_2026_09.md`.
* The realized paper record (163 closes, 13.5 percent win rate, -1,342.68 USD) was
  given in the work request and is **not** reproduced here; see the section on what
  could not be measured.

### The event definition, and proof that it is the published one

The entry is the deployed one: a fresh break of the prior 20 bar range (the close
crosses the level and the previous close was still on the other side of it), faded
immediately at that close, during the 20:00 UTC hour only, with a break depth of at
least 2.0 pips. The hour and depth filters are applied before the non-overlapping
window de-clustering, inside each symbol, which is the ordering the published
figures came from.

Two independent checks that this is the recorded rule rather than an assumption:

1. `python3 tools/edge_cost_check.py` (published tool, unmodified) prints, for the 15
   pair 3 year set at target 15 / stop 20, hold 288: `n=1984`, spread mean 3.02 and
   median 2.30, gross `+3.53`, net on each trade's own spread `+0.51`, `t=+1.38`.
2. `scratch/bracket_economics_pathcheck.py` builds the same pool from scratch and
   printed `n=1984 mean_spread=3.02 median=2.30`, with the epoch sets identical
   (`intersection=1148`, `published-only=0`, `mine-only=0`). Its deployed cell reads
   `n=1984 hit=67.24% gross=+3.53 net=+0.51 t=+1.38`, which is the published number
   exactly.

The same command printed for the 26 pair 12 month set, at target 15 / stop 20: `n=1029`,
cost 4.84, gross `+4.46`, net `-0.38`, `t=-0.73`; and at target 15 / stop 25:
gross `+4.62`, net `-0.22`, `t=-0.38`. These match
`Documentation/Research/SCRAPE_ENTRY_2026_09_13.md` and the correction block in
`src/tradebot_sci/strategy/variants/forex_scrape_fade.py` to the second decimal.

### Cost

Each trade is charged the spread quoted at its own entry bar, taken from the `sp`
field of the candle record and converted with the pair's pip size (0.01 for JPY
quotes, 0.0001 otherwise). **No flat cost is charged anywhere in the grid.** For
reference, the measured means and medians of the subsets used:

| dataset | hold pool | n | spread mean | spread median |
|---|---|---|---|---|
| `candle_history_36m` | 48 | 2187 | 2.96 | 2.30 |
| `candle_history_36m` | 288 | 1984 | 3.02 | 2.30 |
| `candle_history_36m` | 576 | 1643 | 3.01 | 2.20 |
| `candle_history_12m` | 48 | 1115 | 4.79 | 3.10 |
| `candle_history_12m` | 288 | 1029 | 4.84 | 3.10 |
| `candle_history_12m` | 576 | 870 | 4.70 | 3.00 |

Source: `scratch/bracket_table.out`, pool lines, from
`scratch/bracket_economics_table.py`. The work request quoted a portfolio median of
2.45 pips and 2.96 pips at hour 20. The 2.96 matches the measured mean of the 48 bar
pool and is close to the 3.02 mean of the 288 bar pool; the subset **medians** are
2.30 and 2.20, and they are printed only so the gap to the mean is visible. Charging
the median would flatter every trade.

Why the mean and not the median, measured rather than asserted. At the deployed
bracket, `python3 tools/edge_cost_check.py` prints that charging the 2.30 median
instead of the true 3.02 mean overstates the result by 0.72 pips per trade. This
harness reproduces the same direction on both datasets, and shows the error is not
constant with hold, so a flat sweep would also distort the hold comparison:

| dataset | hold | net, each trade's own spread | net if a flat 2.45 is charged | overstatement |
|---|---|---|---|---|
| `candle_history_36m` | 48 | -0.25 | +0.26 | +0.51 |
| `candle_history_36m` | 288 | +0.62 | +1.19 | +0.57 |
| `candle_history_36m` | 576 | +1.04 | +1.60 | +0.56 |
| `candle_history_12m` | 48 | -1.24 | +1.10 | +2.34 |
| `candle_history_12m` | 288 | -0.20 | +2.18 | +2.39 |
| `candle_history_12m` | 576 | +0.03 | +2.28 | +2.25 |

Source: `scratch/bracket_adj.out`, flat cost audit blocks, from
`scratch/bracket_economics_open_adjusted.py`. On the 26 pair set the flat charge
turns a losing rule into a strongly winning one, which is the retracted result
reproduced deliberately as an audit.

### Outcome rule, and the one structural change from the published harness

A trade is resolved by whichever barrier is touched first. When both are touched
inside one bar the stop wins, which is the conservative convention of
`tools/edge_entry.py:outcomes`. A trade that reaches **neither** barrier inside the
hold exits at the close of the last bar of the hold window, at whatever that close
is. `tools/edge_entry.py:outcomes` folds that case into the stop, because its
`fs <= ft` comparison is true when both barriers are absent. That is harmless where
almost every trade reaches a barrier and it is what the published 288 bar figures
were built on, so the deployed cell reproduces them exactly. It is not harmless at
shorter holds: at 48 bars **34.9 percent** of these trades reach neither barrier in
the 36 month pool (682 of 1984 at the 288 bar pool's own paths), and the open trades
average **-1.98 net pips**, not -20. The grid below therefore reports win, loss and
open shares separately and uses the three outcome rule. This is a correction to the
harness, and it is the reason the 48 bar row of this grid does not agree with the
`-2.03` / `-7.22` style figures produced earlier by two outcome accounting.

## Grid

De-clustering: non-overlapping windows, using a spacing equal to the hold being
measured. At the 288 bar hold that is exactly the published harness (`spacing =
horizon`) and it reproduces its figures; at 48 bars it keeps a larger sample (2,187
events) because a 48 bar hold genuinely permits trades 48 bars apart. Sample sizes
and entry days are printed for every cell.

The break-even column is the two outcome requirement
`(stop + mean cost) / (target + mean cost + stop)` computed from **that cell's own
measured mean cost**, not from a global constant. It is exact where the open share is
near zero, which is the 288 and 576 bar rows, and it is optimistic where the open
share is large, which is discussed under the open branch below.

### `candle_history_36m`, 15 pairs, 3 years

| bracket | hold bars | n | entry days | win pct | loss pct | open pct | hit pct | break-even hit pct | net pips | gross pips | mean cost pips | t | t clustered |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15/20 | 48 | 2187 | 579 | 44.5 | 20.5 | 34.9 | 44.5 | 65.6 | -0.25 | +2.71 | 2.96 | -0.83 | -0.53 |
| 20/20 | 48 | 2187 | 579 | 31.6 | 22.9 | 45.5 | 31.6 | 57.4 | -0.39 | +2.58 | 2.96 | -1.15 | -0.72 |
| 30/20 | 48 | 2187 | 579 | 16.5 | 24.8 | 58.8 | 16.5 | 45.9 | -0.51 | +2.45 | 2.96 | -1.37 | -0.84 |
| 40/20 | 48 | 2187 | 579 | 9.5 | 25.7 | 64.8 | 9.5 | 38.3 | -0.49 | +2.47 | 2.96 | -1.21 | -0.74 |
| 60/32 | 48 | 2187 | 579 | 4.3 | 14.0 | 81.7 | 4.3 | 38.0 | -0.50 | +2.46 | 2.96 | -1.05 | -0.61 |
| 55/30 | 48 | 2187 | 579 | 4.9 | 15.9 | 79.2 | 4.9 | 38.8 | -0.67 | +2.29 | 2.96 | -1.44 | -0.84 |
| 15/20 | 288 | 1984 | 560 | 67.2 | 32.2 | 0.6 | 67.2 | 65.8 | +0.62 | +3.64 | 3.02 | +1.69 | +1.18 |
| 20/20 | 288 | 1984 | 560 | 57.8 | 40.4 | 1.8 | 57.8 | 57.6 | +0.48 | +3.50 | 3.02 | +1.10 | +0.77 |
| 30/20 | 288 | 1984 | 560 | 44.1 | 51.3 | 4.6 | 44.1 | 46.0 | +0.20 | +3.22 | 3.02 | +0.36 | +0.25 |
| 40/20 | 288 | 1984 | 560 | 34.8 | 56.9 | 8.4 | 34.8 | 38.4 | +0.43 | +3.45 | 3.02 | +0.68 | +0.47 |
| 60/32 | 288 | 1984 | 560 | 27.9 | 49.0 | 23.1 | 27.9 | 38.1 | +1.11 | +4.13 | 3.02 | +1.23 | +0.81 |
| 55/30 | 288 | 1984 | 560 | 29.7 | 50.5 | 19.8 | 29.7 | 38.8 | +0.64 | +3.66 | 3.02 | +0.75 | +0.50 |
| 15/20 | 576 | 1643 | 522 | 68.7 | 31.3 | 0.0 | 68.7 | 65.7 | +1.04 | +4.05 | 3.01 | +2.58 | +1.87 |
| 20/20 | 576 | 1643 | 522 | 59.2 | 40.5 | 0.3 | 59.2 | 57.5 | +0.74 | +3.75 | 3.01 | +1.53 | +1.10 |
| 30/20 | 576 | 1643 | 522 | 46.4 | 52.4 | 1.2 | 46.4 | 46.0 | +0.53 | +3.54 | 3.01 | +0.87 | +0.61 |
| 40/20 | 576 | 1643 | 522 | 38.9 | 58.9 | 2.2 | 38.9 | 38.3 | +0.98 | +3.99 | 3.01 | +1.36 | +0.99 |
| 60/32 | 576 | 1643 | 522 | 34.8 | 54.0 | 11.1 | 34.8 | 38.1 | +1.97 | +4.98 | 3.01 | +1.86 | +1.30 |
| 55/30 | 576 | 1643 | 522 | 36.3 | 54.5 | 9.2 | 36.3 | 38.8 | +1.43 | +4.44 | 3.01 | +1.44 | +1.00 |

### `candle_history_36m`, 15 pairs, with the live spread guard applied

The pair subset keeps the 9 of 15 pairs whose entry in `measured_spreads.json` is at
or below the deployed rule's 1.9 pip ceiling: EURAUD, EURCHF, EURJPY, EURUSD,
GBPJPY, GBPUSD, USDCAD, USDCHF, USDJPY. This is an approximation of the live guard,
which evaluates a different measured spread per pair; see the caveats section.

| bracket | hold bars | n | entry days | win pct | loss pct | open pct | hit pct | break-even hit pct | net pips | gross pips | mean cost pips | t | t clustered |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15/20 | 48 | 1370 | 529 | 42.8 | 21.3 | 35.9 | 42.8 | 65.2 | -0.53 | +2.29 | 2.81 | -1.38 | -1.02 |
| 20/20 | 48 | 1370 | 529 | 30.5 | 23.7 | 45.8 | 30.5 | 57.0 | -0.69 | +2.12 | 2.81 | -1.64 | -1.20 |
| 30/20 | 48 | 1370 | 529 | 16.5 | 25.8 | 57.7 | 16.5 | 45.6 | -0.72 | +2.09 | 2.81 | -1.52 | -1.13 |
| 40/20 | 48 | 1370 | 529 | 9.9 | 26.6 | 63.5 | 9.9 | 38.0 | -0.58 | +2.24 | 2.81 | -1.13 | -0.85 |
| 60/32 | 48 | 1370 | 529 | 4.2 | 15.1 | 80.7 | 4.2 | 37.8 | -0.83 | +1.99 | 2.81 | -1.36 | -1.00 |
| 55/30 | 48 | 1370 | 529 | 5.0 | 17.2 | 77.8 | 5.0 | 38.6 | -1.00 | +1.82 | 2.81 | -1.69 | -1.24 |
| 15/20 | 288 | 1248 | 509 | 66.1 | 33.3 | 0.6 | 66.1 | 65.3 | +0.38 | +3.24 | 2.86 | +0.80 | +0.64 |
| 20/20 | 288 | 1248 | 509 | 56.7 | 41.7 | 1.7 | 56.7 | 57.2 | +0.15 | +3.01 | 2.86 | +0.27 | +0.21 |
| 30/20 | 288 | 1248 | 509 | 43.8 | 52.1 | 4.1 | 43.8 | 45.7 | +0.10 | +2.97 | 2.86 | +0.15 | +0.12 |
| 40/20 | 288 | 1248 | 509 | 35.3 | 57.1 | 7.6 | 35.3 | 38.1 | +0.68 | +3.54 | 2.86 | +0.84 | +0.69 |
| 60/32 | 288 | 1248 | 509 | 28.4 | 50.6 | 21.1 | 28.4 | 37.9 | +0.68 | +3.55 | 2.86 | +0.59 | +0.48 |
| 55/30 | 288 | 1248 | 509 | 30.1 | 51.7 | 18.2 | 30.1 | 38.7 | +0.45 | +3.31 | 2.86 | +0.41 | +0.33 |
| 15/20 | 576 | 1029 | 466 | 67.4 | 32.6 | 0.0 | 67.4 | 65.4 | +0.72 | +3.61 | 2.88 | +1.40 | +1.15 |
| 20/20 | 576 | 1029 | 466 | 57.6 | 42.1 | 0.3 | 57.6 | 57.2 | +0.25 | +3.13 | 2.88 | +0.40 | +0.33 |
| 30/20 | 576 | 1029 | 466 | 45.6 | 53.4 | 1.1 | 45.6 | 45.8 | +0.22 | +3.11 | 2.88 | +0.29 | +0.23 |
| 40/20 | 576 | 1029 | 466 | 38.8 | 59.4 | 1.8 | 38.8 | 38.1 | +0.94 | +3.82 | 2.88 | +1.03 | +0.87 |
| 60/32 | 576 | 1029 | 466 | 34.1 | 55.0 | 10.9 | 34.1 | 37.9 | +1.34 | +4.23 | 2.88 | +1.00 | +0.86 |
| 55/30 | 576 | 1029 | 466 | 36.2 | 55.4 | 8.5 | 36.2 | 38.7 | +1.10 | +3.98 | 2.88 | +0.87 | +0.74 |

### `candle_history_12m`, 26 pairs, 12 months

| bracket | hold bars | n | entry days | win pct | loss pct | open pct | hit pct | break-even hit pct | net pips | gross pips | mean cost pips | t | t clustered |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15/20 | 48 | 1115 | 221 | 46.5 | 18.6 | 34.9 | 46.5 | 70.8 | -1.24 | +3.55 | 4.79 | -2.91 | -1.53 |
| 20/20 | 48 | 1115 | 221 | 31.8 | 20.3 | 47.9 | 31.8 | 62.0 | -1.44 | +3.35 | 4.79 | -3.10 | -1.61 |
| 30/20 | 48 | 1115 | 221 | 14.8 | 22.5 | 62.7 | 14.8 | 49.6 | -2.32 | +2.47 | 4.79 | -4.54 | -2.31 |
| 40/20 | 48 | 1115 | 221 | 7.8 | 23.2 | 69.0 | 7.8 | 41.3 | -2.54 | +2.25 | 4.79 | -4.74 | -2.35 |
| 60/32 | 48 | 1115 | 221 | 3.5 | 13.5 | 83.0 | 3.5 | 40.0 | -2.92 | +1.87 | 4.79 | -4.61 | -2.17 |
| 55/30 | 48 | 1115 | 221 | 3.9 | 14.7 | 81.4 | 3.9 | 40.9 | -2.91 | +1.88 | 4.79 | -4.74 | -2.26 |
| 15/20 | 288 | 1029 | 217 | 69.9 | 29.1 | 1.1 | 69.9 | 71.0 | -0.20 | +4.63 | 4.84 | -0.40 | -0.23 |
| 20/20 | 288 | 1029 | 217 | 60.1 | 37.0 | 2.9 | 60.1 | 62.1 | -0.21 | +4.63 | 4.84 | -0.34 | -0.20 |
| 30/20 | 288 | 1029 | 217 | 43.1 | 49.7 | 7.2 | 43.1 | 49.7 | -1.42 | +3.41 | 4.84 | -1.86 | -1.07 |
| 40/20 | 288 | 1029 | 217 | 33.5 | 53.7 | 12.7 | 33.5 | 41.4 | -0.85 | +3.99 | 4.84 | -0.97 | -0.55 |
| 60/32 | 288 | 1029 | 217 | 25.5 | 44.8 | 29.7 | 25.5 | 40.0 | -0.13 | +4.71 | 4.84 | -0.10 | -0.06 |
| 55/30 | 288 | 1029 | 217 | 27.6 | 45.9 | 26.5 | 27.6 | 41.0 | -0.28 | +4.55 | 4.84 | -0.24 | -0.13 |
| 15/20 | 576 | 870 | 211 | 70.6 | 29.3 | 0.1 | 70.6 | 70.6 | +0.03 | +4.73 | 4.70 | +0.06 | +0.04 |
| 20/20 | 576 | 870 | 211 | 61.0 | 38.3 | 0.7 | 61.0 | 61.7 | -0.08 | +4.62 | 4.70 | -0.12 | -0.07 |
| 30/20 | 576 | 870 | 211 | 44.8 | 53.3 | 1.8 | 44.8 | 49.4 | -1.78 | +2.92 | 4.70 | -2.08 | -1.31 |
| 40/20 | 576 | 870 | 211 | 36.9 | 59.4 | 3.7 | 36.9 | 41.2 | -1.45 | +3.25 | 4.70 | -1.47 | -0.93 |
| 60/32 | 576 | 870 | 211 | 30.3 | 54.0 | 15.6 | 30.3 | 39.9 | -1.33 | +3.37 | 4.70 | -0.93 | -0.56 |
| 55/30 | 576 | 870 | 211 | 32.3 | 54.5 | 13.2 | 32.3 | 40.8 | -1.48 | +3.22 | 4.70 | -1.10 | -0.65 |

### `candle_history_12m`, 26 pairs, with the live spread guard applied

| bracket | hold bars | n | entry days | win pct | loss pct | open pct | hit pct | break-even hit pct | net pips | gross pips | mean cost pips | t | t clustered |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15/20 | 48 | 421 | 175 | 40.6 | 17.1 | 42.3 | 40.6 | 66.3 | -0.57 | +2.64 | 3.21 | -0.88 | -0.64 |
| 20/20 | 48 | 421 | 175 | 28.3 | 19.2 | 52.5 | 28.3 | 58.0 | -0.83 | +2.38 | 3.21 | -1.16 | -0.84 |
| 30/20 | 48 | 421 | 175 | 11.6 | 20.9 | 67.5 | 11.6 | 46.4 | -1.55 | +1.66 | 3.21 | -2.01 | -1.44 |
| 40/20 | 48 | 421 | 175 | 6.7 | 21.4 | 72.0 | 6.7 | 38.7 | -1.44 | +1.77 | 3.21 | -1.78 | -1.28 |
| 60/32 | 48 | 421 | 175 | 4.0 | 12.8 | 83.1 | 4.0 | 38.3 | -1.93 | +1.28 | 3.21 | -1.90 | -1.35 |
| 55/30 | 48 | 421 | 175 | 4.5 | 13.3 | 82.2 | 4.5 | 39.1 | -1.81 | +1.41 | 3.21 | -1.85 | -1.32 |
| 15/20 | 288 | 389 | 170 | 70.7 | 28.5 | 0.8 | 70.7 | 66.5 | +1.61 | +4.89 | 3.28 | +1.98 | +1.60 |
| 20/20 | 288 | 389 | 170 | 60.2 | 37.8 | 2.1 | 60.2 | 58.2 | +1.15 | +4.43 | 3.28 | +1.18 | +0.94 |
| 30/20 | 288 | 389 | 170 | 44.2 | 49.9 | 5.9 | 44.2 | 46.6 | +0.36 | +3.64 | 3.28 | +0.29 | +0.24 |
| 40/20 | 288 | 389 | 170 | 35.2 | 53.5 | 11.3 | 35.2 | 38.8 | +1.48 | +4.76 | 3.28 | +1.04 | +0.85 |
| 60/32 | 288 | 389 | 170 | 27.0 | 45.0 | 28.0 | 27.0 | 38.3 | +2.75 | +6.03 | 3.28 | +1.37 | +1.10 |
| 55/30 | 288 | 389 | 170 | 29.0 | 46.0 | 24.9 | 29.0 | 39.2 | +2.56 | +5.84 | 3.28 | +1.35 | +1.08 |
| 15/20 | 576 | 329 | 155 | 72.9 | 27.1 | 0.0 | 72.9 | 66.3 | +2.32 | +5.53 | 3.21 | +2.68 | +2.26 |
| 20/20 | 576 | 329 | 155 | 62.9 | 36.8 | 0.3 | 62.9 | 58.0 | +2.04 | +5.25 | 3.21 | +1.92 | +1.62 |
| 30/20 | 576 | 329 | 155 | 47.7 | 50.8 | 1.5 | 47.7 | 46.4 | +1.10 | +4.31 | 3.21 | +0.80 | +0.69 |
| 40/20 | 576 | 329 | 155 | 41.0 | 56.2 | 2.7 | 41.0 | 38.7 | +2.26 | +5.48 | 3.21 | +1.39 | +1.23 |
| 60/32 | 576 | 329 | 155 | 34.3 | 50.5 | 15.2 | 34.3 | 38.3 | +3.85 | +7.07 | 3.21 | +1.63 | +1.39 |
| 55/30 | 576 | 329 | 155 | 36.8 | 51.4 | 11.9 | 36.8 | 39.1 | +3.17 | +6.38 | 3.21 | +1.43 | +1.19 |

## Answers to the four questions

### 1. Does any cell clear the pre-registered |t| > 3 bar, net of each trade's own spread?

**On the grid as specified, no. Not one cell, in any dataset, at any hold, with or
without the measured table guard, plain t or clustered t.** The largest plain t in the
whole grid is +2.58 (`36m`, 15/20, hold 576, n=1,643, net +1.04); with calendar day
clustering it is +1.87. On the independent 26 pair set the largest is +0.06
(`T15/S20/H576`, n=870, net +0.03) and its measured table guard subset reaches +2.68
(n=329) with a clustered t of +2.26. The most negative is -4.74 on the 26 pair set at
a 48 bar hold, in the losing direction.

**One further variant does clear it, and it was found after the grid above, so it is
reported separately rather than slipped into the table: enforce the 1.9 pip ceiling on
the spread quoted at the trade's own entry bar.** With that gate, holding everything
else identical and still charging each trade its own quote, the 15 pair 3 year set
gives **T15/S20 at 288 bars: n=703, hit 67.7 percent, net +2.32, t = +3.80, clustered
t = +3.12**, positive in both halves (+2.06 first, +2.58 second); and **at 576 bars:
n=604, hit 70.4 percent, net +3.01, t = +4.62, clustered t = +3.72**, positive in
both halves (+2.49, +3.53). Source `scratch/bracket_gate_stats.out` from
`scratch/bracket_economics_gate_stats.py`, full grid in `scratch/bracket_gate.out` from
`scratch/bracket_economics_gate.py`. The gate addendum below states what that is worth
and what it is not.

A note on the clustered t. These trades are not independent draws: every pair fires
in the same UTC hour, so one market move produces many trades at once. All 26 pairs
breaking together is the single largest cluster and the plain t ignores it entirely.
The grid therefore reports `t clustered`, computed with cluster robust standard
errors grouped by the calendar day of entry, for example 560 clusters over 1,984
trades in the 36 month, 288 bar pool (`scratch/bracket_clustered.out`). Clustering
shrinks every t by roughly 25 to 35 percent, so the |t| > 3 bar is harder to clear
than the published two outcome figures suggest, not easier.

### 2. Which cells have an achieved hit rate above their own break-even requirement?

Above break-even **and** positive net pips, with sample sizes. All of these are
12 hour plus holds; nothing at a 48 bar hold qualifies in any dataset. The two
conditions select the same cells here: a scan of all 72 cells in
`scratch/bracket_economics_table.json` found no cell whose achieved hit rate is above
its break-even while its net is negative, so 17 of the 72 are above break-even and
all 17 are positive. (Corrected 2026-10-10: this sentence read 144 cells and 26 above
break-even. The artefact holds 72 cells, 18 baseline plus 18 guarded per dataset, and
table 2 below lists exactly 17 rows. See fact 193.)

| dataset | pool | bracket | hold bars | n | hit pct | break-even pct | margin pp | net pips | t | t clustered |
|---|---|---|---|---|---|---|---|---|---|---|
| `36m` | baseline | 15/20 | 288 | 1984 | 67.2 | 65.8 | +1.4 | +0.62 | +1.69 | +1.18 |
| `36m` | baseline | 20/20 | 288 | 1984 | 57.8 | 57.6 | +0.2 | +0.48 | +1.10 | +0.77 |
| `36m` | baseline | 15/20 | 576 | 1643 | 68.7 | 65.7 | +3.0 | +1.04 | +2.58 | +1.87 |
| `36m` | baseline | 20/20 | 576 | 1643 | 59.2 | 57.5 | +1.7 | +0.74 | +1.53 | +1.10 |
| `36m` | baseline | 30/20 | 576 | 1643 | 46.4 | 46.0 | +0.4 | +0.53 | +0.87 | +0.61 |
| `36m` | baseline | 40/20 | 576 | 1643 | 38.9 | 38.3 | +0.6 | +0.98 | +1.36 | +0.99 |
| `36m` | guard | 15/20 | 288 | 1248 | 66.1 | 65.3 | +0.8 | +0.38 | +0.80 | +0.64 |
| `36m` | guard | 15/20 | 576 | 1029 | 67.4 | 65.4 | +2.0 | +0.72 | +1.40 | +1.15 |
| `36m` | guard | 20/20 | 576 | 1029 | 57.6 | 57.2 | +0.4 | +0.25 | +0.40 | +0.33 |
| `36m` | guard | 40/20 | 576 | 1029 | 38.8 | 38.1 | +0.7 | +0.94 | +1.03 | +0.87 |
| `12m` | guard | 15/20 | 288 | 389 | 70.7 | 66.5 | +4.2 | +1.61 | +1.98 | +1.60 |
| `12m` | guard | 20/20 | 288 | 389 | 60.2 | 58.2 | +2.0 | +1.15 | +1.18 | +0.94 |
| `12m` | baseline | 15/20 | 576 | 870 | 70.6 | 70.6 | +0.0 | +0.03 | +0.06 | +0.04 |
| `12m` | guard | 15/20 | 576 | 329 | 72.9 | 66.3 | +6.6 | +2.32 | +2.68 | +2.26 |
| `12m` | guard | 20/20 | 576 | 329 | 62.9 | 58.0 | +4.9 | +2.04 | +1.92 | +1.62 |
| `12m` | guard | 30/20 | 576 | 329 | 47.7 | 46.4 | +1.3 | +1.10 | +0.80 | +0.70 |
| `12m` | guard | 40/20 | 576 | 329 | 41.0 | 38.7 | +2.3 | +2.26 | +1.39 | +1.16 |

Source: `scratch/bracket_table.out`, filtered on `hit pct > break-even pct and net >
0`. Every row above is a small margin against a toll of 2.9 to 3.3 pips, and the
margins do not stack up to a defensible edge: the largest achievable t among them is
+2.68, and the same cell on the full 15 pair 3 year sample (which contains the same
recent period plus an earlier regime) is only +0.72 with t=+1.40 at its guard
equivalent. Two things are being selected at once here, the bracket with the highest
hit rate and the cheapest pairs, on data where 26 of 28 pairs were visible.

### 3. Is the deployed bracket's problem the target, the stop, the hold, or the signal?

**The hold matters, the target does not help, and the residue is the signal.**
Measured, not argued.

**The hold is a real effect and it is the one thing that reproduces everywhere.**
Holding the event pool fixed (the 288 bar pool, 1,984 events, so the comparison is
not confounded by a different de-clustered sample) and reading the 15/20 bracket at
three holds, `scratch/bracket_hold_rw.out` from
`scratch/bracket_economics_hold_and_rw.py`:

| dataset | hold bars | n | hit pct | break-even pct | net pips | t | open pct |
|---|---|---|---|---|---|---|---|
| `36m` | 48 | 1984 | 45.3 | 65.8 | +1.00 | +1.46 | 34.4 |
| `36m` | 288 | 1984 | 67.2 | 65.8 | +0.62 | +1.69 | 0.6 |
| `36m` | 576 | 1984 | 67.2 | 65.8 | +0.62 | +1.69 | 0.6 |
| `12m` | 48 | 1029 | 47.1 | 71.0 | -0.86 | -0.94 | 34.8 |
| `12m` | 288 | 1029 | 69.9 | 71.0 | -0.20 | -0.40 | 1.1 |
| `12m` | 576 | 1029 | 69.9 | 71.0 | -0.20 | -0.40 | 1.1 |

The 48 bar hold is not a disaster on the 36 month set, because 34.4 percent of its
trades neither win nor lose and exit near flat; the deployed hold of 288 bars is the
better setting. The 576 bar column is identical to 288 on a fixed pool because no
trade in this entry set stays undecided past 288 bars at this bracket, which means
288 was already long enough and extending the hold further changes nothing. The
honest statement about the docstring's "the hold is the load-bearing parameter" is
that it was true as a correction to 48 bars, and past 288 bars there is nothing left
to load.

**Raising the target relative to the stop does not move the net up.** On the 36 month
baseline pool at a 288 bar hold, from `scratch/bracket_table.out`: 15/20 net +0.62
(t +1.69, n 1,984), 20/20 net +0.48 (t +1.10), 30/20 net +0.20 (t +0.36), 40/20 net
+0.43 (t +0.68), 60/32 net +1.11 (t +1.23, n 1,984), 55/30 net +0.64 (t +0.75). The
reward to risk near 1.85 brackets do not stand out. The hit rate collapses as the
target grows, 67.2 percent at 15 pips against 27.9 percent at 60 pips, and it
collapses faster than the break-even requirement falls, 65.8 percent against 38.1
percent. At a 576 bar hold, 60/32 is the highest net cell at +1.97 pips but the
difference from 40/20 at +0.98 is inside one standard error (t of the difference is
not computed, but 1.86 against 1.36 with n=1,643 is not a separation).

The reason the target increase cannot work is visible in the path statistics from
`scratch/bracket_pathcheck.out` on the 288 bar pool: within 288 bars, 85.2 percent of
these trades touch +15 pips and 67.2 percent touch -20 pips; at +60 pips only 36.2
percent ever get there, and 53.6 percent touch -32. A larger target asks the fade to
travel further than the reversion actually goes.

**Which leaves the signal.** The measured statement, from
`scratch/bracket_rw.out` (`scratch/bracket_economics_randomwalk.py`), all on the 36
month pool at a 288 bar hold, where the pooled M5 close to close return standard
deviation is 4.01 pips and the drift over 288 bars is +0.99 pips:

| bracket | measured hit pct | driftless random walk pct | Monte Carlo on real returns pct | measured minus random walk pp |
|---|---|---|---|---|
| 15/20 | 67.2 | 57.1 | 55.5 | +10.1 |
| 20/20 | 57.8 | 50.0 | 47.5 | +7.8 |
| 30/20 | 44.1 | 40.0 | 35.7 | +4.1 |
| 40/20 | 34.8 | 33.3 | 27.3 | +1.4 |
| 60/32 | 27.9 | 34.8 | 18.3 | -6.9 |
| 55/30 | 29.7 | 35.3 | 20.7 | -5.6 |

So the fade **does** beat a driftless walk at small targets and a day hold, by about
10 percentage points, which is a real and reproducible directional effect and is why
the gross is +3.64 pips. But the toll demands 65.8 percent and the signal delivers
67.2 percent on 15 pairs over 3 years, and 69.9 against a needed 71.0 on the 26 pair
12 month set. **The signal is real and too small to pay a 3 pip round trip.** The
bracket is not the problem: at 15/20 the toll is 3.02 pips against a 12.04 pip net
win, so it takes 20 percent of the winning leg, and no bracket in the grid does
materially better because the toll is fixed while the win leg has to be reachable,
and it is not reachable beyond about 20 pips.

### 4. What the cached history can and cannot support, and what was approximated

Supportable, with the caveats being about coverage rather than quality:

* **Pairs and periods.** `candle_history_36m`: 15 pairs, 2023-09-26 to 2026-09-10,
  220,339 to 220,586 M5 bars each. `candle_history_12m`: 26 pairs, 2025-09-15 to
  2026-09-10, 73,516 to 73,727 bars each. Bar size is **M5 only** in both; the
  deployed strategy's `max_hold_bars` is expressed in five minute bars and that
  matches the data, so no bar size conversion was needed anywhere.
* **Spread per trade.** The `sp` field is present in every record of both datasets,
  so each trade could be charged its own spread. The values are consistent with the
  prior art: the 15 pair pool has a mean of 3.02 and a median of 2.30 against the
  published 3.02 / 2.30 (`tools/edge_cost_check.py`).
* **Enough history for a 576 bar hold.** Only 1 event of 1,984 in the 288 bar pool
  and 1 of 1,643 in the 576 bar pool is truncated by the end of the loaded history,
  so the long hold cells are genuinely measured rather than edge effects
  (`scratch/bracket_table.out`, pool lines, `truncated` field).

Not supportable, and stated rather than papered over:

* **The 36 month set is 15 pairs and includes none of the widest crosses.** It has no
  EURNZD, GBPNZD, GBPAUD or EURCAD, which are the pairs that dominate the 26 pair
  set's cost distribution (median 3.10 pips against 2.30). So the 36 month set is
  systematically cheaper than the pair universe the bot can actually trade, and the
  cleanest long sample is flattered by that.
* **`data/candle_history_forex` carries no spread at all.** Its 28 pairs have
  `sp = null` in every record, and 3,999 bars per pair (7,203 for EURUSD and GBPUSD),
  which is four days of M5, not enough for a 288 bar hold with any sample. The
  work request listed it as a source; it cannot be used for a net-of-cost
  measurement and it was not used. The same is true of `data/forex_backtest`, whose
  files are `*_5m.json` OHLC candles with no quote record.
* **The realized paper record could not be reproduced from anything in this
  repository.** The figure given in the request is 163 closes at a 13.5 percent win
  rate for -1,342.68 USD. The paper ledger at
  `/home/qchan/.config/tradebot-sci-gui/local/data/paper_ledger.json` contains 252
  closed trades from 2026-06-18 to 2026-10-09, and its trade log attributes exactly
  **2** of them to `forex_scrape_fade`, for +59.77 USD in total, with its
  `by_strategy` block reporting `trades: 0` for every strategy. Those two counts
  cannot both be right and neither produces 163 closes. The 163 trade figure is
  therefore taken from the work request as given and is not independently verified
  here.
* **The live spread guard was approximated.** The real guard compares a per pair
  measured value from `measured_spreads.json` (in basis points, converted against
  the pair's last close) to 1.9 pips. The grid approximates it by keeping pairs whose
  table entry is at or below 1.9, which drops AUDJPY, AUDUSD, CADJPY, CHFJPY, GBPCHF
  and NZDUSD from the 15 pair set. This is close but not identical to the live test,
  because the live conversion multiplies by the current price and so varies with it.
  Every guard table row is labelled as the approximation.
* **Carry was not charged.** `LARGE_TARGETS_2026_09_13.md` measured adverse financing
  of about 1.1 pips median over a 5 day hold, up to 6.5 pips on GBPJPY. A 576 bar
  hold is 2 days, so the financing not charged here is roughly half that, on the
  order of 0.5 pips on the carry pairs and near zero on the rest. That is the same
  order as the +1.04 pips the best 15 pair cell shows, so the 576 bar column should
  be read as gross of financing. Financing is therefore one further reason to doubt
  the longest holds, and it pushes in the direction of the negative verdict.
* **The spread charged is the quoted candle spread, not a realized round trip.**
  That is the same charge the prior art uses, and it is what makes these figures
  comparable with `Documentation/Research/SCRAPE_ENTRY_2026_09_13.md`, but it does
  not include slippage on the stop or any widening between the entry bar and the exit
  bar. Since the deployed rule holds for a day in some of the widest hours of the
  session, the true toll is likely higher than charged, not lower.

## Addendum: the gate that does clear the bar, and what it is worth

This was not one of the requested cells. It is reported because it is the only
configuration in the whole exercise that clears |t| > 3, and leaving it out would make
the first answer wrong.

**What it is.** Refuse the trade when the spread quoted at the trade's own entry bar
is wider than 1.9 pips, then trade exactly as deployed. It rests on the same `sp`
field that is charged as the toll, so it is an ex-ante cost rule with no look ahead:
the quote at the entry bar is known when the entry is taken.

**What it measures, 15 pairs, 3 years, each trade charged its own entry quote**
(`scratch/bracket_gate_stats.out`):

| bracket | hold | n | entry days | hit pct | break-even pct | mean cost | net pips | t | t clustered | first half | second half |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 15/20 | 288 | 703 | 354 | 67.7 | 61.8 | 1.62 | +2.32 | +3.80 | +3.12 | +2.06 (t +2.36) | +2.58 (t +3.02) |
| 30/20 | 288 | 703 | 354 | 44.1 | 43.2 | 1.62 | +2.37 | +2.60 | +2.11 | +2.62 (t +2.02) | +2.12 (t +1.65) |
| 40/20 | 288 | 703 | 354 | 34.3 | 36.0 | 1.62 | +3.02 | +2.88 | +2.32 | +2.92 (t +1.95) | +3.12 (t +2.12) |
| 15/20 | 576 | 604 | 313 | 70.4 | 61.8 | 1.62 | +3.01 | +4.62 | +3.72 | +2.49 (t +2.67) | +3.53 (t +3.89) |
| 30/20 | 576 | 604 | 313 | 48.8 | 43.2 | 1.62 | +3.15 | +3.11 | +2.51 | +2.97 (t +2.06) | +3.33 (t +2.33) |
| 40/20 | 576 | 604 | 313 | 42.4 | 36.0 | 1.62 | +4.47 | +3.73 | +2.96 | +3.86 (t +2.28) | +5.09 (t +2.99) |

The gate keeps 703 of 1,984 events at a 24 hour hold, 35.4 percent, and cuts the mean
charged cost from 3.02 to 1.62 pips. That cost reduction is 1.40 of the 1.70 pip
improvement at 15/20; the remaining 0.30 comes from the gated subset also having a
slightly higher gross (+3.94 against +3.64), which is the expected consequence of
cheap quotes arriving in calmer, tighter conditions.

**Its weaknesses, stated at the same length.**

1. **The independent set is much weaker.** On the 26 pair 12 month set the gate keeps
   212 of 1,029 events at 24 hours (13 pairs, 102 entry days) and 185 of 870 at 48
   hours (13 pairs, 93 entry days). The 15/20 cell reads n=212, net +4.01, t = +3.80
   but clustered t = +2.87, and the split half is +2.63 then +5.40, meaning most of it
   is the recent period. At 48 hours it is n=185, net +4.87, t = +4.39, clustered t =
   +3.36, first half +3.07, second half +6.76. So the plain t clears on the
   independent set too, and the clustered t does so only at 48 hours, and the effect
   is concentrated late in the sample. The 26 pair set is also the only one of the two
   where the gate is doing the heaviest lifting: it drops 79 percent of the events,
   and most of the dropped ones are the wide crosses that made that set's ungated
   result negative.
2. **It is selected after seeing the grid.** The gate is the best cell of a new
   sub-grid, and the same warning from
   `Documentation/Research/LARGE_TARGETS_2026_09_13.md` applies: a 49 cell grid's best
   cell is not evidence. What defends it here is that the rule is one parameter, it is
   the rule the deployed strategy already claims to implement, the sign holds in both
   halves at 15/20 on the large set, and the mechanism is arithmetic rather than a new
   signal. That is a candidate for a forward test, not a demonstration.
3. **The gate cannot be trusted to hold in live execution.** It filters on the quote
   seen at the entry bar. In the cache, a pair's spread at a given bar is a recorded
   number; live, the quote that matters includes whatever widening occurs between the
   decision and the fill. A rule whose entire edge is a 1.4 pip saving on the toll is
   directly exposed to exactly that.
4. **It also requires genuinely cheap quotes to exist.** The gated subset's mean cost
   is 1.62 pips, which is EURUSD and USDJPY territory. The deployed table
   (`measured_spreads.json`) shows 6 of the 15 pairs above the 1.9 pip ceiling, so the
   live rule would be trading a smaller universe than the backtest's 15 pairs, and
   concentration and correlation across those 9 to 13 pairs are not measured here.
5. **The same financing gap applies.** At 48 hours the cell is gross of carry, worth
   roughly 0.5 pips on the carry pairs by the estimate in
   `LARGE_TARGETS_2026_09_13.md`. At 24 hours it is about half that.

**Why the deployed rule does not already capture this.** As of this writing the
strategy file tests its ceiling against one number per pair from
`measured_spreads.json`, and only when that number is present. The number is an
average for the pair, not the trade's own quote, so a trade taken while the quote is
wide still passes. This measurement is the size of that gap, and it is larger than the
whole ungated edge.

**Note on a moving target.** Another agent was editing
`src/tradebot_sci/strategy/variants/forex_scrape_fade.py` and `tools/edge_entry.py`
during this measurement pass (file modification times 01:36 and 01:40 on 2026-10-10,
after this session started; both files carry uncommitted changes). The gate paragraph
above describes the state of the strategy file as read at the start of this session,
which is the same state as the copy this measurement is about. Its new docstring
already cites `+2.32 pips at t=+3.80` on fifteen pairs and `+3.90 at t=+3.49` on
twenty-six. The fifteen pair figure is this document's 15/20 cell at 288 bars with the
gate, exactly. The twenty-six pair figure does not match this document's gate cells,
which are +4.01 at `t=+3.80` (288 bars, n=212) and +4.87 at `t=+4.39` (576 bars,
n=185), so it is presumably a different cell or a different ceiling; it was not
reproduced here. What matters for reading the tables above:
`tools/edge_cost_check.py` was re-run after those edits and still prints the recorded
`+0.51` at `t=+1.38` and `-0.22` at `t=-0.38`, and the `detect` function this harness
imports was not among the parts of `tools/edge_entry.py` that changed.

## Corrections made during this work

Recorded because two of them changed results materially and a third was the reason
earlier project figures look as they do.

1. **A trade that reaches neither barrier was being charged a full stop loss.** My
   first grid pass used the `tools/edge_entry.py:outcomes` tie rule literally, in
   which `fs <= ft` is true when neither barrier exists and the trade is booked as
   -stop. On the 48 bar hold 34.9 percent of trades reach neither barrier, so the
   first version of this grid reported -7.37 pips per trade for the 15/20 48 bar cell
   where the three outcome answer is -0.25. Every 48 bar figure in this document is
   from the corrected rule; the buggy numbers are in
   `scratch/bracket_grid_run1.out` and are superseded.
2. **Forward paths were one to two bars short.** My first pass padded every event's
   path to the longest available rather than to the hold window, which silently
   evaluated a 288 bar hold over 276 or 287 bars depending on the event. The fix
   reproduces the published harness exactly, which is how it was caught. The
   before-and-after is visible by comparing `scratch/bracket_grid_run1.out` with
   `scratch/bracket_final.out`; the deployed cell went from +0.94 / t +2.31 to
   +0.62 / t +1.69, and the published `+0.51` figure at the published spacing is
   reproduced by `scratch/bracket_economics_pathcheck.py`.
3. **The first random walk check used differences of bar highs.** Bar highs ratchet,
   so that pool had a large positive drift and produced Monte Carlo hit rates of 82
   to 98 percent, which is nonsense. The corrected pool is close to close and is
   comparable to the driftless closed form (`scratch/bracket_rw.out`).
4. **The open adjusted break-even hurdle was mis-derived on the first attempt and is
   not used as a headline.** Solving for the win rate that makes a cell zero while
   holding the open branch fixed is only meaningful when the loss branch has negative
   expectancy; where it does not the solution is undefined or negative, and in the
   48 bar rows the open branch dominates, so the hurdle is unstable. The column was
   therefore dropped from the grid tables above. The correct statement, verified
   against the group decomposition in `scratch/bracket_groups.out`, is that at the
   deployed cell the open trades are few (0.6 percent, 12 of 1,984) and average -3.64
   net pips, so the open adjusted requirement is 68.8 percent against an achieved
   67.2 percent, which is the same conclusion as the simple hurdle. The win, loss and
   open columns in the grid tables carry the same information without the instability.

## The best cell, and what it is worth

Two answers, because there are two populations.

**Best cell on the grid as measured, whole pool, no gate.** The highest net per trade
anywhere is `36m` baseline 60/32 at a 576 bar hold:
**+1.97 pips per trade over 1,643 trades, hit rate 34.8 percent against a break-even
of 38.1 percent, t = +1.86, clustered t = +1.30**. It does not clear the bar, its hit
rate is below its own break-even, and its 11.1 percent of time stop exits contribute
+12.85 pips each, which is what actually carries the number. The best combination of
above break-even hit rate and sample size in that population is the deployed bracket
itself at a 576 bar hold on 15 pairs: 1,643 trades, 68.7 percent against 65.7 percent,
+1.04 pips, t = +2.58, clustered t = +1.87.

**Best cell overall, with the own quote gate.** The deployed bracket, 15/20, at a 48
hour hold, on the 15 pair 3 year set: **n = 604, 70.4 percent hit rate against a 61.8
percent break-even, mean charged cost 1.62 pips, +3.01 pips per trade, t = +4.62,
clustered t = +3.72, positive in both halves.** It is the only thing in this study
that clears |t| > 3 after clustering. On the independent 26 pair set the same settings
give n = 185, +4.87 pips, t = +4.39, clustered t = +3.36, but its first half is +3.07
against a second half of +6.76, so read that as an effect concentrated in the recent
period rather than as a stable edge.

The 26 pair confirmation set, whole pool and ungated, returns -1.33 to +0.03 pips
across its entire 576 bar row. Nothing on the grid as deployed is a recommendation to
trade anything. The gate is the one thing here worth a forward test, and the addendum
lists the five reasons to expect less from it live than it shows in the cache.
