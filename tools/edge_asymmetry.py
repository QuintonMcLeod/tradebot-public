#!/usr/bin/env python3
"""Payoff asymmetry: does a position in profit keep running, or give it back?

The most repeated piece of trading advice there is — cut losers, let winners run
— assumes that an open gain tends to grow. If that is true, trailing exits add
value and taking profit early destroys it. If it is false, the opposite holds.

Method: for every bar, take the move already travelled over the last N bars as a
proxy for unrealised profit, sort into buckets by its size in ATR, then measure
the next move in the same direction. A positive number means continuation (the
advice is right); a negative number means the position tends to give the move
back (the advice is wrong at that horizon).

Every result is net of half the quoted spread per side, because the test only
matters if it survives the cost of acting on it.

Usage:
    python3 tools/edge_asymmetry.py --hold 12
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

BUCKETS = [(-99, -3), (-3, -2), (-2, -1), (-1, -0.5), (-0.5, 0),
           (0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 99)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,USDCAD,USDCHF,GBPJPY,EURJPY")
    ap.add_argument("--lookback", type=int, default=12, help="Bars of travel used as the P&L proxy")
    ap.add_argument("--hold", type=int, default=12, help="Forward horizon in bars")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir

    rows = {b: {"vals": [], "keys": []} for b in BUCKETS}
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        s = load_series(data_dir, sym, None, None)
        if s is None:
            continue
        a = atr(s.h, s.l, s.c, 14)
        pip = s.pip
        travel = np.full(s.c.size, np.nan)
        travel[args.lookback:] = (s.c[args.lookback:] - s.c[:-args.lookback]) / pip
        with np.errstate(invalid="ignore", divide="ignore"):
            norm = travel / (a / pip)
        fwd = np.full(s.c.size, np.nan)
        h = args.hold
        fwd[:s.c.size - h] = (s.c[h:] - s.c[:s.c.size - h]) / pip
        cost = s.spread_pips()          # full round trip charged on the move
        good = np.isfinite(norm) & np.isfinite(fwd)
        idxs = np.where(good)[0]
        for i in idxs:
            n = norm[i]
            if not np.isfinite(n):
                continue
            for lo, hi in BUCKETS:
                if lo <= n < hi:
                    # Continuation in the direction already travelled: multiply
                    # by the travel's sign, never copysign(), which would discard
                    # the forward move's own sign and manufacture the result.
                    signed = (1.0 if n > 0 else -1.0) * fwd[i] - cost
                    rows[(lo, hi)]["vals"].append(signed)
                    rows[(lo, hi)]["keys"].append(int(s.epoch[i] // (300 * h)))
                    break

    print(f"[ASYM] travel over {args.lookback} bars -> next {args.hold} bars | "
          f"net of the round-trip spread | continuation in the direction travelled\n")
    print(f"{'travel bucket (ATR)':>22}{'n':>9}{'net pips':>10}{'t':>7}{'clusters':>10}  reading")
    print("-" * 74)
    for b in BUCKETS:
        vals = np.array(rows[b]["vals"])
        keys = np.array(rows[b]["keys"])
        if vals.size < 100:
            continue
        order = np.argsort(keys)
        ks, vs = keys[order], vals[order]
        uniq, starts = np.unique(ks, return_index=True)
        means = np.add.reduceat(vs, starts) / np.diff(np.append(starts, vs.size))
        sd = means.std(ddof=1) if means.size > 2 else 0.0
        t = means.mean() / (sd / math.sqrt(means.size)) if sd else 0.0
        if abs(t) < 3:
            reading = "no signal"
        elif means.mean() > 0:
            reading = "KEEPS RUNNING"
        else:
            reading = "gives it back"
        print(f"{b[0]:>10.1f} to {b[1]:>6.1f}{vals.size:>9}{vals.mean():>10.2f}"
              f"{t:>7.2f}{means.size:>10}  {reading}")
    print("\n'KEEPS RUNNING' on the positive buckets would support letting winners run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
