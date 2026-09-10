#!/usr/bin/env python3
"""Maker vs taker: can a better entry price rescue the real intraday pattern?

The intraday panel found a genuine, broad, stable effect — fading a 2-sigma
stretch earns about 0.25 pips, and 0.52 pips when volatility is low — and both
are smaller than the 1.6-pip spread a market order pays. So the question that
decides everything is whether entering as a *maker* changes the arithmetic.

Two things happen when you rest a limit order instead of taking the price:

1. You gain the offset: a buy limit D pips below the market fills at a better
   price than the close the signal fired on.
2. You suffer adverse selection: the limit only fills when price keeps coming,
   which is precisely the case where the pattern was wrong.

This measures both. For each signal event a limit is rested at close minus D
pips; if it fills within a short window the trade is taken at the limit price,
exited at market after the holding period, and the result is compared against
taking the trade immediately at the spread.

Reported per offset: fill rate, net pips per signal (unfilled counts as no trade),
net pips per filled trade, and a clustered t-statistic. Net pips per *signal* is
the number that matters — a strategy that fills 20% of the time with a great
price per fill can still be worse than one that always trades.

Usage:
    python3 tools/edge_maker.py --symbols EURUSD,GBPUSD,USDJPY --hold 12 --window 12
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

from edge_research import (  # noqa: E402
    load_series, sma, rolling_std, atr, day_index, hour_of,
)


def atr_percentile(s) -> np.ndarray:
    a = atr(s.h, s.l, s.c, 14)
    out = np.full(s.c.size, np.nan)
    good = np.isfinite(a)
    if good.sum() > 100:
        out[good] = np.argsort(np.argsort(a[good])) / max(good.sum() - 1, 1)
    return out


def signal_events(s, kind: str) -> tuple[list[int], list[int]]:
    """Indices of (long, short) signal bars."""
    c = s.c
    ma = sma(c, 20)
    sd = rolling_std(c, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - ma) / sd
    longs: list[int] = []
    shorts: list[int] = []
    if kind == "fade2":
        longs = list(np.where(np.isfinite(z) & (z <= -2.0))[0])
        shorts = list(np.where(np.isfinite(z) & (z >= 2.0))[0])
    elif kind == "fade2_lowvol":
        pct = atr_percentile(s)
        low = np.nan_to_num(pct, nan=0.5) < 0.2
        longs = list(np.where(np.isfinite(z) & (z <= -2.0) & low)[0])
        shorts = list(np.where(np.isfinite(z) & (z >= 2.0) & low)[0])
    return longs, shorts


def simulate(s, events, side: str, offsets_pips: list[float], hold: int, window: int,
             exit_is_maker: bool):
    """Return {offset: (per_signal_pips, per_fill_pips, cluster_keys, fill_flags)}."""
    pip = s.pip
    spread = s.spread_pips() * pip          # in price units
    half = spread / 2.0
    n = s.c.size
    out: dict[float, dict] = {}

    for off in offsets_pips:
        per_signal: list[float] = []
        per_fill: list[float] = []
        keys: list[int] = []
        fills = 0
        attempts = 0
        for i in events:
            if i + window + hold >= n:
                continue
            attempts += 1
            limit = s.c[i] - off * pip if side == "long" else s.c[i] + off * pip
            fill_idx = None
            for f in range(i + 1, i + window + 1):
                if side == "long" and s.l[f] <= limit:
                    fill_idx = f
                    break
                if side == "short" and s.h[f] >= limit:
                    fill_idx = f
                    break
            key = int(s.epoch[i] // (300 * max(hold, 1)))
            if fill_idx is None:
                per_signal.append(0.0)
                keys.append(key)
                continue
            k = fill_idx + hold
            if k >= n:
                per_signal.append(0.0)
                keys.append(key)
                continue
            exit_px = s.c[k] + half if (exit_is_maker and side == "long") else s.c[k]
            if side == "long":
                gross = exit_px - limit
                if not exit_is_maker:
                    gross -= half          # taker exit sells at the bid
            else:
                gross = limit - exit_px
                if not exit_is_maker:
                    gross -= half
            pips = gross / pip
            per_signal.append(pips)
            per_fill.append(pips)
            keys.append(key)
            fills += 1
        out[off] = {
            "per_signal": np.array(per_signal),
            "per_fill": np.array(per_fill),
            "keys": np.array(keys),
            "fill_rate": fills / attempts if attempts else 0.0,
            "attempts": attempts,
        }
    return out


def clustered_t(vals: np.ndarray, keys: np.ndarray) -> tuple[float, int, float]:
    if vals.size == 0:
        return 0.0, 0, 0.0
    uniq, starts = np.unique(keys, return_index=True)
    order = np.argsort(keys)
    ks = keys[order]
    vs = vals[order]
    uniq, starts = np.unique(ks, return_index=True)
    means = np.add.reduceat(vs, starts) / np.diff(np.append(starts, vs.size))
    if means.size < 5:
        return 0.0, int(means.size), float(means.mean())
    sd = means.std(ddof=1)
    t = means.mean() / (sd / math.sqrt(means.size)) if sd else 0.0
    return float(t), int(means.size), float(means.mean())


def main() -> int:
    ap = argparse.ArgumentParser(description="Maker vs taker entry test.")
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,AUDUSD,NZDUSD,USDCAD,USDCHF,GBPJPY,EURJPY")
    ap.add_argument("--hold", type=int, default=12, help="Holding period in M5 bars")
    ap.add_argument("--window", type=int, default=12, help="Bars a resting limit stays valid")
    ap.add_argument("--signal", default="fade2_lowvol", choices=["fade2", "fade2_lowvol"])
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = DATA_DIR / args.data_dir

    offsets = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0]
    agg = {off: {"sig": [], "fill": [], "keys": [], "attempts": 0, "fills": 0}
           for off in offsets}
    loaded = 0
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        s = load_series(data_dir, sym, None, None)
        if s is None:
            continue
        loaded += 1
        longs, shorts = signal_events(s, args.signal)
        for side, events in (("long", longs), ("short", shorts)):
            res = simulate(s, events, side, offsets, args.hold, args.window, exit_is_maker=False)
            for off, r in res.items():
                agg[off]["sig"].append(r["per_signal"])
                agg[off]["fill"].append(r["per_fill"])
                agg[off]["keys"].append(r["keys"])
                agg[off]["attempts"] += r["attempts"]
                agg[off]["fills"] += int(r["fill_rate"] * r["attempts"])

    if not loaded:
        print("No data")
        return 1

    print(f"[MAKER] signal={args.signal} | {loaded} pairs | hold {args.hold} bars "
          f"| limit valid {args.window} bars | exit at market (taker)")
    print(f"[MAKER] note: 'offset 0' is the baseline — a market order at the signal close\n")
    print(f"{'limit offset':>14}{'fill rate':>11}{'net/signal':>12}{'net/fill':>10}"
          f"{'t':>7}{'clusters':>10}{'trades':>8}  verdict")
    print("-" * 86)
    for off in offsets:
        sig = np.concatenate(agg[off]["sig"]) if agg[off]["sig"] else np.array([])
        fil = np.concatenate(agg[off]["fill"]) if agg[off]["fill"] else np.array([])
        keys = np.concatenate(agg[off]["keys"]) if agg[off]["keys"] else np.array([])
        if sig.size == 0:
            continue
        t, clusters, _ = clustered_t(sig, keys)
        per_sig = float(sig.mean())
        per_fill = float(fil.mean()) if fil.size else 0.0
        fill_rate = agg[off]["fills"] / agg[off]["attempts"] if agg[off]["attempts"] else 0.0
        if per_sig <= 0:
            verdict = "unprofitable"
        elif abs(t) < 3.0:
            verdict = "below bar"
        else:
            verdict = "CANDIDATE"
        print(f"{off:>13.2f}p{fill_rate:>10.0%}{per_sig:>12.2f}{per_fill:>10.2f}"
              f"{t:>7.2f}{clusters:>10}{agg[off]['fills']:>8}  {verdict}")

    print("\nnet/signal already charges the exit spread; offset 0 charges the full spread.")
    print("A maker entry only helps if net/signal rises above zero as the offset grows,")
    print("which requires the better price to outweigh the fills it loses to adverse selection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
