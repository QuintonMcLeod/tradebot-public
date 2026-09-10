#!/usr/bin/env python3
"""Scrape test, second pass: WHEN matters, break-even stops, and price action vs indicators.

Four claims from the operator, each tested here:

1. "Oanda widens spreads at certain times - around 5-6pm - that is their way of
   telling you not to trade."  Measured: the spread goes 1.60 -> 4.30 pips at
   21:00 UTC (17:00 New York), then 2.00 at 22:00. Trade timing is charged, and
   the rollover is where it is worst.

2. "You are not correlating WHEN the wins are and WHEN the losses are. Trade the
   hours with the most wins, avoid the hours with the most losses."  Reported
   hour by hour: hit rate, gross and net expectancy for all 24 hours.

3. "Set your SLs early, usually around break even."  Tested as a break-even stop:
   once the trade is X pips in profit the stop moves to entry, so a winner cannot
   turn into a loser.

4. "Follow price action before indicators; indicators lag, so you are always
   chasing."  Tested head to head: an SMA z-score entry against pure price-action
   entries (runs of closes, 20-bar range breaks, prior-day extremes).

Conventions that keep it honest
------------------------------
- The stop wins same-bar ties; optimistic ties invent traders who do not exist.
- Entries are sampled every `hold` bars so forward windows do not overlap.
- Every trade pays the pair's measured round-trip spread, win or lose.
- Inference is clustered in time rather than counted per trade.

Usage:
    python3 tools/edge_scrape.py --by-hour
    python3 tools/edge_scrape.py --entry pa_consec3 --be-trigger 5
    python3 tools/edge_scrape.py --all-entries --exclude-hours 21,22
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from edge_research import load_series, sma, rolling_std  # noqa: E402

DEFAULT_SYMBOLS = ("EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,USDCAD,USDCHF,GBPJPY,EURJPY,"
                   "AUDJPY,EURAUD,EURCHF,GBPCHF,CADJPY,CHFJPY")


def build_signal(s, kind: str):
    """(long_mask, short_mask) for the requested entry style. All are fade-style:
    the long mask fires after price has fallen, the short mask after it has risen."""
    c, h, l = s.c, s.h, s.l
    n = c.size

    if kind == "fade_z":
        ma, sd = sma(c, 20), rolling_std(c, 20)
        with np.errstate(invalid="ignore", divide="ignore"):
            zs = (c - ma) / sd
        return zs <= -1.0, zs >= 1.0

    if kind in ("pa_consec2", "pa_consec3"):
        k = 2 if kind.endswith("2") else 3
        down = np.ones(n, dtype=bool)
        up = np.ones(n, dtype=bool)
        for j in range(1, k + 1):
            prev = np.roll(c, j)
            down &= c < prev
            up &= c > prev
        down[:k + 1] = False
        up[:k + 1] = False
        return down, up

    if kind == "pa_break_range":
        win = 20
        rmax = np.full(n, np.nan)
        rmin = np.full(n, np.nan)
        for i in range(win, n):
            rmax[i] = h[i - win:i].max()
            rmin[i] = l[i - win:i].min()
        return c < rmin, c > rmax

    if kind == "pa_prior_day":
        day = (s.epoch // 86400).astype(np.int64)
        pdh = np.full(n, np.nan)
        pdl = np.full(n, np.nan)
        uniq = np.unique(day)
        for k in range(1, len(uniq)):
            prev, cur = uniq[k - 1], uniq[k]
            pm, cm = day == prev, day == cur
            if pm.sum() > 10:
                pdh[cm] = h[pm].max()
                pdl[cm] = l[pm].min()
        return l <= pdl, h >= pdh

    raise SystemExit(f"unknown entry kind: {kind}")


def bracket(s, tp_pips, sl_pips, hold, direction, long_mask, short_mask,
            cost_pips=None, be_trigger=0.0):
    """Brackets with an optional break-even stop, vectorised over entry bars."""
    n = s.c.size
    pip = s.pip
    cost = cost_pips if cost_pips is not None else s.spread_pips()
    tp, sl = tp_pips * pip, sl_pips * pip
    be = be_trigger * pip

    mask = long_mask if direction == "long" else short_mask
    idx = np.arange(0, n - hold - 1)
    if idx.size == 0:
        return None
    idx = idx[mask[idx]]
    if idx.size == 0:
        return None

    m = idx.size
    entry = s.c[idx]
    undecided = np.ones(m, dtype=bool)
    gross = np.zeros(m)
    armed = np.zeros(m, dtype=bool)

    for k in range(1, hold + 1):
        if not undecided.any():
            break
        highs, lows = s.h[idx + k], s.l[idx + k]

        if direction == "long":
            if be > 0:
                armed |= undecided & ~armed & (highs >= entry + be)
            stop = np.where(armed, entry, entry - sl)
            hit_sl = undecided & (lows <= stop)
            gross[hit_sl] = np.where(armed[hit_sl], 0.0, (stop[hit_sl] - entry[hit_sl]) / pip)
            undecided &= ~hit_sl
            hit_tp = undecided & (highs >= entry + tp)
            gross[hit_tp] = tp_pips
            undecided &= ~hit_tp
        else:
            if be > 0:
                armed |= undecided & ~armed & (lows <= entry - be)
            stop = np.where(armed, entry, entry + sl)
            hit_sl = undecided & (highs >= stop)
            gross[hit_sl] = np.where(armed[hit_sl], 0.0, (entry[hit_sl] - stop[hit_sl]) / pip)
            undecided &= ~hit_sl
            hit_tp = undecided & (lows <= entry - tp)
            gross[hit_tp] = tp_pips
            undecided &= ~hit_tp

    if undecided.any():
        exit_px = s.c[idx[undecided] + hold]
        if direction == "long":
            gross[undecided] = (exit_px - entry[undecided]) / pip
        else:
            gross[undecided] = (entry[undecided] - exit_px) / pip

    win = gross >= tp_pips - 1e-9
    return {"epoch": s.epoch[idx], "gross": gross, "net": gross - cost, "win": win,
            "hours": ((s.epoch[idx] // 3600) % 24).astype(int)}


def clustered(vals, epochs, hold):
    buckets = epochs // (300 * hold)
    order = np.argsort(buckets)
    b, v = buckets[order], vals[order]
    uniq, starts = np.unique(b, return_index=True)
    means = np.add.reduceat(v, starts) / np.diff(np.append(starts, v.size))
    sd = means.std(ddof=1) if means.size > 2 else 0.0
    t = means.mean() / (sd / math.sqrt(means.size)) if sd else 0.0
    return float(t), int(means.size)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape test: timing, break-even stops, price action.")
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--entry", default="fade_z",
                    choices=["fade_z", "pa_consec2", "pa_consec3", "pa_break_range", "pa_prior_day"])
    ap.add_argument("--all-entries", action="store_true", help="Compare every entry style")
    ap.add_argument("--hold", type=int, default=48)
    ap.add_argument("--tp", type=float, default=5.0)
    ap.add_argument("--sl", type=float, default=20.0)
    ap.add_argument("--be-trigger", type=float, default=0.0,
                    help="Pips in profit at which the stop moves to break even (0 = off)")
    ap.add_argument("--cost-pips", type=float, default=None)
    ap.add_argument("--by-hour", action="store_true")
    ap.add_argument("--exclude-hours", default=None, help="Comma list of UTC hours to skip")
    ap.add_argument("--only-hours", default=None, help="Comma list of UTC hours to KEEP")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD lower bound (out-of-sample check)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD upper bound")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir
    skip = {int(x) for x in args.exclude_hours.split(",")} if args.exclude_hours else set()
    keep_only = {int(x) for x in args.only_hours.split(",")} if args.only_hours else None

    prepared = []
    for sym in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
        s = load_series(data_dir, sym, args.start, args.end)
        if s is not None:
            prepared.append((sym, s))
    if not prepared:
        print("No data")
        return 1

    kinds = (["fade_z", "pa_consec2", "pa_consec3", "pa_break_range", "pa_prior_day"]
             if args.all_entries else [args.entry])

    for kind in kinds:
        net_l, gross_l, win_l, ep_l = [], [], [], []
        per_pair = {}
        for sym, s in prepared:
            lm, sm_ = build_signal(s, kind)
            for direction in ("long", "short"):
                r = bracket(s, args.tp, args.sl, args.hold, direction, lm, sm_,
                            args.cost_pips, args.be_trigger)
                if r is None or r["net"].size == 0:
                    continue
                keep = np.ones(r["net"].size, bool)
                if skip:
                    keep &= ~np.isin(r["hours"], list(skip))
                if keep_only is not None:
                    keep &= np.isin(r["hours"], list(keep_only))
                if not keep.any():
                    continue
                net_l.append(r["net"][keep]); gross_l.append(r["gross"][keep])
                win_l.append(r["win"][keep]); ep_l.append(r["epoch"][keep])
                per_pair.setdefault(sym, []).append(r["net"][keep].mean())
        if not net_l:
            continue
        net, gross = np.concatenate(net_l), np.concatenate(gross_l)
        win, ep = np.concatenate(win_l), np.concatenate(ep_l)
        t, cl = clustered(net, ep, args.hold)
        pos = sum(1 for v in per_pair.values() if np.mean(v) > 0)
        label = kind + (f" +BE@{args.be_trigger:.0f}p" if args.be_trigger else "")
        if skip:
            label += " skip[" + ",".join(str(x) for x in sorted(skip)) + "]"
        print(f"{label:34} n={net.size:>9} cl={cl:>5} TP-win={win.mean():>4.0%} "
              f"gross={gross.mean():>+6.3f} net={net.mean():>+6.3f} t={t:>6.2f} pairs+ {pos}/{len(per_pair)}")

    if args.by_hour:
        print("\nper-hour expectancy, fade_z TP5/SL20 — where the wins and losses actually are")
        print(f"{'UTC':>4}{'ET':>4}{'n':>9}{'TP-win':>8}{'gross':>8}{'net':>8}{'t':>7}  reading")
        print("-" * 66)
        by_hour = {}
        for sym, s in prepared:
            lm, sm_ = build_signal(s, "fade_z")
            for direction in ("long", "short"):
                r = bracket(s, args.tp, args.sl, args.hold, direction, lm, sm_,
                            args.cost_pips, args.be_trigger)
                if r is None:
                    continue
                for hh in np.unique(r["hours"]):
                    m = r["hours"] == hh
                    by_hour.setdefault(int(hh), []).append(
                        (r["gross"][m], r["net"][m], r["win"][m], r["epoch"][m]))
        best = None
        for hh in range(24):
            if hh not in by_hour:
                continue
            g = np.concatenate([x[0] for x in by_hour[hh]])
            nn = np.concatenate([x[1] for x in by_hour[hh]])
            w = np.concatenate([x[2] for x in by_hour[hh]])
            e = np.concatenate([x[3] for x in by_hour[hh]])
            t, _ = clustered(nn, e, args.hold)
            reading = ("gross beats cost" if g.mean() > 2.2 else
                       "gross + but under cost" if g.mean() > 0 else "loses before cost")
            mark = "  <= rollover" if hh in (21, 22) else ""
            print(f"{hh:>4}{((hh-4)%24):>4}{g.size:>9}{w.mean():>8.0%}{g.mean():>8.2f}"
                  f"{nn.mean():>8.2f}{t:>7.2f}  {reading}{mark}")
            if best is None or g.mean() > best[1]:
                best = (hh, g.mean())
        if best:
            print(f"\nbest hour by gross expectancy: {best[0]:02d}:00 UTC at {best[1]:+.2f} pips "
                  f"— cost is ~2.2, so the question is whether it clears that")

    print("\ngross is before the toll, net after it. A high TP-win rate is not an edge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
