#!/usr/bin/env python3
"""Derive exits from the MFE/MAE distribution instead of guessing at round numbers.

The critique this answers: MFE and MAE are the data that say where a target and a
stop belong, and a human watching a trade give ground bails out and keeps something
while a fixed target waits for a level most trades never reach and keeps nothing.

Method
------
1. Replay the validated entry (fade a fresh 20-bar range break, 20:00 UTC) and record
   each trade's whole path once: best favourable and worst adverse excursion at every
   bar, with no exit rules applied. The distribution is therefore not shaped by the
   exits being tested.
2. Report the MFE and MAE distributions — what a target and stop should be read from.
3. Evaluate exit schemes on those same recorded paths, net of each pair's measured
   spread: the current fixed bracket, brackets read off the distribution, and the
   "human bail" (exit once price gives back a fraction of ATR from its best level).

Usage:
    python3 tools/edge_exits.py
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

from edge_research import load_series, atr  # noqa: E402

SYMBOLS = ("EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,USDCAD,USDCHF,GBPJPY,EURJPY,"
           "AUDJPY,EURAUD,EURCHF,GBPCHF,CADJPY,CHFJPY")


def collect(s, hold):
    """All trades for one symbol: entry indices, directions, and per-bar paths."""
    c, h, l = s.c, s.h, s.l
    n = c.size
    rmax = np.full(n, np.nan)
    rmin = np.full(n, np.nan)
    for i in range(20, n):
        rmax[i] = h[i - 20:i].max()
        rmin[i] = l[i - 20:i].min()
    hours = ((s.epoch // 3600) % 24).astype(int)
    a = atr(h, l, c, 14)
    pip = s.pip
    out = []
    last = -10 ** 9
    for i in range(20, n - hold - 2):
        if hours[i] != 20 or (i - last) < hold:
            continue
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        long_break = c[i] < rmin[i]
        short_break = c[i] > rmax[i]
        if not (long_break or short_break):
            continue
        direction = "long" if long_break else "short"
        last = i
        entry = s.o[i + 1]
        best = np.empty(hold)
        worst = np.empty(hold)
        cur = np.empty(hold)
        bb = ww = 0.0
        for k in range(1, hold + 1):
            if direction == "long":
                fav = (h[i + k] - entry) / pip
                adv = (l[i + k] - entry) / pip
                cu = (c[i + k] - entry) / pip
            else:
                fav = (entry - l[i + k]) / pip
                adv = (entry - h[i + k]) / pip
                cu = (entry - c[i + k]) / pip
            bb = max(bb, fav); ww = min(ww, adv)
            best[k - 1] = bb; worst[k - 1] = ww; cur[k - 1] = cu
        out.append(dict(sym=s.symbol, epoch=int(s.epoch[i]), best=best, worst=worst,
                        cur=cur, atr=a[i] / pip, cost=s.spread_pips(),
                        mfe=float(best[-1]), mae=float(worst[-1])))
    return out


def simulate(t, hold, tp=None, sl=None, bail_frac=None, arm_pips=0.0, floor_pips=None):
    """Replay the exit rules against a recorded path. Returns pips before cost."""
    for k in range(hold):
        b, w, cu = t["best"][k], t["worst"][k], t["cur"][k]
        if tp is not None and b >= tp:
            return tp
        if sl is not None and w <= -sl:
            return -sl
        if bail_frac is not None and b >= (floor_pips if floor_pips is not None else arm_pips) \
                and (b - cu) >= bail_frac * t["atr"]:
            return cu
    return t["cur"][-1]


def report(name, vals, costs, epochs, hold):
    v = np.array(vals, dtype=float)
    net = v - np.array(costs, dtype=float)
    if v.size < 30:
        print(f"{name:38} insufficient trades")
        return
    buckets = np.array(epochs, dtype=np.int64) // (300 * hold)
    order = np.argsort(buckets)
    b, x = buckets[order], net[order]
    uniq, starts = np.unique(b, return_index=True)
    means = np.add.reduceat(x, starts) / np.diff(np.append(starts, x.size))
    sd = means.std(ddof=1) if means.size > 2 else 0.0
    t = means.mean() / (sd / math.sqrt(means.size)) if sd else 0.0
    print(f"{name:38}{v.size:>6}{v.mean():>8.2f}{np.mean(costs):>7.2f}{net.mean():>8.2f}"
          f"{t:>7.2f}{(net > 0).mean():>7.0%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="candle_history_36m")
    ap.add_argument("--symbols", default=SYMBOLS)
    ap.add_argument("--hold", type=int, default=48)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir

    trades = []
    for sym in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
        s = load_series(data_dir, sym, args.start, args.end)
        if s is None or s.c.size < 500:
            continue
        trades.extend(collect(s, args.hold))
    if not trades:
        print("no entries")
        return 1

    mfe = np.array([t["mfe"] for t in trades])
    mae = np.array([t["mae"] for t in trades])
    atrs = np.array([t["atr"] for t in trades])
    costs = [t["cost"] for t in trades]
    epochs = [t["epoch"] for t in trades]

    print(f"[EXITS] {len(trades)} trades from the validated entry "
          f"(fresh 20-bar range break, 20:00 UTC), paths recorded over {args.hold} bars "
          f"with no exit rules applied\n")
    print("MFE — where a target belongs (pips):")
    print("   " + "  ".join(f"p{p}={np.percentile(mfe, p):.1f}" for p in (25, 50, 60, 70, 80, 90)))
    print("MAE — where a stop belongs (pips):")
    print("   " + "  ".join(f"p{p}={np.percentile(mae, p):.1f}" for p in (25, 50, 60, 70, 80, 90)))
    print(f"\n   median ATR {np.median(atrs):.1f}p | median spread {np.median(costs):.2f}p"
          f" | share of trades that ever go positive {float((mfe > 0).mean()):.0%}")

    med_atr = float(np.median(atrs))
    tp60, sl60 = float(np.percentile(mfe, 60)), float(abs(np.percentile(mae, 60)))
    tp50, sl70 = float(np.percentile(mfe, 50)), float(abs(np.percentile(mae, 70)))
    tp80 = float(np.percentile(mfe, 80))

    schemes = [
        ("current fixed 10/20", dict(tp=10.0, sl=20.0)),
        (f"distribution p60/p60 ({tp60:.0f}/{sl60:.0f})", dict(tp=tp60, sl=sl60)),
        (f"distribution p50/p70 ({tp50:.0f}/{sl70:.0f})", dict(tp=tp50, sl=sl70)),
        ("bail 0.2ATR after +0.2ATR, SL20", dict(bail_frac=0.2, arm_pips=0.2 * med_atr, sl=20.0)),
        ("bail 0.3ATR after +0.3ATR, SL20", dict(bail_frac=0.3, arm_pips=0.3 * med_atr, sl=20.0)),
        ("bail 0.2ATR after +0.1ATR, SL20", dict(bail_frac=0.2, arm_pips=0.1 * med_atr, sl=20.0)),
        ("bail 0.2ATR from breakeven, SL20", dict(bail_frac=0.2, arm_pips=0.0, sl=20.0)),
        (f"bail 0.2ATR + TP p80 ({tp80:.0f}), SL20", dict(bail_frac=0.2, arm_pips=0.2 * med_atr,
                                                          tp=tp80, sl=20.0)),
        ("no exit (hold to window end)", dict()),
    ]

    print(f"\n{'scheme':38}{'n':>6}{'gross':>8}{'cost':>7}{'NET':>8}{'t':>7}{'green':>7}")
    print("-" * 88)
    for name, kw in schemes:
        vals = [simulate(t, args.hold, **kw) for t in trades]
        report(name, vals, costs, epochs, args.hold)

    print("\nNET is after each pair's measured spread. Only an improvement on the")
    print("current fixed bracket counts; the rest is a different way to lose the same.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
