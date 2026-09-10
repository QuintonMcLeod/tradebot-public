#!/usr/bin/env python3
"""Carry factor test with real interest rates.

Carry is the interest differential between the two legs of a pair: long AUDJPY
earns the AUD rate and pays the JPY rate. It is the best-documented factor in
foreign exchange, and the earlier static high-yield basket was not a fair test of
it — a fixed basket is a bet on particular currencies, not on carry.

What is measured here
---------------------
1. Cross-sectional carry: rank all pairs by their carry each month, go long the
   highest and short the lowest, rebalance monthly.
2. Monotonicity: mean return per carry quintile. A real factor rises across the
   quintiles; a lucky one pops in a single bucket.
3. Time-series carry: long every pair with positive carry, short every negative.
4. Accrual split: results are shown with and without the interest accrual itself,
   because a retail account receives financing at a marked-down rate — so the
   spot-only column is the pessimistic read.

Discipline
----------
- Rates are lagged a month, so nothing uses a figure that was not yet published.
- Periods are non-overlapping months; the t-statistic is computed across months.
- Results are reported for 2013-2019 and 2020-2026 separately, which is the
  out-of-sample check: the factor has to show up in both eras to count.

Usage:
    python3 tools/edge_carry.py
    python3 tools/edge_carry.py --quintiles --split 2020-01-01
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from edge_daily import load_panel, measured_spreads, pip_size, DEFAULT_SPREAD_PIPS  # noqa: E402


def load_rates(rate_dir: Path, currencies: set[str]) -> dict[str, dict[str, float]]:
    """Return {currency: {'YYYY-MM': rate_pct}}."""
    out: dict[str, dict[str, float]] = {}
    for ccy in sorted(currencies):
        path = rate_dir / f"{ccy}.csv"
        if not path.exists():
            continue
        series: dict[str, float] = {}
        with open(path) as fh:
            for row in csv.DictReader(fh):
                series[row["date"][:7]] = float(row["rate_pct"])
        if series:
            out[ccy] = series
    return out


def rate_at(rates: dict[str, dict[str, float]], ccy: str, month: str, lag_months: int = 1) -> float | None:
    """Rate for a currency as of `month`, lagged so only published data is used."""
    series = rates.get(ccy)
    if not series:
        return None
    y, m = int(month[:4]), int(month[5:7])
    for _ in range(lag_months + 6):        # walk back until a value exists
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        key = f"{y:04d}-{m:02d}"
        if key in series:
            return series[key]
    return None


def carry_matrix(dates: list[str], syms: list[str], rates: dict[str, dict[str, float]]) -> np.ndarray:
    """Annualised carry in percent, per date per pair."""
    out = np.full((len(dates), len(syms)), np.nan)
    cache: dict[tuple[str, str], float | None] = {}
    for i, d in enumerate(dates):
        month = d[:7]
        for j, sym in enumerate(syms):
            base, quote = sym[:3], sym[3:]
            key = (month, sym)
            if key not in cache:
                b = rate_at(rates, base, month)
                q = rate_at(rates, quote, month)
                cache[key] = None if b is None or q is None else b - q
            out[i, j] = cache[key] if cache[key] is not None else np.nan
    return out


def summarise(returns: np.ndarray, label: str, periods_per_year: int) -> dict:
    x = returns[np.isfinite(returns)]
    if x.size < 12:
        return {}
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    t = mean / (sd / math.sqrt(x.size)) if sd else 0.0
    half = x.size // 2
    return {"label": label, "n": int(x.size), "bps": mean * 1e4, "t": t,
            "ann_pct": mean * periods_per_year * 100,
            "h1": float(x[:half].mean()) * 1e4, "h2": float(x[half:].mean()) * 1e4,
            "win": float((x > 0).mean())}


def print_block(title: str, rows: list[dict]) -> None:
    print(f"\n{title}")
    print(f"{'portfolio':40}{'n':>5}{'bps/mo':>9}{'t':>7}{'ann%':>8}{'h1':>8}{'h2':>8}{'win':>7}  verdict")
    print("-" * 100)
    for r in rows:
        if abs(r["t"]) < 3.0:
            verdict = "below bar"
        elif r["h1"] * r["h2"] <= 0:
            verdict = "one era only"
        elif r["ann_pct"] <= 0:
            verdict = "eaten by cost"
        else:
            verdict = "CANDIDATE"
        print(f"{r['label']:40}{r['n']:>5}{r['bps']:>9.1f}{r['t']:>7.2f}{r['ann_pct']:>8.2f}"
              f"{r['h1']:>8.1f}{r['h2']:>8.1f}{r['win']:>7.0%}  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Carry factor test on real rate history.")
    ap.add_argument("--data-dir", default="candle_history_daily")
    ap.add_argument("--hold", type=int, default=21, help="Holding period in trading days")
    ap.add_argument("--split", default="2020-01-01", help="Train/test era boundary")
    ap.add_argument("--quintiles", action="store_true", help="Print the quintile ladder")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir
    rate_dir = DATA_DIR / "rates"
    if not data_dir.is_dir() or not rate_dir.is_dir():
        print("Missing candle or rate data")
        return 1

    symbols = sorted({p.name.split("_")[0] for p in data_dir.glob("*_D.jsonl")})
    panel = load_panel(data_dir, "D", symbols)
    if panel is None:
        print("Panel empty")
        return 1
    dates, syms, closes = panel

    currencies = {s[:3] for s in syms} | {s[3:] for s in syms}
    rates = load_rates(rate_dir, currencies)
    print(f"[CARRY] {len(syms)} pairs x {len(dates)} days ({dates[0]} to {dates[-1]})")
    print(f"[CARRY] rate series loaded for: {', '.join(sorted(rates))}")

    carry = carry_matrix(dates, syms, rates)
    coverage = float(np.isfinite(carry).mean())
    print(f"[CARRY] carry available on {coverage:.1%} of pair-days\n")
    if coverage < 0.5:
        print("Too little rate coverage to test carry.")
        return 1

    spreads = measured_spreads(DATA_DIR / "candle_history_12m")
    avg_price = np.nanmean(closes, axis=0)
    cost = np.array([(spreads.get(s, DEFAULT_SPREAD_PIPS) * pip_size(s)) / avg_price[j]
                     for j, s in enumerate(syms)])

    hold = args.hold
    grid = np.arange(0, len(dates) - hold, hold)
    split_idx = next((i for i, d in enumerate(dates) if d >= args.split), len(dates) // 2)

    def period_return(i: int, w: np.ndarray, include_accrual: bool) -> float:
        """Return over [i, i+hold) for weights w, net of one round trip per name."""
        w = np.nan_to_num(w, nan=0.0)
        gross = np.abs(w).sum()
        if gross <= 0:
            return np.nan
        spot = np.where(np.isfinite(closes[i + hold]) & np.isfinite(closes[i]),
                        closes[i + hold] / closes[i] - 1.0, 0.0)
        accr = np.zeros(len(syms))
        if include_accrual:
            days = hold
            accr = np.nan_to_num(carry[i], nan=0.0) / 100.0 * days / 365.0
        pnl = float((w * (spot + accr)).sum() / gross)
        fee = float((np.abs(w) * cost).sum() / gross)
        return pnl - fee

    def run(make_weights, include_accrual: bool, label: str, era: str) -> dict:
        vals = []
        for i in grid:
            if era == "train" and i >= split_idx:
                continue
            if era == "test" and i < split_idx:
                continue
            w = make_weights(i)
            if w is None:
                continue
            r = period_return(i, w, include_accrual)
            if np.isfinite(r):
                vals.append(r)
        return summarise(np.array(vals), label, 365 // hold)

    def xs_weights(i: int):
        c = carry[i]
        good = np.isfinite(c)
        if good.sum() < 8:
            return None
        idxs = np.where(good)[0]
        ranked = c[idxs]
        k = max(2, good.sum() // 5)
        order = np.argsort(ranked)
        w = np.zeros(len(syms))
        w[idxs[order[-k:]]] = 1.0 / k
        w[idxs[order[:k]]] = -1.0 / k
        return w

    def ts_weights(i: int):
        c = carry[i]
        good = np.isfinite(c) & (np.abs(c) > 0.05)
        if good.sum() < 4:
            return None
        w = np.zeros(len(syms))
        w[good] = np.sign(c[good]) / good.sum()
        return w

    all_rows: list[dict] = []
    for label, maker in (("XSEC carry: long high / short low", xs_weights),
                         ("TS carry: long positive / short negative", ts_weights)):
        for accrual, tag in ((True, "with accrual"), (False, "spot only")):
            for era in ("all", "train", "test"):
                r = run(maker, accrual, f"{label} [{tag}] {era}", era)
                if r and era == "all":
                    all_rows.append(r)
                if r and era != "all":
                    all_rows.append(r)

    print_block("Carry portfolios (2013-2026, monthly rebalance, net of spread); "
                "train = pre-2020, test = 2020+", all_rows)

    if args.quintiles:
        print("\nQuintile ladder: mean monthly bps by carry rank (test of monotonicity)")
        q_rows: list[dict] = []
        for q in range(5):
            vals = []
            for i in grid:
                c = carry[i]
                good = np.isfinite(c)
                if good.sum() < 10:
                    continue
                idxs = np.where(good)[0]
                order = idxs[np.argsort(c[idxs])]
                k = good.sum() // 5
                sel = order[q * k:(q + 1) * k] if q < 4 else order[4 * k:]
                if sel.size == 0:
                    continue
                w = np.zeros(len(syms))
                w[sel] = 1.0 / sel.size
                r = period_return(i, w, True)
                if np.isfinite(r):
                    vals.append(r)
            s = summarise(np.array(vals), f"quintile {q + 1} ({'lowest' if q == 0 else 'highest' if q == 4 else 'mid'} carry)", 365 // hold)
            if s:
                q_rows.append(s)
        print(f"{'quintile':40}{'n':>5}{'bps/mo':>9}{'t':>7}{'ann%':>8}")
        for s in q_rows:
            print(f"{s['label']:40}{s['n']:>5}{s['bps']:>9.1f}{s['t']:>7.2f}{s['ann_pct']:>8.2f}")

    print("\nBar for CANDIDATE: |t|>3 across independent months, positive pre-2020 AND post-2020,")
    print("and positive after deducting the measured spread.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
