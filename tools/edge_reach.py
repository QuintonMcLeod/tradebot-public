#!/usr/bin/env python3
"""Reachability: can the one real edge be traded at a cost that exists?

Round one established that mean reversion after a 2-sigma stretch is genuine —
t=5.7, positive on 100% of pairs, stable across sample halves — and worth about
0.52 pips against a 1.6-pip spread. That leaves exactly one question: is there any
*configuration* whose edge exceeds the cost available in the hours it trades?

Two levers are tested together, because separately neither is enough:

- **Signal strength.** A 3-sigma stretch should pay more per trade than a 2-sigma
  one. If edge grows with stretch while cost stays fixed, a higher threshold can
  cross the line.
- **Session.** Spreads are not constant. The all-hours median is dominated by the
  Asian session and the rollover. London and New York hours carry materially
  tighter quotes, so a strategy that only trades then is charged less.

The grid is (stretch threshold) x (session) x (volatility regime) x (horizon), and
each cell is charged the spread actually quoted in its own symbol-hours rather than
a global average. Inference is clustered in time, halves are checked for sign
consistency, and the count of tested cells is printed so the significance bar can
be adjusted for it.

Usage:
    python3 tools/edge_reach.py
    python3 tools/edge_reach.py --horizons 12 --thresholds 2.0,2.5,3.0
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

from edge_research import load_series, sma, rolling_std, atr  # noqa: E402

BAR_SECONDS = 300
SESSIONS = {
    "all": (0, 24),
    "Asia 00-06": (0, 7),
    "London 07-11": (7, 12),
    "NY 12-16": (12, 17),
    "London+NY 07-16": (7, 17),
}
DEFAULT_SYMBOLS = ("EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,USDCAD,USDCHF,GBPJPY,EURJPY,"
                   "AUDJPY,EURAUD,EURCHF,GBPCHF,CADJPY,CHFJPY")


def session_spreads(s) -> dict[str, float]:
    """Median quoted spread per session, in pips, from the candles themselves."""
    hours = ((s.epoch // 3600) % 24).astype(int)
    pip = s.pip
    out = {}
    good = np.isfinite(s.sp) & (s.sp > 0)
    for name, (lo, hi) in SESSIONS.items():
        m = good & (hours >= lo) & (hours < hi)
        out[name] = float(np.median(s.sp[m])) / pip if m.sum() > 50 else float("nan")
    return out


def declustered_events(mask: np.ndarray, horizon: int) -> np.ndarray:
    """Keep at most one event per (symbol, non-overlapping window) to remove overlap."""
    idx = np.where(mask)[0]
    if idx.size == 0:
        return idx
    buckets = idx // horizon
    _, first = np.unique(buckets, return_index=True)
    return idx[np.sort(first)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Cost-reachability grid for the real intraday edge.")
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--thresholds", default="2.0,2.5,3.0")
    ap.add_argument("--horizons", default="12,48", help="M5 bars: 12 = 1h, 48 = 4h")
    ap.add_argument("--min-events", type=int, default=120)
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = DATA_DIR / args.data_dir

    thresholds = [float(t) for t in args.thresholds.split(",")]
    horizons = [int(h) for h in args.horizons.split(",")]

    # ── Load once, precompute per-symbol features ────────────────────────────
    prepared = []
    for sym in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
        s = load_series(data_dir, sym, None, None)
        if s is None:
            continue
        ma = sma(s.c, 20)
        sd = rolling_std(s.c, 20)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (s.c - ma) / sd
        a = atr(s.h, s.l, s.c, 14)
        pct = np.full(s.c.size, np.nan)
        ok = np.isfinite(a)
        if ok.sum() > 100:
            pct[ok] = np.argsort(np.argsort(a[ok])) / max(ok.sum() - 1, 1)
        fwds = {}
        for h in horizons:
            f = np.full(s.c.size, np.nan)
            f[:s.c.size - h] = (s.c[h:] - s.c[:s.c.size - h]) / s.pip
            fwds[h] = f
        hours = ((s.epoch // 3600) % 24).astype(int)
        spreads = session_spreads(s)
        prepared.append({"sym": sym, "s": s, "z": z, "pct": pct, "fwds": fwds,
                         "hours": hours, "spreads": spreads})

    if not prepared:
        print("No data loaded")
        return 1

    print(f"[REACH] {len(prepared)} pairs | {args.thresholds} sigma x "
          f"{list(SESSIONS)} sessions x vol regimes")
    print("\nMeasured spread by session (median of pair medians, pips):")
    print(f"{'session':18}" + "".join(f"{n:>10}" for n in SESSIONS))
    for name in SESSIONS:
        vals = [p["spreads"][name] for p in prepared if np.isfinite(p["spreads"][name])]
        if not vals:
            continue
    for name in SESSIONS:
        row = f"{name:18}"
        for p in prepared[:1]:
            pass
        med = [np.median([p["spreads"][name] for p in prepared
                          if np.isfinite(p["spreads"][name])]) for name in SESSIONS]
        break
    print(f"{'median':18}" + "".join(f"{v:>10.2f}" for v in med))

    rows = []
    for horizon in horizons:
        for thr in thresholds:
            for sess_name, (lo, hi) in SESSIONS.items():
                for regime, regime_mask_name in (("all vol", None), ("low vol", "low"), ("high vol", "high")):
                    ev_epochs, ev_pips, ev_cost, ev_dir = [], [], [], []
                    per_symbol = {}
                    for p in prepared:
                        s, z, pct, hours = p["s"], p["z"], p["pct"], p["hours"]
                        low = np.nan_to_num(pct, nan=0.5) < 0.3
                        high = np.nan_to_num(pct, nan=0.5) > 0.7
                        sess = (hours >= lo) & (hours < hi)
                        base = sess & np.isfinite(z)
                        if regime_mask_name == "low":
                            base &= low
                        elif regime_mask_name == "high":
                            base &= high
                        cost = p["spreads"][sess_name]
                        if not np.isfinite(cost):
                            continue
                        long_m = declustered_events(base & (z <= -thr), horizon)
                        short_m = declustered_events(base & (z >= thr), horizon)
                        for idx, direction in ((long_m, 1), (short_m, -1)):
                            if idx.size == 0:
                                continue
                            f = p["fwds"][horizon][idx]
                            ok = np.isfinite(f)
                            idx, f = idx[ok], f[ok]
                            if idx.size == 0:
                                continue
                            pips = f * direction
                            per_symbol.setdefault(p["sym"], []).append(pips.mean())
                            ev_epochs.append(s.epoch[idx])
                            ev_pips.append(pips)
                            ev_cost.append(np.full(idx.size, cost))
                    if not ev_epochs:
                        continue
                    epochs = np.concatenate(ev_epochs)
                    pips = np.concatenate(ev_pips)
                    costv = np.concatenate(ev_cost)
                    if pips.size < args.min_events:
                        continue
                    net = pips - costv
                    bucket = epochs // (BAR_SECONDS * horizon)
                    order = np.argsort(bucket)
                    bs, ns = bucket[order], net[order]
                    uniq, starts = np.unique(bs, return_index=True)
                    bmeans = np.add.reduceat(ns, starts) / np.diff(np.append(starts, ns.size))
                    sd = bmeans.std(ddof=1) if bmeans.size > 2 else 0.0
                    t = bmeans.mean() / (sd / math.sqrt(bmeans.size)) if sd else 0.0
                    mid = bmeans.size // 2
                    pos_syms = sum(1 for v in per_symbol.values() if np.mean(v) > 0)
                    rows.append({
                        "label": f"{thr}σ {sess_name} {regime} h{horizon}",
                        "n": int(pips.size), "clusters": int(bmeans.size),
                        "gross": float(pips.mean()), "cost": float(costv.mean()),
                        "net": float(net.mean()), "t": float(t),
                        "h1": float(bmeans[:mid].mean()) if mid else 0.0,
                        "h2": float(bmeans[mid:].mean()) if mid else 0.0,
                        "sym_pos": pos_syms / max(len(per_symbol), 1),
                    })

    rows.sort(key=lambda r: -r["net"])
    cells = len(rows)
    bar = 3.0 + math.log10(max(cells, 1))          # rough family-wise inflation
    print(f"\n{cells} cells tested; family-wise bar for this many tests is about |t|>{bar:.1f}")
    print(f"\n{'cell':38}{'n':>7}{'cl':>6}{'gross':>8}{'cost':>7}{'net':>8}{'t':>7}"
          f"{'h1':>7}{'h2':>7}{'+sym':>6}  verdict")
    print("-" * 104)
    for r in rows[:18]:
        if r["net"] <= 0:
            verdict = "cost exceeds edge"
        elif abs(r["t"]) < bar:
            verdict = "below bar"
        elif r["h1"] * r["h2"] <= 0:
            verdict = "one half only"
        elif r["sym_pos"] < 0.6:
            verdict = "not broad"
        else:
            verdict = "REACHABLE"
        print(f"{r['label']:38}{r['n']:>7}{r['clusters']:>6}{r['gross']:>8.2f}{r['cost']:>7.2f}"
              f"{r['net']:>8.2f}{r['t']:>7.2f}{r['h1']:>7.2f}{r['h2']:>7.2f}"
              f"{r['sym_pos']:>6.0%}  {verdict}")

    print("\ngross/cost/net are pips per trade; each cell is charged the spread quoted")
    print("in its own session. 'REACHABLE' requires a positive net beyond the family bar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
