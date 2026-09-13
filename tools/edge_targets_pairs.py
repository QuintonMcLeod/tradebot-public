#!/usr/bin/env python3
"""Per-pair breakdown of the one entry family that survived the target sweep.

The bracket sweep found the hour-20 fade of a fresh range break is the only entry
whose whole target grid stays profitable, and that it needs a multi-day hold rather
than an intraday one. Two questions decide whether that is worth anything:

1. Which pairs carry it? A portfolio average is an average of pairs that cost
   1.6 pips to trade and pairs that cost 3.4, so the cheap ones must be separated
   before the edge can be judged.
2. How much of the multi-day hold is paid away in financing? Five days of swap is
   a cost the bracket sweep never charged.

Usage:
    python3 tools/edge_targets_pairs.py
    python3 tools/edge_targets_pairs.py --horizon 5 --data-dir candle_history_36m
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

from edge_targets import declare, evaluate, BARS_PER_DAY  # noqa: E402

BRACKETS = ((40.0, 40.0), (30.0, 30.0), (50.0, 50.0), (35.0, 35.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="candle_history_36m")
    ap.add_argument("--rule", default="scrape_h20")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--cheap", type=float, default=2.0)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        data_dir = (Path.home() / ".config" / "tradebot-sci-gui" / "local"
                    / "data" / args.data_dir)
    symbols = sorted(p.name for p in data_dir.iterdir() if p.is_dir())

    print(f"[PAIRS] {args.rule} @ {args.horizon}d  data={data_dir.name}")
    print(f"[PAIRS] {'sym':8s} {'n':>5s} {'spread':>7s} {'gross':>7s} {'net':>7s} "
          f"{'hit%':>6s} {'t':>6s} {'half1':>7s} {'half2':>7s}")

    rows = []
    for sym in symbols:
        per = declare(args.rule, data_dir, (args.horizon,), [sym])
        d = per[args.horizon]
        if not d["mfe"].size or d["mfe"].shape[0] < 40:
            continue
        med = np.median(d["t"])
        out = {}
        for name, mask in (("all", np.ones(d["mfe"].shape[0], bool)),
                           ("h1", d["t"] <= med), ("h2", d["t"] > med)):
            sub = evaluate(d["mfe"][mask], d["mae"][mask], d["fin"][mask],
                           d["sp"][mask], [b[0] for b in BRACKETS],
                           [b[1] for b in BRACKETS])
            out[name] = {(r["T"], r["S"]): r for r in sub}
        key = BRACKETS[0]
        a = out["all"].get(key)
        if not a:
            continue
        b1 = out["h1"].get(key, {}).get("exp", float("nan"))
        b2 = out["h2"].get(key, {}).get("exp", float("nan"))
        rows.append({
            "sym": sym, "n": a["n"], "spread": a["cost"], "gross": a["gross"],
            "net": a["exp"], "hit": a["hit"], "t": a["t"], "h1": b1, "h2": b2,
            "brackets": out["all"],
        })
        print(f"[PAIRS] {sym:8s} {a['n']:5d} {a['cost']:7.2f} {a['gross']:7.2f} "
              f"{a['exp']:7.2f} {a['hit']:6.1f} {a['t']:6.2f} {b1:7.2f} {b2:7.2f}")

    if not rows:
        print("[PAIRS] no pairs produced enough trades")
        return

    print("\n[PAIRS] ranked by net at T=40/S=40")
    for r in sorted(rows, key=lambda r: -r["net"]):
        flag = "cheap" if r["spread"] <= args.cheap else "wide "
        print(f"  {r['sym']:8s} {flag}  spread={r['spread']:5.2f}  "
              f"gross={r['gross']:6.2f}  net={r['net']:6.2f}  "
              f"hit={r['hit']:5.1f}%  n={r['n']:4d}  halves {r['h1']:6.2f}/{r['h2']:6.2f}")

    def agg(subset, label):
        if not subset:
            return
        n = sum(r["n"] for r in subset)
        # trade-weighted mean of gross and net
        g = sum(r["gross"] * r["n"] for r in subset) / n
        e = sum(r["net"] * r["n"] for r in subset) / n
        sp = sum(r["spread"] * r["n"] for r in subset) / n
        hi = sum(r["hit"] * r["n"] for r in subset) / n
        sd = np.sqrt(sum(r["n"] * (r["net"] - e) ** 2 for r in subset) / max(n - 1, 1))
        t = e / (sd / math.sqrt(n)) if sd > 0 else 0.0
        pos = sum(1 for r in subset if r["net"] > 0)
        print(f"  {label:22s} pairs={len(subset):2d} n={n:5d} spread={sp:5.2f} "
              f"gross={g:6.2f} net={e:6.2f} hit={hi:5.1f}% t={t:5.2f} "
              f"positive pairs {pos}/{len(subset)}")

    print("\n[PAIRS] aggregate at T=40/S=40 (t uses between-pair variance, the "
          "conservative reading)")
    agg(rows, "all pairs")
    agg([r for r in rows if r["spread"] <= args.cheap], f"cheap (<= {args.cheap:.1f})")
    agg([r for r in rows if r["spread"] > args.cheap], "wide")

    print("\n[PAIRS] bracket robustness on the cheap subset")
    cheap = [r for r in rows if r["spread"] <= args.cheap]
    for T, S in BRACKETS:
        vals = [(r["brackets"].get((T, S)), r) for r in cheap]
        vals = [(v, r) for v, r in vals if v]
        if not vals:
            continue
        n = sum(v["n"] for v, _ in vals)
        e = sum(v["exp"] * v["n"] for v, _ in vals) / n
        g = sum(v["gross"] * v["n"] for v, _ in vals) / n
        pos = sum(1 for v, _ in vals if v["exp"] > 0)
        print(f"  T={T:4.0f} S={S:4.0f}  gross={g:6.2f}  net={e:6.2f}  "
              f"positive pairs {pos}/{len(vals)}  n={n}")


if __name__ == "__main__":
    main()
