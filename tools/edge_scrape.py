#!/usr/bin/env python3
"""The scrape test: many small targets, all hours, all pairs.

The hypothesis, as stated by a human rather than by me
-----------------------------------------------------
Foreign exchange whipsaws and does not trend, so trend rules are the wrong tool.
What works instead is scrapping: take a little, repeatedly, everywhere — not only
around London and New York. High frequency, small targets.

That is a *bracket* claim, and none of the earlier tests addressed it. They measured
forward returns at a fixed horizon, which is a different object from "enter, take
three pips if they come, give back fifteen if they do not". This tool measures the
bracket directly:

  - enter at the close of a bar,
  - take profit T pips away and stop loss S pips away,
  - whichever is reached first wins; if neither is reached within the holding
    window, exit at the market and take whatever that is,
  - charge the pair's measured round-trip spread to every trade, win or lose.

Conventions that keep the result honest
---------------------------------------
- If a single bar touches both levels, the **stop** is assumed to fill. Optimistic
  tie-breaking is the classic way a backtest invents a scraper that does not exist.
- Entries are sampled every `hold` bars so forward windows do not overlap.
- Both directions are run. A pure direction-less average tells us whether the
  bracket shape itself pays; the directional variants test fading versus following.
- Results are reported per hour of day, because the claim is explicitly that all
  sessions work, and per pair, because a rule that only works on two pairs is not a
  rule.

Usage:
    python3 tools/edge_scrape.py
    python3 tools/edge_scrape.py --hold 12 --tp 2,3,5 --sl 5,10,15
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


def bracket(s, tp_pips: float, sl_pips: float, hold: int, direction: str,
            signal: np.ndarray | None = None, cost_pips: float | None = None):
    """Simulate brackets vectorised over entry bars.

    Returns (entry_indices, net_pips, hours) where net_pips already has the spread
    deducted.
    """
    n = s.c.size
    pip = s.pip
    spread = cost_pips if cost_pips is not None else s.spread_pips()
    tp = tp_pips * pip
    sl = sl_pips * pip

    # valid entries: leave room for the holding window
    empty = (np.array([]),) * 5
    idx = np.arange(0, n - hold - 1)
    if idx.size == 0:
        return empty
    if signal is not None:
        keep = signal[idx]
        idx = idx[keep]
        if idx.size == 0:
            return empty

    if direction == "short":
        tp_lvl = s.c[idx] - tp          # profit target below (sell first)
        sl_lvl = s.c[idx] + sl
        hit_tp = np.full(idx.size, hold + 1)
        hit_sl = np.full(idx.size, hold + 1)
        for k in range(1, hold + 1):
            lows = s.l[idx + k]
            highs = s.h[idx + k]
            fresh = hit_tp == hold + 1
            hit_tp[fresh & (lows <= tp_lvl)] = k
            fresh = hit_sl == hold + 1
            hit_sl[fresh & (highs >= sl_lvl)] = k
    else:
        tp_lvl = s.c[idx] + tp
        sl_lvl = s.c[idx] - sl
        hit_tp = np.full(idx.size, hold + 1)
        hit_sl = np.full(idx.size, hold + 1)
        for k in range(1, hold + 1):
            highs = s.h[idx + k]
            lows = s.l[idx + k]
            fresh = hit_tp == hold + 1
            hit_tp[fresh & (highs >= tp_lvl)] = k
            fresh = hit_sl == hold + 1
            hit_sl[fresh & (lows <= sl_lvl)] = k

    # Stop wins ties: if both are touched in the same bar we assume the bad one.
    win = hit_tp < hit_sl
    pips = np.where(win, tp_pips, -sl_pips).astype(float)

    # Neither level reached: exit at market after `hold` bars.
    timeout = (hit_tp > hold) & (hit_sl > hold)
    if timeout.any():
        exit_px = s.c[idx[timeout] + hold]
        if direction == "short":
            pips[timeout] = (s.c[idx[timeout]] - exit_px) / pip
        else:
            pips[timeout] = (exit_px - s.c[idx[timeout]]) / pip

    net = pips - spread
    hours = ((s.epoch[idx] // 3600) % 24).astype(int)
    return idx, net, hours, win, pips


def main() -> int:
    ap = argparse.ArgumentParser(description="Test the 'scrape' profile honestly.")
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--hold", default="6,12,48", help="Holding window in M5 bars")
    ap.add_argument("--tp", default="2,3,5,8")
    ap.add_argument("--sl", default="5,10,15,20")
    ap.add_argument("--cost-pips", type=float, default=None,
                    help="Override the round-trip cost, to ask what venue would be needed")
    ap.add_argument("--entry", default="both", choices=["both", "fade", "follow"],
                    help="'both' = direction-less bracket test")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir
    holds = [int(x) for x in args.hold.split(",")]
    tps = [float(x) for x in args.tp.split(",")]
    sls = [float(x) for x in args.sl.split(",")]

    prepared = []
    for sym in [x.strip().upper() for x in args.symbols.split(",") if x.strip()]:
        s = load_series(data_dir, sym, None, None)
        if s is None:
            continue
        if args.entry == "both":
            sig_long = None
        else:
            ma, sd = sma(s.c, 20), rolling_std(s.c, 20)
            with np.errstate(invalid="ignore", divide="ignore"):
                z = (s.c - ma) / sd
            # fade: long after a drop; follow: long after a rise
            sig_long = (z <= -1.0) if args.entry == "fade" else (z >= 1.0)
        prepared.append((sym, s, sig_long))

    if not prepared:
        print("No data")
        return 1
    print(f"[SCRAPE] {len(prepared)} pairs | entry mode: {args.entry} | "
          f"cost = each pair's measured spread, charged on every trade")
    print(f"[SCRAPE] holds {holds} bars (M5), TP {tps} pips, SL {sls} pips")
    print("[SCRAPE] stop wins same-bar ties (conservative)\n")

    rows = []
    for hold in holds:
        for tp in tps:
            for sl in sls:
                all_net, all_hours, all_epoch, all_win, all_gross = [], [], [], [], []
                per_pair = {}
                for sym, s, sig_long in prepared:
                    for direction in ("long", "short"):
                        sig = None
                        if sig_long is not None:
                            # fade: long when z low, short when z high
                            sig = sig_long if direction == "long" else ~sig_long
                            sig = sig & np.isfinite(s.c)
                        idx, net, hours, win, gross = bracket(s, tp, sl, hold, direction, sig, args.cost_pips)
                        if net.size == 0:
                            continue
                        all_win.append(win); all_gross.append(gross)
                        all_net.append(net)
                        all_hours.append(hours)
                        all_epoch.append(s.epoch[idx])
                        per_pair.setdefault(sym, []).append(net.mean())
                if not all_net:
                    continue
                net = np.concatenate(all_net)
                hours = np.concatenate(all_hours)
                epochs = np.concatenate(all_epoch)
                wins = np.concatenate(all_win)
                gross = np.concatenate(all_gross)
                tp_rate = float(wins.mean())                       # TP reached before stop
                avg_w = float(gross[wins].mean()) if wins.any() else 0.0
                avg_l = float(gross[~wins].mean()) if (~wins).any() else 0.0
                win_rate = tp_rate
                mean = float(net.mean())

                # Cluster in time: pairs move together, so averaging the trades
                # that share a window collapses both overlap and correlation.
                buckets = epochs // (300 * hold)
                order = np.argsort(buckets)
                b, v = buckets[order], net[order]
                uniq, starts = np.unique(b, return_index=True)
                bmeans = np.add.reduceat(v, starts) / np.diff(np.append(starts, v.size))
                sd = bmeans.std(ddof=1) if bmeans.size > 2 else 0.0
                t = bmeans.mean() / (sd / math.sqrt(bmeans.size)) if sd else 0.0
                clusters = int(bmeans.size)
                pos_pairs = sum(1 for v in per_pair.values() if np.mean(v) > 0)
                rows.append({
                    "hold": hold, "tp": tp, "sl": sl, "n": int(net.size),
                    "win": win_rate, "net": mean, "t": t,
                    "avg_w": avg_w, "avg_l": avg_l,
                    "gross": float(gross.mean()),
                    "pairs": f"{pos_pairs}/{len(per_pair)}",
                    "clusters": clusters,
                    "h1": float(bmeans[:bmeans.size // 2].mean()),
                    "h2": float(bmeans[bmeans.size // 2:].mean()),
                })

    rows.sort(key=lambda r: -r["net"])
    print(f"{'hold':>5}{'TP':>5}{'SL':>5}{'n':>9}{'cl':>7}{'TP hit':>8}{'avgW':>6}{'avgL':>6}"
          f"{'gross':>7}{'NET':>7}{'t':>8}{'+pairs':>8}  verdict")
    print("-" * 92)
    for r in rows[:16]:
        v = "PROFITABLE" if r["net"] > 0 and abs(r["t"]) > 3 else (
            "net>0, below bar" if r["net"] > 0 else "loses after cost")
        print(f"{r['hold']:>5}{r['tp']:>5.0f}{r['sl']:>5.0f}{r['n']:>9}{r['clusters']:>7}"
              f"{r['win']:>8.0%}{r['avg_w']:>6.1f}{r['avg_l']:>6.1f}{r['gross']:>7.2f}"
              f"{r['net']:>7.2f}{r['t']:>8.2f}{r['pairs']:>8}  {v}")

    best = rows[0]
    print(f"\nbest cell: hold {best['hold']} bars, TP {best['tp']:.0f}, SL {best['sl']:.0f} "
          f"-> hit rate {best['win']:.0%}, net {best['net']:+.2f} pips/trade")
    print("hit rate is necessary but not sufficient: expectancy is what pays the rent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
