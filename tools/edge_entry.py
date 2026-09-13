#!/usr/bin/env python3
"""Improve the fade entry, measured gross so the signal is visible before costs.

Why this exists
---------------
Two findings put the effort here. The scrape is the only entry family whose target
grid stayed profitable, and the large-target experiment showed why chasing a bigger
target cannot rescue it: the entries that reach a large target carry no directional
information at all. What is left is the scrape, with the target it already has, and
the only remaining lever is the quality of the entry.

Costs are deliberately switched off by default. Every previous result has been
dominated by a 2.45-pip toll, which makes a good entry and a mediocre one look the
same. Gross expectancy says whether the signal knows anything; the spread is then a
separate, arithmetic question.

Method
------
Every fresh break of a prior range is an event. For each event the forward path is
recorded together with the conditions around it, so the same pool of events can be
read through any filter without re-detecting anything:

    hour, day of week, break depth in ATR, whether the break bar expanded, how far
    price had stretched from its mean, the width of the range that broke, the
    volatility regime, and how many bars had already run in the break direction.

Filters are then read off that pool. Selection is done on the first half of the
sample and validated on the second half, because a filter chosen on all of the data
and reported on all of the data is not evidence of anything.

Two event types are compared: fading the break as it happens, and waiting for the
break to fail before entering.

Usage:
    python3 tools/edge_entry.py --data-dir candle_history_36m
    python3 tools/edge_entry.py --data-dir candle_history_36m --win 60 --horizon 48
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

from edge_research import load_series  # noqa: E402
from edge_targets import atr  # noqa: E402

BARS_PER_DAY = 288
TARGETS = (6.0, 8.0, 10.0, 12.0, 15.0)
STOPS = (10.0, 15.0, 20.0, 30.0)
FEATURES = ("hour", "break_atr", "bar_range_atr", "stretch_atr",
            "range_width_atr", "vol_ratio", "cons", "dow", "break_pips")


def vol_regime(epoch, a):
    """ATR relative to the median ATR of the trailing 30 days."""
    day = epoch // 86400
    udays, starts = np.unique(day, return_index=True)
    starts = np.append(starts, day.size)
    med = np.array([np.nanmedian(a[starts[k]:starts[k + 1]])
                    for k in range(udays.size)], dtype=float)
    out = np.full(a.size, np.nan)
    for k in range(udays.size):
        lo = max(0, k - 30)
        w = med[lo:k + 1]
        w = w[np.isfinite(w)]
        if w.size >= 10 and np.isfinite(med[k]) and med[k] > 0:
            sl = slice(starts[k], starts[k + 1])
            out[sl] = a[sl] / np.median(w)
    return out


def detect(s, win, kind, spacing):
    """Fresh range-break events. kind is 'break' (fade now) or 'fail' (wait)."""
    c, h, l = s.c, s.h, s.l
    n = c.size
    pip = s.pip
    w = np.lib.stride_tricks.sliding_window_view(h, win)
    wl = np.lib.stride_tricks.sliding_window_view(l, win)
    rmax = np.full(n, np.nan)
    rmin = np.full(n, np.nan)
    rmax[win:] = w[:n - win].max(axis=1)
    rmin[win:] = wl[:n - win].min(axis=1)
    a = atr(h, l, c, 14)
    vr = vol_regime(s.epoch, a)
    sma = np.full(n, np.nan)
    cs = np.cumsum(np.insert(c, 0, 0.0))
    sma[win:] = (cs[win:n] - cs[:n - win]) / win
    hours = ((s.epoch // 3600) % 24).astype(int)
    dows = ((s.epoch // 86400) + 4) % 7

    idx, dirs, feat = [], [], []
    last = -10 ** 9
    for i in range(win + 2, n - 2):
        if i - last < spacing:
            continue
        if not (np.isfinite(rmax[i]) and np.isfinite(a[i]) and a[i] > 0):
            continue
        up = c[i] > rmax[i] and c[i - 1] <= rmax[i]
        dn = c[i] < rmin[i] and c[i - 1] >= rmin[i]
        if not (up or dn):
            continue
        d = -1 if up else 1          # fade: sell the up-break, buy the down-break
        entry_i = i
        if kind == "fail":
            # require the break to be rejected: price closes back inside the range
            # within the next few bars, and enter on that close instead
            entry_i = -1
            for k in range(1, 5):
                j = i + k
                if j >= n - 2:
                    break
                if d < 0 and c[j] < rmax[i]:
                    entry_i = j
                    break
                if d > 0 and c[j] > rmin[i]:
                    entry_i = j
                    break
            if entry_i < 0:
                continue
        break_pips = (c[i] - rmax[i]) / pip if up else (rmin[i] - c[i]) / pip
        cons = 0
        k = i - 1
        while k > 0 and cons < 12:
            if up and c[k] > c[k - 1]:
                cons += 1
            elif dn and c[k] < c[k - 1]:
                cons += 1
            else:
                break
            k -= 1
        idx.append(entry_i)
        dirs.append(d)
        feat.append((
            hours[entry_i],
            break_pips / (a[i] / pip) if a[i] > 0 else np.nan,
            (h[i] - l[i]) / a[i],
            abs(c[i] - sma[i]) / a[i] if np.isfinite(sma[i]) else np.nan,
            (rmax[i] - rmin[i]) / a[i],
            vr[entry_i],
            cons,
            dows[entry_i],
            break_pips,
        ))
        last = entry_i
    return (np.array(idx, dtype=np.int64), np.array(dirs, dtype=np.int8),
            np.array(feat, dtype=float))


def collect(data_dir, symbols, win, kind, horizon, spacing):
    M, A, F, SP, T, SY, FI = [], [], [], [], [], [], []
    for sym in symbols:
        s = load_series(data_dir, sym, None, None)
        if s is None or s.c.size < 5000:
            continue
        idx, dirs, feat = detect(s, win, kind, spacing)
        if idx.size == 0:
            continue
        c, h, l = s.c, s.h, s.l
        pip = s.pip
        n = c.size
        mfe = np.full((idx.size, horizon), np.nan, dtype=np.float32)
        mae = np.full((idx.size, horizon), np.nan, dtype=np.float32)
        fin = np.full(idx.size, np.nan, dtype=np.float32)
        for j, (i, d) in enumerate(zip(idx, dirs)):
            end = min(i + horizon, n)
            if end - i < 3:
                continue
            if d > 0:
                f = (h[i + 1:end] - c[i]) / pip
                a = (l[i + 1:end] - c[i]) / pip
            else:
                f = (c[i] - l[i + 1:end]) / pip
                a = (c[i] - h[i + 1:end]) / pip
            wd = f.size
            mfe[j, :wd] = np.maximum.accumulate(f)
            mae[j, :wd] = np.minimum.accumulate(a)
            if wd < horizon:
                mfe[j, wd:] = mfe[j, wd - 1]
                mae[j, wd:] = mae[j, wd - 1]
            fin[j] = d * (c[end - 1] - c[i]) / pip
        ok = np.isfinite(fin)
        M.append(mfe[ok]); A.append(mae[ok]); F.append(feat[ok])
        FI.append(fin[ok])
        SP.append(np.where(np.isfinite(s.sp), s.sp, np.nan)[idx[ok]] / pip)
        T.append(s.epoch[idx[ok]])
        SY.append(np.array([sym] * int(ok.sum())))
    if not M:
        return None
    return {
        "mfe": np.vstack(M), "mae": np.vstack(A), "feat": np.vstack(F),
        "sp": np.concatenate(SP), "t": np.concatenate(T), "sym": np.concatenate(SY),
        "fin": np.concatenate(FI),
    }


def outcomes(mfe, mae, fin, T_, S_, cost):
    """Gross and net expectancy for one bracket."""
    climb = np.maximum.accumulate(mfe, axis=1)
    fall = np.maximum.accumulate(-mae, axis=1)
    it = climb >= T_
    is_ = fall >= S_
    ft = np.where(it.any(axis=1), it.argmax(axis=1), 10 ** 6)
    fs = np.where(is_.any(axis=1), is_.argmax(axis=1), 10 ** 6)
    won = ft < fs
    lost = fs <= ft
    open_ = ~(won | lost)
    gross = np.where(won, T_, np.where(lost, -S_, fin))
    net = gross - cost
    n = net.size
    sd = net.std(ddof=1) if n > 1 else 0.0
    return {
        "n": n, "gross": float(gross.mean()), "net": float(net.mean()),
        "hit": float(won.mean() * 100), "t": float(net.mean() / (sd / math.sqrt(n))) if sd > 0 else 0.0,
    }


def table(rows, label, key_name, key_fmt="{:>6.2f}"):
    print(f"\n  {label}")
    print(f"    {key_name:>10s} {'n':>6s} {'gross':>7s} {'hit%':>6s} {'g1':>7s} {'g2':>7s}  {'edge':>5s}")
    for k, r in rows:
        flag = ""
        if r["g1"] is not None and r["g2"] is not None and r["g1"] > 0 and r["g2"] > 0:
            flag = "BOTH"
        print(f"    {key_fmt.format(k):>10s} {r['n']:6d} {r['gross']:7.2f} {r['hit']:6.1f} "
              f"{(r['g1'] if r['g1'] is not None else float('nan')):7.2f} "
              f"{(r['g2'] if r['g2'] is not None else float('nan')):7.2f}  {flag:>5s}")


def scan(d, name, edges, T_, S_, cost, horizon):
    """Read one feature through the event pool, split by half."""
    v = d["feat"][:, FEATURES.index(name)]
    med = np.median(d["t"])
    h1 = d["t"] <= med
    rows = []
    for lo, hi in edges:
        m = np.isfinite(v) & (v >= lo) & (v < hi)
        if m.sum() < 60:
            continue
        full = outcomes(d["mfe"][m], d["mae"][m], d["fin"][m], T_, S_, cost)
        a = outcomes(d["mfe"][m & h1], d["mae"][m & h1], d["fin"][m & h1], T_, S_, cost)
        b = outcomes(d["mfe"][m & ~h1], d["mae"][m & ~h1], d["fin"][m & ~h1], T_, S_, cost)
        full["g1"] = a["gross"] if a["n"] >= 40 else None
        full["g2"] = b["gross"] if b["n"] >= 40 else None
        rows.append((lo, {**full, "lo": lo, "hi": hi}))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="candle_history_36m")
    ap.add_argument("--win", type=int, default=20)
    ap.add_argument("--horizon", type=int, default=48)
    ap.add_argument("--target", type=float, default=10.0)
    ap.add_argument("--stop", type=float, default=20.0)
    ap.add_argument("--cost", type=float, default=0.0)
    ap.add_argument("--kind", default="break,fail")
    ap.add_argument("--spacing", type=int, default=0,
                    help="minimum bars between events; 0 uses the horizon")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        data_dir = (Path.home() / ".config" / "tradebot-sci-gui" / "local"
                    / "data" / args.data_dir)
    symbols = sorted(p.name for p in data_dir.iterdir() if p.is_dir())
    print(f"[ENTRY] data={data_dir.name} pairs={len(symbols)} range={args.win} bars "
          f"horizon={args.horizon} bars bracket={args.target:.0f}/{args.stop:.0f} "
          f"cost={args.cost:.2f}")

    HOUR_EDGES = [(h, h + 1) for h in range(24)] + [(0, 24)]
    DOW_EDGES = [(d, d + 1) for d in range(7)]
    CONT = {
        "break_atr": [(0, .25), (.25, .5), (.5, .75), (.75, 1.0), (1.0, 1.5),
                      (1.5, 2.5), (2.5, 99)],
        "bar_range_atr": [(0, .5), (.5, .8), (.8, 1.2), (1.2, 2.0), (2.0, 99)],
        "stretch_atr": [(0, .5), (.5, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)],
        "range_width_atr": [(0, 1.5), (1.5, 2.5), (2.5, 4.0), (4.0, 99)],
        "break_pips": [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 5), (5, 99)],
        "vol_ratio": [(0, .7), (.7, .9), (.9, 1.1), (1.1, 1.4), (1.4, 99)],
        "cons": [(0, 1), (1, 2), (2, 3), (3, 5), (5, 13)],
    }

    n_tests = 0
    spacing = args.spacing or args.horizon
    for kind in args.kind.split(","):
        d = collect(data_dir, symbols, args.win, kind, args.horizon, spacing)
        if d is None:
            print(f"[ENTRY] {kind}: no events")
            continue
        base = outcomes(d["mfe"], d["mae"], d["fin"], args.target, args.stop, args.cost)
        print(f"\n{'=' * 74}")
        print(f"[ENTRY] kind={kind}  events={base['n']}  "
              f"median spread={np.nanmedian(d['sp']):.2f} pips")
        print(f"[ENTRY] unfiltered: gross={base['gross']:+.2f}p hit={base['hit']:.1f}% "
              f"net={base['net']:+.2f}p t={base['t']:+.2f}")
        print(f"{'=' * 74}")

        for name, edges in (("hour", HOUR_EDGES), ("dow", DOW_EDGES), *CONT.items()):
            rows = scan(d, name, edges, args.target, args.stop, args.cost, args.horizon)
            n_tests += len(rows)
            if name in ("hour", "dow"):
                table(rows, f"{name} all buckets", name, "{:>6.0f}")
            else:
                top = sorted(rows, key=lambda r: -r[1]["gross"])[:4]
                table(top, f"best {name} buckets by gross", name)
        print(f"\n  [ENTRY] hypotheses examined so far: {n_tests}")

    print("\n[ENTRY] gross is what the signal knows; net is what is left after the "
          "spread. A filter that is positive in only one half is noise regardless of "
          "how large its gross looks.")


if __name__ == "__main__":
    main()
