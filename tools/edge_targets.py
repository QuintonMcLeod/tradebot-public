#!/usr/bin/env python3
"""Can a large target survive the spread? Read the target from the MFE/MAE path.

Why this exists
---------------
The scrape experiment was killed by a cost ratio, not by a bad signal: a 10-pip
target against a 1.6-pip round trip hands the broker 16% of the trade before the
signal does anything. The obvious escape is a bigger target — at 30 pips the same
toll is 5.3%. But a bigger target is only worth having if price actually reaches
it often enough, and that is a measurable quantity, not an opinion.

This harness measures it the one way that settles the question: record each
trade's whole forward path, then ask what every target/stop bracket would have
returned on those exact paths, charged the spread that was really quoted at the
entry bar.

Method
------
1. For a set of price-action entries (prior-day break, 5-day break, volatility
   compression break, pullback in trend) plus the validated scrape rule as a
   control, find each occurrence on M5 bars.
2. Walk the path forward for the horizon with no exit applied, recording the
   running best and worst excursion. Because the extremes are monotone in bar
   index, the bar at which any target or stop would have filled is a binary
   search rather than a rescan — so the whole bracket grid comes free.
3. Charge each trade the spread quoted at its own entry bar, in pips. The data
   carries the real quote, so no flat assumption is imposed.
4. When both barriers fall inside one bar the stop is assumed to fill first.
   The intrabar sequence is unknowable from M5 data, and the alternative
   assumption flatters every result.

Discipline
----------
Entries are de-clustered at the horizon, so no two trades in a sample share a
bar. Every configuration is reported on both halves of the sample. The number of
brackets examined is printed, because 49 brackets on one sample will always
produce a pretty one by chance.

Usage:
    python3 tools/edge_targets.py --data-dir candle_history_36m
    python3 tools/edge_targets.py --data-dir candle_history_12m --symbols EURUSD,GBPUSD
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

from edge_research import load_series, pip_size  # noqa: E402

BARS_PER_DAY = 288
HOUR_BARS = 12
TARGETS = (10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0)
STOPS = (10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0)
HORIZONS = (1, 3, 5, 10)


def atr(h, l, c, n=14):
    """Wilder ATR over n bars."""
    prev = np.roll(c, 1)
    prev[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    out = np.full_like(tr, np.nan, dtype=float)
    if tr.size <= n:
        return out
    acc = tr[1:n + 1].mean()
    out[n] = acc
    for i in range(n + 1, tr.size):
        acc = (acc * (n - 1) + tr[i]) / n
        out[i] = acc
    return out


def day_levels(epoch, h, l):
    """Prior-day, prior-2-day and prior-5-day high/low, broadcast back to bars."""
    day = epoch // 86400
    udays, inv = np.unique(day, return_inverse=True)
    dhi = np.full(udays.size, -np.inf)
    dlo = np.full(udays.size, np.inf)
    np.maximum.at(dhi, inv, h)
    np.minimum.at(dlo, inv, l)

    n = udays.size
    pdh = np.full(n, np.nan)
    pdl = np.full(n, np.nan)
    h2 = np.full(n, np.nan)
    l2 = np.full(n, np.nan)
    h5 = np.full(n, np.nan)
    l5 = np.full(n, np.nan)
    for k in range(1, n):
        pdh[k] = dhi[k - 1]
        pdl[k] = dlo[k - 1]
        if k >= 2:
            h2[k] = dhi[k - 2:k].max()
            l2[k] = dlo[k - 2:k].min()
        if k >= 5:
            h5[k] = dhi[k - 5:k].max()
            l5[k] = dlo[k - 5:k].min()
    return pdh[inv], pdl[inv], h2[inv], l2[inv], h5[inv], l5[inv]


def bucket_levels(epoch, h, l, c):
    """Non-overlapping 12h bucket high/low, the prior bucket, and its median range."""
    b = np.arange(c.size) // (HOUR_BARS * 12)
    ub, binv = np.unique(b, return_inverse=True)
    bhi = np.full(ub.size, -np.inf)
    blo = np.full(ub.size, np.inf)
    np.maximum.at(bhi, binv, h)
    np.minimum.at(blo, binv, l)

    n = ub.size
    prev_hi = np.full(n, np.nan)
    prev_lo = np.full(n, np.nan)
    med_rng = np.full(n, np.nan)
    rng = bhi - blo
    for k in range(1, n):
        prev_hi[k] = bhi[k - 1]
        prev_lo[k] = blo[k - 1]
        lo = max(0, k - 60)
        if k - lo >= 10:
            med_rng[k] = np.median(rng[lo:k])
    return prev_hi[binv], prev_lo[binv], med_rng[binv]


def signals(s, rule):
    """Return (indices, directions) of entries for one rule."""
    fade_map = {"fade_prevday": "donchian_prevday",
                "fade_5day": "donchian_5day",
                "fade_compression": "compression_break"}
    flip = rule in fade_map
    if flip:
        rule = fade_map[rule]
    c, h, l = s.c, s.h, s.l
    n = c.size
    pip = s.pip
    idx: list[int] = []
    dirs: list[int] = []

    if rule in ("donchian_prevday", "donchian_5day"):
        pdh, pdl, h2, l2, h5, l5 = day_levels(s.epoch, h, l)
        up = pdh if rule == "donchian_prevday" else h5
        dn = pdl if rule == "donchian_prevday" else l5
        for i in range(6, n - 2):
            if not (np.isfinite(up[i]) and np.isfinite(dn[i])):
                continue
            if c[i] > up[i] and c[i - 1] <= up[i]:
                idx.append(i); dirs.append(1)
            elif c[i] < dn[i] and c[i - 1] >= dn[i]:
                idx.append(i); dirs.append(-1)

    elif rule == "compression_break":
        bhi, blo, med = bucket_levels(s.epoch, h, l, c)
        for i in range(6, n - 2):
            if not (np.isfinite(bhi[i]) and np.isfinite(med[i])):
                continue
            if (bhi[i] - blo[i]) >= 0.6 * med[i]:
                continue
            if c[i] > bhi[i] and c[i - 1] <= bhi[i]:
                idx.append(i); dirs.append(1)
            elif c[i] < blo[i] and c[i - 1] >= blo[i]:
                idx.append(i); dirs.append(-1)

    elif rule == "pullback_trend":
        pdh, pdl, h2, l2, h5, l5 = day_levels(s.epoch, h, l)
        a = atr(h, l, c, 14)
        for i in range(6, n - 2):
            if not (np.isfinite(h5[i]) and np.isfinite(a[i]) and a[i] > 0):
                continue
            # the 5-day extreme must have been touched within the last two days
            hi = h5[i]
            if h2[i] >= hi and (hi - c[i]) >= 0.8 * a[i] and c[i] > c[i - 1] >= c[i - 2]:
                idx.append(i); dirs.append(1)
                continue
            lo = l5[i]
            if l2[i] <= lo and (c[i] - lo) >= 0.8 * a[i] and c[i] < c[i - 1] <= c[i - 2]:
                idx.append(i); dirs.append(-1)

    elif rule == "scrape_h20":
        win = np.lib.stride_tricks.sliding_window_view(h, 20)
        rmax = np.full(n, np.nan)
        rmin = np.full(n, np.nan)
        rmax[20:] = win[:n - 20].max(axis=1)
        winl = np.lib.stride_tricks.sliding_window_view(l, 20)
        rmin[20:] = winl[:n - 20].min(axis=1)
        hours = ((s.epoch // 3600) % 24).astype(int)
        for i in range(21, n - 2):
            if hours[i] != 20:
                continue
            if not (np.isfinite(rmax[i]) and np.isfinite(rmin[i])):
                continue
            brk = max(c[i] - rmax[i], rmin[i] - c[i])
            if brk <= 0 or brk < 2.0 * pip:
                continue
            idx.append(i)
            dirs.append(-1 if c[i] > rmax[i] else 1)
    else:
        raise ValueError(rule)

    out_dirs = np.array(dirs, dtype=np.int8)
    if flip:
        out_dirs = -out_dirs
    return np.array(idx, dtype=np.int64), out_dirs


def paths(s, idx, dirs, hbars):
    """Running best/worst excursion in pips for each entry, plus entry spread."""
    c, h, l = s.c, s.h, s.l
    pip = s.pip
    n = c.size
    mfe = np.full((idx.size, hbars), np.nan, dtype=np.float32)
    mae = np.full((idx.size, hbars), np.nan, dtype=np.float32)
    fin = np.full(idx.size, np.nan, dtype=np.float32)
    for j, (i, d) in enumerate(zip(idx, dirs)):
        end = min(i + hbars, n)
        if end - i < 2:
            continue
        fin[j] = d * (c[end - 1] - c[i]) / pip
        if d > 0:
            f = (h[i + 1:end] - c[i]) / pip
            a = (l[i + 1:end] - c[i]) / pip
        else:
            f = (c[i] - l[i + 1:end]) / pip
            a = (c[i] - h[i + 1:end]) / pip
        width = f.size
        mfe[j, :width] = np.maximum.accumulate(f)
        mae[j, :width] = np.minimum.accumulate(a)
        if width < hbars:
            mfe[j, width:] = mfe[j, width - 1]
            mae[j, width:] = mae[j, width - 1]
    return mfe, mae, fin


def declare(rule, data_dir, horizons, symbols):
    """Collect de-clustered paths for one rule at several horizons."""
    print(f"\n[RULE] {rule}", flush=True)
    per_h = {hz: {"mfe": [], "mae": [], "fin": [], "sp": [], "t": []} for hz in horizons}
    for sym in symbols:
        s = load_series(data_dir, sym, None, None)
        if s is None or s.c.size < 5000:
            continue
        idx, dirs = signals(s, rule)
        if idx.size == 0:
            continue
        sp = np.where(np.isfinite(s.sp), s.sp, np.nan) / s.pip
        for hz in horizons:
            hbars = hz * BARS_PER_DAY
            keep, last = [], -10 ** 12
            for k, i in enumerate(idx):
                if i - last >= hbars and i + hbars < s.c.size:
                    keep.append(k)
                    last = i
            if not keep:
                continue
            kk = np.array(keep)
            mfe, mae, fin = paths(s, idx[kk], dirs[kk], hbars)
            ok = np.isfinite(mfe[:, -1]) & np.isfinite(mae[:, -1])
            per_h[hz]["mfe"].append(mfe[ok])
            per_h[hz]["mae"].append(mae[ok])
            per_h[hz]["fin"].append(fin[ok])
            per_h[hz]["sp"].append(sp[idx[kk][ok]])
            per_h[hz]["t"].append(s.epoch[idx[kk][ok]])
            per_h[hz].setdefault("sym", []).append(
                np.array([sym] * int(ok.sum()), dtype="U8"))
        print(f"  {sym}: {idx.size} raw signals", flush=True)
    for hz in horizons:
        d = per_h[hz]
        if not d["mfe"]:
            continue
        d["mfe"] = np.vstack(d["mfe"])
        d["mae"] = np.vstack(d["mae"])
        d["fin"] = np.concatenate(d["fin"])
        d["sp"] = np.concatenate(d["sp"])
        d["t"] = np.concatenate(d["t"])
        if d.get("sym"):
            d["sym"] = np.concatenate(d["sym"])
    return per_h


def evaluate(mfe, mae, fin, spread, targets, stops):
    """First-passage result for every bracket. Stop wins an intrabar tie."""
    rows = []
    climb = np.maximum.accumulate(mfe, axis=1)
    fall = np.maximum.accumulate(-mae, axis=1)
    for T in targets:
        hit_t = climb >= T
        any_t = hit_t.any(axis=1)
        first_t = np.where(any_t, hit_t.argmax(axis=1), 10 ** 6)
        for S in stops:
            hit_s = fall >= S
            any_s = hit_s.any(axis=1)
            first_s = np.where(any_s, hit_s.argmax(axis=1), 10 ** 6)
            won = first_t < first_s
            lost = first_s <= first_t
            open_ = ~(won | lost)
            # a bracket neither barrier reached is settled at the horizon close
            gross = np.where(won, T, np.where(lost, -S, fin))
            net = gross - spread
            n = net.size
            if n < 30:
                continue
            mean = float(net.mean())
            sd = float(net.std(ddof=1)) if n > 1 else 0.0
            t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
            rows.append({
                "T": T, "S": S, "n": n, "hit": float(won.mean() * 100.0),
                "exp": mean, "t": t, "gross": float(gross.mean()),
                "cost": float(spread.mean()), "unres": float(open_.mean() * 100.0),
            })
    return rows


def split_eval(mfe, mae, fin, spread, tstamp, targets, stops, label):
    """Evaluate on the full sample and on each half."""
    out = {"all": evaluate(mfe, mae, fin, spread, targets, stops)}
    med = np.median(tstamp)
    for name, mask in (("h1", tstamp <= med), ("h2", tstamp > med)):
        if mask.sum() >= 30:
            out[name] = evaluate(mfe[mask], mae[mask], fin[mask], spread[mask],
                                 targets, stops)
    out["_label"] = label
    return out


def show(cfg, label):
    full = cfg["all"]
    if not full:
        return
    big = [r for r in full if r["T"] >= 25.0]
    big.sort(key=lambda r: -r["exp"])
    med = np.median([r["t"] for r in full]) if full else 0.0
    pos = sum(1 for r in full if r["exp"] > 0)
    print(f"\n  {label}: {len(full)} brackets, {full[0]['n']} trades, "
          f"median spread {full[0]['cost']:.2f} pips")
    print(f"    positive brackets: {pos}/{len(full)}   "
          f"mean net across all brackets: {np.mean([r['exp'] for r in full]):6.2f}p")
    print(f"    median |t| across brackets: {abs(med):.2f}   "
          f"(with {len(full)} brackets tested, large t is expected by chance)")
    print("    best brackets with a 25-40 pip target:")
    print("      T     S     n    hit%    gross    net    t      half1     half2")
    for r in big[:8]:
        a = next((x["exp"] for x in cfg.get("h1", [])
                  if x["T"] == r["T"] and x["S"] == r["S"]), float("nan"))
        b = next((x["exp"] for x in cfg.get("h2", [])
                  if x["T"] == r["T"] and x["S"] == r["S"]), float("nan"))
        print(f"      {r['T']:4.0f}  {r['S']:4.0f}  {r['n']:5d}  {r['hit']:5.1f}  "
              f"{r['gross']:7.2f}  {r['exp']:6.2f}  {r['t']:5.2f}  "
              f"{a:7.2f}  {b:7.2f}")


def distribution(mfe, mae, label):
    print("    MFE percentiles (pips): ", end="")
    for p in (50, 60, 70, 80, 90, 95):
        print(f"p{p}={np.percentile(mfe[:, -1], p):5.1f}  ", end="")
    print()
    print("    MAE percentiles (pips): ", end="")
    for p in (50, 60, 70, 80, 90):
        print(f"p{p}={np.percentile(mae[:, -1], p):6.1f}  ", end="")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="candle_history_36m")
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--rules", default="donchian_prevday,donchian_5day,"
                                      "compression_break,pullback_trend,scrape_h20,"
                                      "fade_prevday,fade_5day,fade_compression")
    ap.add_argument("--horizons", default="1,3,5,10")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        data_dir = Path.home() / ".config" / "tradebot-sci-gui" / "local" / "data" / args.data_dir
    symbols = (args.symbols.split(",") if args.symbols
               else sorted(p.name for p in data_dir.iterdir() if p.is_dir()))
    horizons = tuple(int(x) for x in args.horizons.split(","))

    print(f"[TARGETS] data={data_dir} symbols={len(symbols)} horizons={horizons}")
    print(f"[TARGETS] brackets per rule/horizon: {len(TARGETS)}x{len(STOPS)}")
    print("[TARGETS] cost: real quoted spread at each entry bar; stop wins intrabar tie")

    summary = {}
    for rule in args.rules.split(","):
        per_h = declare(rule, data_dir, horizons, symbols)
        for hz in horizons:
            d = per_h[hz]
            if not d["mfe"].size:
                continue
            print(f"\n[HORIZON] {rule} {hz}d  trades={d['mfe'].shape[0]}")
            distribution(d["mfe"], d["mae"], rule)
            cfg = split_eval(d["mfe"], d["mae"], d["fin"], d["sp"], d["t"],
                             TARGETS, STOPS, f"{rule} {hz}d")
            show(cfg, f"{rule} {hz}d")
            summary[(rule, hz)] = cfg

    print("\n" + "=" * 78)
    print("[SUMMARY] every rule/horizon whose best 25-40 pip target is positive")
    print("=" * 78)
    ranked = []
    for (rule, hz), cfg in summary.items():
        full = cfg["all"]
        big = [r for r in full if r["T"] >= 25.0]
        if not big:
            continue
        best = max(big, key=lambda r: r["exp"])
        pos = sum(1 for r in full if r["exp"] > 0)
        ranked.append((pos / len(full), best["exp"], rule, hz, best, pos, len(full)))
    ranked.sort(reverse=True)
    print(f"  {'rule':20s} {'hz':>3s}  {'pos/49':>6s}  {'mean':>7s}  "
          f"{'best 25-40':>10s}  {'t':>6s}  {'halves':>14s}")
    for frac, exp, rule, hz, r, pos, tot in ranked:
        cfg = summary[(rule, hz)]
        a = next((x["exp"] for x in cfg.get("h1", [])
                  if x["T"] == r["T"] and x["S"] == r["S"]), float("nan"))
        b = next((x["exp"] for x in cfg.get("h2", [])
                  if x["T"] == r["T"] and x["S"] == r["S"]), float("nan"))
        mean = np.mean([x["exp"] for x in cfg["all"]])
        print(f"  {rule:20s} {hz:2d}d  {pos:3d}/{tot:<3d}  {mean:6.2f}p  "
              f"T{r['T']:3.0f}/S{r['S']:<3.0f}  {r['t']:6.2f}  "
              f"{a:6.2f}/{b:6.2f}")
    print("\n[TARGETS] 'pos/49' is the share of the whole target/stop grid that is "
          "profitable. One good cell is a coin flip; a positive surface is a signal.")
    print("[TARGETS] a positive number here is a hypothesis, not a finding: "
          "the halves and the t must agree before it earns a replay.")


if __name__ == "__main__":
    main()
