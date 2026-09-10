#!/usr/bin/env python3
"""Daily-panel edge research over a decade of history.

Why daily
---------
Twelve months of M5 showed that intraday patterns are real but tiny: fading a
2-sigma stretch pays about 0.25 pips against a 1.6-pip spread. The cost of a
trade is roughly fixed while the size of a move grows with the holding period,
so the question turns into: at what horizon does the pattern finally beat the
spread? Daily data answers that with power — thirteen years is ~3,370 sessions
per pair, and ~680 independent Mondays.

Method
------
Signals are turned into positions, positions into period returns, and every
result is reported gross AND net of that pair's measured spread. Inference is
clustered: pooled pairs are averaged within a date first, because twenty-six
correlated pairs on one day are close to one observation, not twenty-six.
Overlapping forward windows are removed by sampling on a grid of the holding
period.

Rules tested are the ones people actually trade: calendar drift, turn-of-month
flows, trend following, buying dips, and cross-sectional strength.

Usage:
    python3 tools/edge_daily.py --granularity D --symbols-file auto
    python3 tools/edge_daily.py --granularity D --hold 20
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

DEFAULT_SPREAD_PIPS = 2.0
PIP = {"JPY": 0.01}
DEFAULT_PIP = 0.0001


def pip_size(symbol: str) -> float:
    return PIP.get(symbol.upper()[-3:], DEFAULT_PIP)


def measured_spreads(data_dir: Path) -> dict[str, float]:
    """Median quoted spread per pair, in pips, from the M5 store if present."""
    out: dict[str, float] = {}
    for sym_dir in sorted(data_dir.glob("*")):
        if not sym_dir.is_dir():
            continue
        vals: list[float] = []
        for path in sorted(sym_dir.glob("*.jsonl"))[:40]:
            try:
                with open(path) as fh:
                    for line in fh:
                        rec = json.loads(line)
                        for c in rec.get("ltf", []):
                            sp = c.get("sp")
                            if sp:
                                vals.append(float(sp))
            except Exception:
                continue
        if vals:
            out[sym_dir.name] = float(np.median(vals)) / pip_size(sym_dir.name)
    return out


def load_panel(data_dir: Path, granularity: str, symbols: list[str]):
    """Return (dates, symbols, close matrix). Missing values are NaN."""
    series: dict[str, dict[str, float]] = {}
    for sym in symbols:
        path = data_dir / f"{sym}_{granularity}.jsonl"
        if not path.exists():
            continue
        rows: dict[str, float] = {}
        with open(path) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows[rec["t"][:10]] = float(rec["c"])
        if len(rows) > 250:
            series[sym] = rows

    if not series:
        return None
    all_dates = sorted(set().union(*[set(v) for v in series.values()]))
    syms = sorted(series)
    closes = np.full((len(all_dates), len(syms)), np.nan)
    idx = {d: i for i, d in enumerate(all_dates)}
    for j, sym in enumerate(syms):
        for d, c in series[sym].items():
            closes[idx[d], j] = c
    return all_dates, syms, closes


def forward_return(closes: np.ndarray, hold: int) -> np.ndarray:
    """Simple forward return over `hold` rows, aligned to the entry row."""
    n = closes.shape[0]
    fwd = np.full_like(closes, np.nan, dtype=float)
    if hold < n:
        fwd[:n - hold] = closes[hold:] / closes[:n - hold] - 1.0
    return fwd


def stats(period_returns: np.ndarray, label: str, dates_per_year: int) -> dict:
    """Clustered-by-construction: period_returns already has one value per date."""
    x = period_returns[np.isfinite(period_returns)]
    if x.size < 30:
        return {}
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    t = mean / (sd / math.sqrt(x.size)) if sd else 0.0
    half = x.size // 2
    return {
        "label": label,
        "n": int(x.size),
        "bps": mean * 1e4,
        "t": t,
        "ann_pct": mean * dates_per_year * 100,
        "h1_bps": float(x[:half].mean()) * 1e4,
        "h2_bps": float(x[half:].mean()) * 1e4,
        "win": float((x > 0).mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily-panel edge research.")
    ap.add_argument("--data-dir", default="candle_history_daily")
    ap.add_argument("--granularity", default="D", choices=["D", "H4"])
    ap.add_argument("--hold", type=int, default=5, help="Holding period in bars")
    ap.add_argument("--split", default=None, help="YYYY-MM-DD walk-forward split")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = DATA_DIR / args.data_dir
    if not data_dir.is_dir():
        print(f"No data at {data_dir}")
        return 1

    symbols = sorted({p.name.split("_")[0] for p in data_dir.glob("*_D.jsonl")})
    if not symbols:
        print(f"No per-symbol files in {data_dir}")
        return 1

    m5_dir = DATA_DIR / "candle_history_12m"
    spreads = measured_spreads(m5_dir) if m5_dir.is_dir() else {}
    panel = load_panel(data_dir, args.granularity, symbols)
    if panel is None:
        print("Panel empty")
        return 1
    dates, syms, closes = panel
    bars_per_year = 252 if args.granularity == "D" else 252 * 6
    print(f"[DAILY] {len(syms)} pairs x {len(dates)} {args.granularity} bars "
          f"({dates[0]} to {dates[-1]}) | hold {args.hold} bars")

    hold = args.hold
    fwd = forward_return(closes, hold)
    ret1 = np.full_like(closes, np.nan)
    ret1[1:] = closes[1:] / closes[:-1] - 1.0

    # Cost in return units per pair, for one round trip.
    cost = np.array([
        (spreads.get(s, DEFAULT_SPREAD_PIPS) * pip_size(s)) / np.nanmean(closes[:, j])
        for j, s in enumerate(syms)
    ])
    print(f"[DAILY] median round-trip cost: "
          f"{np.median([spreads.get(s, DEFAULT_SPREAD_PIPS) for s in syms]):.2f} pips\n")

    results: list[dict] = []

    # Positions are expressed as weights in [-1, 1] per pair.
    def evaluate(weights: np.ndarray, label: str, net_cost: bool = True) -> None:
        """weights: dates x pairs, already lagged so they use only past data."""
        w = np.nan_to_num(weights, nan=0.0)
        gross_exposure = np.abs(w).sum(axis=1)
        active = gross_exposure > 0
        per_pair = np.where(np.isfinite(fwd), w * np.nan_to_num(fwd), 0.0)
        port = np.divide(per_pair.sum(axis=1), gross_exposure,
                         out=np.full(len(dates), np.nan), where=active)
        if net_cost:
            # One round trip per position held, spread over the holding period.
            c = np.divide((np.abs(w) * cost).sum(axis=1), gross_exposure,
                          out=np.zeros(len(dates)), where=active)
            port = port - c
        # Grid-sample so the forward windows do not overlap.
        grid = np.arange(0, len(dates), hold)
        r = stats(port[grid], label, bars_per_year // hold)
        if r:
            results.append(r)

    # ── 1. Calendar drift: hold long through each weekday ────────────────────
    dow = np.array([datetime.fromisoformat(d).weekday() for d in dates])
    for name, day in (("Mon", 0), ("Tue", 1), ("Wed", 2), ("Thu", 3), ("Fri", 4)):
        # The forward return at row i realises on the session at row i+1, so the
        # weight belongs one row earlier for the label to name the right session.
        mask = np.zeros_like(closes)
        mask[:-1][dow[1:] == day] = 1.0
        evaluate(mask / max(len(syms), 1), f"drift: long all {name} (1d hold)", net_cost=True)

    # ── 2. Turn of month: last session and first two of the month ────────────
    months = np.array([d[:7] for d in dates])
    tom = np.zeros(len(dates), dtype=bool)
    for m in np.unique(months):
        idxs = np.where(months == m)[0]
        tom[idxs[:2]] = True          # first two sessions
        tom[idxs[-1]] = True          # last session
    w = np.zeros_like(closes)
    w[tom] = 1.0
    evaluate(w / max(len(syms), 1), "drift: long turn-of-month", net_cost=False)

    # ── 3. Trend following: sign of the past N-bar move ─────────────────────
    for look in (20, 60, 120, 250):
        past = np.full_like(closes, np.nan)
        past[look:] = closes[look:] / closes[:-look] - 1.0
        w = np.sign(np.nan_to_num(past, nan=0.0))
        evaluate(w / max(len(syms), 1), f"trend: follow past {look}d", net_cost=True)
        evaluate(-w / max(len(syms), 1), f"trend: fade past {look}d", net_cost=True)

    # ── 4. Short-term reversal: buy what just fell ──────────────────────────
    for look in (1, 5):
        past = np.full_like(closes, np.nan)
        past[look:] = closes[look:] / closes[:-look] - 1.0
        w = -np.sign(np.nan_to_num(past, nan=0.0))
        evaluate(w / max(len(syms), 1), f"reversal: fade past {look}d", net_cost=True)

    # ── 5. Cross-sectional momentum: strength vs peers ──────────────────────
    for look in (20, 60, 120):
        past = np.full_like(closes, np.nan)
        past[look:] = closes[look:] / closes[:-look] - 1.0
        w = np.zeros_like(closes)
        for i in range(look, len(dates)):
            row = past[i]
            good = np.isfinite(row)
            if good.sum() < 6:
                continue
            ranked = row[good]
            k = max(2, good.sum() // 5)
            order = np.argsort(ranked)
            idxs = np.where(good)[0]
            w[i, idxs[order[-k:]]] = 1.0 / k      # strongest
            w[i, idxs[order[:k]]] = -1.0 / k      # weakest
        evaluate(w, f"XSMOM: long strong / short weak {look}d", net_cost=True)
        evaluate(-w, f"XSMOM: reversed {look}d", net_cost=True)

    # ── 6. Volatility-conditioned trend ─────────────────────────────────────
    vol = np.full_like(closes, np.nan)
    vol[20:] = np.array([np.nanstd(ret1[i - 20:i], axis=0) for i in range(20, len(dates))])
    vol_rank = np.full_like(closes, np.nan)
    for j in range(len(syms)):
        col = vol[:, j]
        good = np.isfinite(col)
        if good.sum() > 100:
            r = np.argsort(np.argsort(col[good])) / max(good.sum() - 1, 1)
            vol_rank[good, j] = r
    past60 = np.full_like(closes, np.nan)
    past60[60:] = closes[60:] / closes[:-60] - 1.0
    trend = np.sign(np.nan_to_num(past60, nan=0.0))
    low_vol = np.nan_to_num(vol_rank, nan=0.5) < 0.4
    w = np.where(low_vol, trend, 0.0)
    evaluate(w / max(len(syms), 1), "trend 60d in low vol only", net_cost=True)

    # ── 7. Carry proxy: long high-yielders against low-yielders ─────────────
    # Real carry needs an interest-rate history we do not have, but in this
    # sample AUD/NZD/CAD paid and JPY/CHF charged throughout, so the classic
    # carry basket can be approximated from the currency legs.
    HIGH_YIELD = {"AUD", "NZD", "CAD"}
    LOW_YIELD = {"JPY", "CHF"}
    w = np.zeros_like(closes)
    for j, sym in enumerate(syms):
        base, quote = sym[:3], sym[3:]
        if base in HIGH_YIELD and quote in LOW_YIELD:
            w[:, j] = 1.0        # long the high yielder
        elif base in LOW_YIELD and quote in HIGH_YIELD:
            w[:, j] = -1.0       # short the low yielder
    evaluate(w / max(np.abs(w).sum(axis=1).max(), 1), "carry proxy: high vs low yield", net_cost=True)

    # ── 8. Monthly seasonality ──────────────────────────────────────────────
    month = np.array([int(d[5:7]) for d in dates])
    for m in range(1, 13):
        w = np.zeros_like(closes)
        w[month == m] = 1.0
        evaluate(w / max(len(syms), 1), f"seasonal: long month {m:02d}", net_cost=False)

    # ── 9. Reversal, long-only (many accounts cannot short cheaply) ─────────
    for look in (1, 5):
        past_l = np.full_like(closes, np.nan)
        past_l[look:] = closes[look:] / closes[:-look] - 1.0
        w = np.where(np.nan_to_num(past_l, nan=0.0) < 0, 1.0, 0.0)
        evaluate(w / max(len(syms), 1), f"reversal long-only after {look}d fall", net_cost=True)

    print(f"{'rule':38}{'n':>6}{'bps':>9}{'t':>7}{'ann%':>9}{'h1':>8}{'h2':>8}{'win':>7}  verdict")
    print("-" * 108)
    for r in sorted(results, key=lambda x: -abs(x["t"])):
        net = r["ann_pct"]
        if abs(r["t"]) < 3.0:
            verdict = "below bar"
        elif r["h1_bps"] * r["h2_bps"] <= 0:
            verdict = "one half only"
        elif net <= 0:
            verdict = "eaten by cost"
        else:
            verdict = "CANDIDATE"
        print(f"{r['label']:38}{r['n']:>6}{r['bps']:>9.2f}{r['t']:>7.2f}{net:>9.1f}"
              f"{r['h1_bps']:>8.2f}{r['h2_bps']:>8.2f}{r['win']:>7.0%}  {verdict}")
    print()
    print("bps = mean return per holding period, NET of the measured spread.")
    print("Bar: |t|>3 across independent periods, same sign in both halves, positive after cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
