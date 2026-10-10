#!/usr/bin/env python3
"""Does placing the stop relative to market structure beat a flat stop?

Why this exists
---------------
`forex_scrape_fade` places its stop at a flat `entry -/+ 20 pips`. Stop WIDTH has
been swept (10/15/20/25/30 flat), but the stop has never been placed relative to
the level the entry actually trades against. One live loss is attributed to
exactly that: the stop sat ON the obvious consolidation high, at the level every
other participant could see, and was swept before price turned. The live record's
one surviving trade put its stop *beyond* the same kind of level and lived.

The untested question is therefore not "how wide" but "where": given the same
entry and the same target, does a stop placed just beyond a structural reference
do better than a stop placed a fixed distance from the entry?

Two entry types, because the structural reference is different for each
------------------------------------------------------------------------
break  The deployed rule. Fade a fresh close outside the prior 20-bar range, so
       entry is BEYOND the broken level and that level sits behind the trade. The
       only reference still ahead of such an entry is the extreme the break bar
       itself reached, so the stop goes beyond `h[i]` (short) or `l[i]` (long).
fail   The retest entry the live agent actually traded (sell a break that has
       closed back inside the range). Here the broken level is ahead of the entry
       and the stop goes beyond `rmax[i]` (short) or `rmin[i]` (long). This is the
       geometry of the swept stop.

Method
------
Reuses tools/edge_entry.detect with the hour-20 and break-depth filters from
tools/edge_cost_check.py, de-clustered at a 24-hour horizon inside each symbol.
Every stop candidate charges each trade its own quoted spread, and is reported
with a plain t, a t clustered on 24-hour time buckets, and a first/second half
split. Mean and median widths are printed for every cell: a structure stop and a
flat stop with different widths are not comparing placement. If a structure cell
only wins at a wider width, that is the width result again, not a placement one.

A guard, learned the hard way
-----------------------------
If a stop width is not strictly positive the barrier is already "hit" at bar 0 and
the trade books `-stop` as a PROFIT. The first version of this script computed the
broken level for a break entry, which is behind the entry, and produced a
structure+0p cell at +1.98 pips and clustered t=+4.84 - a number that would have
cleared the |t|>3 bar and been reported as a finding. It was measuring the sign of
a negative barrier. `outcome()` asserts the width is positive.

Caveats: financing is not charged (tools/edge_cost_check.py omits it too), and the
conservative "stop wins ties" rule is used.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from edge_entry import detect  # noqa: E402
from edge_research import load_series  # noqa: E402

DEFAULT_DATA = Path.home() / ".config" / "tradebot-sci-gui" / "local" / "data"

WIN = 20          # prior-range lookback, matches detect and edge_cost_check
HOUR = 20         # the only hour the rule trades, UTC
HORIZON = 288     # 24 hours of M5 bars
SPACING = 288     # non-overlapping windows, applied inside the filtered subset
TARGET = 15.0     # the deployed target

FLAT_WIDTHS = (10.0, 15.0, 20.0, 25.0, 30.0)
BUFFERS = (0.0, 2.0, 4.0, 6.0, 8.0, 12.0, 15.0)
MIN_WIDTH = 1.0   # a sub-pip stop is not a tradeable bracket; floor and say so

DATASETS = (
    ("candle_history_36m", 2.0, "15 pairs, 3 years"),
    ("candle_history_12m", 2.0, "26 pairs, 12 months"),
)


def _extremes(h: np.ndarray, l: np.ndarray, win: int) -> tuple[np.ndarray, np.ndarray]:
    """Prior-range high/low, the same window detect compares the close against."""
    n = h.size
    w = np.lib.stride_tricks.sliding_window_view(h, win)
    wl = np.lib.stride_tricks.sliding_window_view(l, win)
    rmax = np.full(n, np.nan)
    rmin = np.full(n, np.nan)
    rmax[win:] = w[:n - win].max(axis=1)
    rmin[win:] = wl[:n - win].min(axis=1)
    return rmax, rmin


def _break_bars(c: np.ndarray, rmax: np.ndarray, rmin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar break flag (-1 up, +1 down, 0 none) and the level that was broken."""
    n = c.size
    flag = np.zeros(n, dtype=np.int8)
    level = np.full(n, np.nan)
    with np.errstate(invalid="ignore"):
        up = (c[1:] > rmax[1:]) & (c[:-1] <= rmax[1:])
        dn = (c[1:] < rmin[1:]) & (c[:-1] >= rmin[1:])
    flag[1:][up] = -1
    flag[1:][dn] = 1
    level[1:][up] = rmax[1:][up]
    level[1:][dn] = rmin[1:][dn]
    return flag, level


def build(data_dir: Path, min_depth: float, kind: str,
          horizon: int = HORIZON, spacing: int = SPACING) -> list[dict]:
    """Filtered fade events, each carrying its structural stop reference price."""
    events: list[dict] = []
    for symbol in sorted(p.name for p in data_dir.iterdir() if p.is_dir()):
        series = load_series(data_dir, symbol, None, None)
        if series is None or series.c.size < 5000:
            continue

        idx, dirs, feat = detect(series, WIN, kind, 1)  # no thinning yet
        c, h, l, pip = series.c, series.h, series.l, series.pip
        n = c.size
        rmax, rmin = _extremes(h, l, WIN)
        bflag, blevel = _break_bars(c, rmax, rmin)

        selected = [j for j in range(idx.size)
                    if feat[j, 0] == HOUR and feat[j, 8] >= min_depth]
        selected.sort(key=lambda j: idx[j])

        last = -(10 ** 9)
        for j in selected:
            e, d = int(idx[j]), int(dirs[j])
            if e - last < spacing:      # de-cluster inside the filtered subset
                continue
            end = min(e + horizon, n)
            if end - e < 3:
                continue

            if kind == "fail":
                # Recover the break bar this failure belongs to and its level.
                ref = np.nan
                for i in range(e - 1, max(e - 5, WIN), -1):
                    if bflag[i] == d:
                        ref = blevel[i]
                        break
                if not np.isfinite(ref):
                    continue
            else:
                # Break entry: entry is beyond the broken level, so the only
                # reference ahead of it is the extreme the break bar reached.
                # A short fade (d < 0) of an up-break stops above h[e]; a long
                # fade (d > 0) of a down-break stops below l[e].
                ref = h[e] if d < 0 else l[e]

            last = e
            if d > 0:
                favourable = (h[e + 1:end] - c[e]) / pip
                adverse = (l[e + 1:end] - c[e]) / pip
                width0 = (c[e] - ref) / pip     # stop below ref: long
            else:
                favourable = (c[e] - l[e + 1:end]) / pip
                adverse = (c[e] - h[e + 1:end]) / pip
                width0 = (ref - c[e]) / pip     # stop above ref: short

            if not np.isfinite(width0):
                continue

            events.append(dict(
                mfe=np.maximum.accumulate(favourable) if favourable.size else np.array([0.0]),
                mae=np.minimum.accumulate(adverse) if adverse.size else np.array([0.0]),
                fin=d * (c[end - 1] - c[e]) / pip,
                spread=(series.sp[e] / pip) if np.isfinite(series.sp[e]) else 0.0,
                epoch=int(series.epoch[e]),
                width0=float(width0),
            ))
    return events


def outcome(e: dict, target: float, stop: float) -> float:
    """Signed pips, stop winning ties as in edge_entry.outcomes."""
    assert stop > 0, f"non-positive stop width {stop!r} books the barrier as profit"
    hit_t = np.flatnonzero(e["mfe"] >= target)
    hit_s = np.flatnonzero(-e["mae"] >= stop)
    first_t = hit_t[0] if hit_t.size else 10 ** 6
    first_s = hit_s[0] if hit_s.size else 10 ** 6
    if first_t < first_s:
        return target
    if first_s <= first_t:
        return -stop
    return e["fin"]


def _t(x: np.ndarray) -> float:
    sd = x.std(ddof=1) if x.size > 1 else 0.0
    return float(x.mean() / (sd / math.sqrt(x.size))) if sd > 0 else 0.0


def clustered(vals: np.ndarray, epochs: np.ndarray) -> tuple[float, int]:
    """t on 24-hour buckets: pairs breaking together count as one observation."""
    buckets = epochs // (300 * HORIZON)
    order = np.argsort(buckets)
    b, v = buckets[order], vals[order]
    uniq, starts = np.unique(b, return_index=True)
    means = np.add.reduceat(v, starts) / np.diff(np.append(starts, v.size))
    sd = means.std(ddof=1) if means.size > 2 else 0.0
    t = means.mean() / (sd / math.sqrt(means.size)) if sd else 0.0
    return float(t), int(means.size)


def cell(events: list[dict], widths: np.ndarray, label: str) -> dict:
    raw = widths
    widths = np.maximum(widths, MIN_WIDTH)
    gross = np.array([outcome(e, TARGET, w) for e, w in zip(events, widths)])
    spreads = np.array([e["spread"] for e in events])
    epochs = np.array([e["epoch"] for e in events])
    net = gross - spreads

    split = np.median(epochs)
    first, second = net[epochs <= split], net[epochs > split]
    tc, nc = clustered(net, epochs)
    stopped = float(np.mean([outcome(e, TARGET, w) == -w
                             for e, w in zip(events, widths)]))

    return dict(label=label, n=net.size, width=float(widths.mean()),
                width_med=float(np.median(widths)), net=float(net.mean()),
                t=_t(net), tc=tc, clusters=nc, stopped=stopped,
                floored=int((raw < MIN_WIDTH).sum()),
                fh=float(first.mean()) if first.size else float("nan"),
                sh=float(second.mean()) if second.size else float("nan"))


def show(rows: list[dict]) -> None:
    print(f"{'stop rule':<26}{'n':>6}{'width':>7}{'medW':>7}{'stop%':>7}{'net':>8}"
          f"{'t':>7}{'t_cl':>7}{'cl':>5}{'1st':>8}{'2nd':>8}{'floor':>7}")
    print("-" * 102)
    for r in rows:
        print(f"{r['label']:<26}{r['n']:>6}{r['width']:>7.1f}{r['width_med']:>7.1f}"
              f"{100*r['stopped']:>6.0f}%{r['net']:>+8.2f}{r['t']:>+7.2f}{r['tc']:>+7.2f}"
              f"{r['clusters']:>5}{r['fh']:>+8.2f}{r['sh']:>+8.2f}{r['floored']:>7}")


def run(data_dir: Path, min_depth: float, label: str, kind: str) -> None:
    events = build(data_dir, min_depth, kind)
    if not events:
        print(f"\n{label} [{kind}]: no events")
        return

    spreads = np.array([e["spread"] for e in events])
    w0 = np.array([e["width0"] for e in events])
    print(f"\n{label} [{kind} entry]  dataset={data_dir.name}  n={len(events)}  "
          f"target={TARGET:.0f}  hour={HOUR}  depth>={min_depth:.0f}p  hold={HORIZON} bars")
    print(f"  own quoted spread: mean={spreads.mean():.2f} median={np.median(spreads):.2f} pips")
    print(f"  distance entry->structural reference: mean={w0.mean():.2f} "
          f"median={np.median(w0):.2f} p10={np.percentile(w0, 10):.2f} "
          f"p90={np.percentile(w0, 90):.2f} pips")
    print(f"  structural widths below {MIN_WIDTH:.0f}p are floored at {MIN_WIDTH:.0f}p "
          f"({int((w0 < MIN_WIDTH).sum())} of {w0.size} events at buffer 0)")

    print()
    show([cell(events, np.full(len(events), w), f"flat {w:.0f}p") for w in FLAT_WIDTHS])
    print()
    show([cell(events, w0 + b, f"structure + {b:.0f}p buffer") for b in BUFFERS])


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=("break", "fail", "both"), default="both")
    ap.add_argument("--dataset", choices=("36m", "12m", "both"), default="both")
    args = ap.parse_args()

    kinds = ("break", "fail") if args.kind == "both" else (args.kind,)
    print("[STOP-PLACEMENT] flat stop width vs stop referenced to market structure")
    print("[STOP-PLACEMENT] bar for a finding: |t| > 3 on independent (24h) clusters")
    for name, depth, label in DATASETS:
        if args.dataset != "both" and not name.endswith(args.dataset):
            continue
        data_dir = DEFAULT_DATA / name
        if not data_dir.is_dir():
            print(f"\n{label}: missing {data_dir}")
            continue
        for kind in kinds:
            run(data_dir, depth, label, kind)
    print("\n[STOP-PLACEMENT] A structure cell only counts against a flat cell of the "
          "same median width; otherwise the width result is read as placement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
