#!/usr/bin/env python3
"""Time-series momentum across a diversified multi-asset basket.

Why this test
-------------
The FX work ended on a structural point: on that account the round trip costs about
as much as the average daily move, and no pattern in the tested families beat it.
That leaves an open question — is systematic trading hopeless, or is foreign
exchange the wrong market to ask?

Time-series momentum is the single most documented systematic strategy in
existence: long markets that have risen, short those that have fallen, sized by
volatility, spread across many uncorrelated markets. It has survived a century of
out-of-sample evidence across equities, bonds, commodities and currencies. If it
does not work on this basket either, the honest conclusion is that the earlier
failures were not an FX quirk. If it does work, the bot has been trading the wrong
instrument class.

What is measured
----------------
- Long/short trend with volatility targeting, rebalanced on a fixed schedule.
- A long-only variant, because the equity risk premium alone may explain the result.
- The reversal variant, as a control: someone always claims the opposite rule works.
- Buy-and-hold equal weight of the same basket, so any "edge" has to beat simply
  owning the markets rather than merely de-risking them.
- Cost sensitivity at 2, 5 and 10 basis points of turnover, and the sample split in
  half so the second half is genuinely out of sample.

Usage:
    python3 tools/edge_tsmom.py
    python3 tools/edge_tsmom.py --lookback 250 --hold 21 --cost-bps 5
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

TARGET_VOL = 0.10          # annualised portfolio volatility target
VOL_WINDOW = 60
MAX_LEVERAGE = 3.0
MAX_GROSS = 2.0            # cap on total notional exposure


def load_multi(multi_dir: Path):
    """Return (dates, labels, close matrix) using adjusted closes."""
    series: dict[str, dict[str, float]] = {}
    for path in sorted(multi_dir.glob("*.csv")):
        label = path.stem
        rows: dict[str, float] = {}
        with open(path) as fh:
            for r in csv.DictReader(fh):
                try:
                    rows[r["date"]] = float(r.get("adjclose") or r["close"])
                except (TypeError, ValueError):
                    continue
        if len(rows) > 500:
            series[label] = rows
    if not series:
        return None
    dates = sorted(set().union(*[set(v) for v in series.values()]))
    labels = sorted(series)
    m = np.full((len(dates), len(labels)), np.nan)
    idx = {d: i for i, d in enumerate(dates)}
    for j, lab in enumerate(labels):
        for d, c in series[lab].items():
            m[idx[d], j] = c
    return dates, labels, m


def monthly_t(daily: np.ndarray, hold: int = 21) -> tuple[float, int]:
    """t-statistic on NON-OVERLAPPING hold-period returns.

    A daily t-statistic on a strategy that holds positions for a month is
    optimistic, because consecutive daily returns are not independent draws.
    Collapsing to the actual decision period is the honest count.
    """
    x = daily[np.isfinite(daily)]
    if x.size < hold * 12:
        return 0.0, 0
    per = [np.prod(1.0 + x[i:i + hold]) - 1.0 for i in range(0, x.size - hold + 1, hold)]
    per = np.array(per)
    sd = per.std(ddof=1)
    if sd == 0:
        return 0.0, per.size
    return float(per.mean() / (sd / math.sqrt(per.size))), int(per.size)


def metrics(daily: np.ndarray, periods: int = 252) -> dict:
    x = daily[np.isfinite(daily)]
    if x.size < 60:
        return {}
    equity = np.cumprod(1.0 + x)
    years = x.size / periods
    cagr = equity[-1] ** (1 / years) - 1 if years > 0 and equity[-1] > 0 else float("nan")
    vol = x.std(ddof=1) * math.sqrt(periods)
    sharpe = (x.mean() * periods) / vol if vol else 0.0
    peak = np.maximum.accumulate(equity)
    dd = float((equity / peak - 1).min())
    t = x.mean() / (x.std(ddof=1) / math.sqrt(x.size)) if x.std(ddof=1) else 0.0
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "maxdd": dd,
            "t": t, "win": float((x > 0).mean())}


def run(m, labels, mode: str, lookback: int, hold: int, cost_bps: float,
        lo: int, hi: int) -> np.ndarray:
    """Daily portfolio returns for [lo, hi). mode: trend | trend_long | reversal | hold."""
    n_dates, n_markets = m.shape
    ret = np.full_like(m, np.nan)
    ret[1:] = m[1:] / m[:-1] - 1.0
    daily = np.full(n_dates, np.nan)
    w_prev = np.zeros(n_markets)
    cost = cost_bps / 1e4

    i = max(lo, lookback + VOL_WINDOW + 1)
    gross_sum = 0.0
    n_rebalances = 0
    while i < hi:
        # Sizing inputs, all from data available at i.
        vol = np.nanstd(ret[i - VOL_WINDOW:i], axis=0) * math.sqrt(252)
        past = m[i] / m[i - lookback] - 1.0
        available = np.isfinite(m[i]) & np.isfinite(past)
        n_act = int(available.sum())
        if n_act == 0:
            i += hold
            continue

        if mode == "hold":
            # Equal weight, unlevered: the honest benchmark.
            w = np.where(available, 1.0 / n_act, 0.0)
        else:
            # Volatility target: for n roughly uncorrelated positions each sized
            # to target_vol/vol_i, dividing by sqrt(n) makes the PORTFOLIO vol
            # approximate the target. Scaling by 1/1 (as an earlier version did)
            # levers the book by the number of markets.
            with np.errstate(invalid="ignore", divide="ignore"):
                unit = np.where(np.isfinite(vol) & (vol > 1e-6),
                                TARGET_VOL / vol, 0.0)
            unit = np.clip(unit, 0.0, MAX_LEVERAGE) / math.sqrt(n_act)
            sig = np.sign(np.nan_to_num(past, nan=0.0))
            if mode == "reversal":
                sig = -sig
            if mode == "trend_long":
                sig = np.where(sig > 0, 1.0, 0.0)
            w = np.where(available, sig * unit, 0.0)
            gross = np.abs(w).sum()
            if gross > MAX_GROSS:
                w = w * (MAX_GROSS / gross)
        gross_sum += np.abs(w).sum()
        n_rebalances += 1

        # Charge turnover once per rebalance.
        turn = np.abs(w - w_prev).sum()
        end = min(i + hold, hi)
        seg = ret[i:end]
        port = np.nansum(np.where(np.isfinite(seg), seg * w, 0.0), axis=1)
        if port.size and cost:
            port[0] -= turn * cost
        daily[i:end] = port
        w_prev = w
        i = end
    return daily[lo:hi], (gross_sum / n_rebalances if n_rebalances else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-asset time-series momentum.")
    ap.add_argument("--data-dir", default="multi")
    ap.add_argument("--lookback", type=int, default=250)
    ap.add_argument("--hold", type=int, default=21)
    ap.add_argument("--cost-bps", type=float, default=5.0)
    ap.add_argument("--sensitivity", action="store_true", help="Run the lookback x hold grid")
    ap.add_argument("--exclude", default=None, help="Comma list of markets to drop")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir
    loaded = load_multi(data_dir)
    if loaded is None:
        print("No data — run tools/fetch_multi.py")
        return 1
    dates, labels, m = loaded
    if args.exclude:
        drop = {x.strip().upper() for x in args.exclude.split(",")}
        keep = [j for j, lab in enumerate(labels) if lab not in drop]
        labels = [labels[j] for j in keep]
        m = m[:, keep]
    print(f"[TSMOM] {len(labels)} markets x {len(dates)} days ({dates[0]} to {dates[-1]})")
    print(f"[TSMOM] markets: {', '.join(labels)}")
    print(f"[TSMOM] lookback {args.lookback}d | rebalance {args.hold}d | "
          f"vol target {TARGET_VOL:.0%} | cost {args.cost_bps:.0f}bps per turnover\n")

    halved = len(dates) // 2
    eras = {"first half": (0, halved), "second half": (halved, len(dates))}

    print(f"{'strategy':26}{'era':13}{'CAGR':>8}{'vol':>7}{'Sharpe':>8}{'maxDD':>8}"
          f"{'t(monthly)':>11}{'n':>5}{'expo':>7}")
    print("-" * 95)
    for mode, name in (("trend", "trend long/short"),
                       ("trend_long", "trend long-only"),
                       ("reversal", "reversal (control)"),
                       ("hold", "buy/hold benchmark")):
        for era, (lo, hi) in eras.items():
            d, avg_gross = run(m, labels, mode, args.lookback, args.hold, args.cost_bps, lo, hi)
            r = metrics(d)
            if not r:
                continue
            tm, nper = monthly_t(d, args.hold)
            print(f"{name:26}{era:13}{r['cagr']:>7.1%}{r['vol']:>7.1%}{r['sharpe']:>8.2f}"
                  f"{r['maxdd']:>8.1%}{tm:>11.2f}{nper:>5}{avg_gross:>7.2f}")

    if args.sensitivity:
        print("\nparameter sensitivity (Sharpe by lookback x rebalance, full sample):")
        print(f"{'lookback':>10}" + "".join(f"{f'hold {h}':>12}" for h in (5, 21, 63)))
        for look in (60, 120, 250):
            row = f"{look:>10}"
            for h in (5, 21, 63):
                d, _ = run(m, labels, "trend_long", look, h, args.cost_bps, 0, len(dates))
                r = metrics(d)
                row += f"{r['sharpe']:>12.2f}" if r else f"{'-':>12}"
            print(row)

    print(f"\ncost sensitivity (full sample, trend long/short):")
    for c in (0.0, 2.0, 5.0, 10.0, 20.0):
        d, _ = run(m, labels, "trend", args.lookback, args.hold, c, 0, len(dates))
        r = metrics(d)
        if r:
            print(f"   {c:>5.0f} bps: CAGR {r['cagr']:>6.1%}  Sharpe {r['sharpe']:>5.2f}  "
                  f"maxDD {r['maxdd']:>6.1%}")

    print("\nThe benchmark row is the one that matters: a trend rule that merely owns")
    print("less risk is not an edge. It has to beat buy-and-hold on Sharpe in BOTH halves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
