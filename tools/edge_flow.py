#!/usr/bin/env python3
"""Positioning factor: is the crowd wrong at extremes?

The one input in this study that is not derived from price. Weekly CFTC data gives
net speculative positions per currency since 2006, which is the standard measure
of crowding, and the claim being tested is the oldest one in the retail book: when
speculators are piled into a currency, it is about to turn.

Method
------
1. Crowding = net leveraged-money position divided by open interest, then
   standardised against its own trailing three years so the measure means the same
   thing in 2008 and 2026.
2. A pair's relative crowding is the base currency's score minus the quote's, so
   EURUSD is crowded long when EUR is crowded *and* USD is not.
3. Signals are contrarian (fade the crowd) and continuation (follow it), at three
   crowding thresholds, over three holding periods.
4. Every result is charged the spread measured for that pair, is clustered in
   time, is split into 2006-2019 and 2020-2026, and reports how many pairs it
   works on.

The report date is Tuesday's position published on Friday, so signals take effect
the following Monday — a lag, not a look-ahead.

Usage:
    python3 tools/edge_flow.py
    python3 tools/edge_flow.py --thresholds 1.0,1.5,2.0 --horizons 5,10,20
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from edge_daily import load_panel, measured_spreads, pip_size, DEFAULT_SPREAD_PIPS  # noqa: E402

Z_WINDOW = 156          # three years of weeks
PUBLISH_LAG_DAYS = 3    # Tuesday position, Friday release; Monday is safe


def load_cot(cot_dir: Path) -> dict[str, dict[str, tuple[str, float]]]:
    """{ccy: {available_date: (report_date, crowding_ratio_z)}} built causally."""
    out: dict[str, dict[str, tuple[str, float]]] = {}
    for path in sorted(cot_dir.glob("*.csv")):
        ccy = path.stem
        weeks: list[tuple[str, float]] = []
        with open(path) as fh:
            for row in csv.DictReader(fh):
                try:
                    lev = float(row["lev_net"])
                    oi = float(row["open_interest"])
                except (KeyError, ValueError):
                    continue
                if oi > 0:
                    weeks.append((row["date"], lev / oi))
        if len(weeks) < Z_WINDOW + 20:
            continue
        ratios = np.array([v for _, v in weeks])
        mapped: dict[str, tuple[str, float]] = {}
        for i in range(Z_WINDOW, len(weeks)):
            window = ratios[i - Z_WINDOW:i]          # strictly prior history
            sd = window.std(ddof=1)
            if sd <= 0:
                continue
            z = (ratios[i] - window.mean()) / sd
            report = weeks[i][0]
            available = (datetime.fromisoformat(report) + timedelta(days=PUBLISH_LAG_DAYS)
                         ).date().isoformat()
            mapped[available] = (report, float(z))
        if mapped:
            out[ccy] = mapped
    return out


def crowding_matrix(dates: list[str], syms: list[str],
                    cot: dict[str, dict[str, tuple[str, float]]]) -> np.ndarray:
    """Relative crowding per pair per date, forward-filled from publication dates."""
    # First: a per-currency daily series of the most recently published score.
    ccy_daily: dict[str, np.ndarray] = {}
    for ccy, mapped in cot.items():
        avail = sorted(mapped)
        series = np.full(len(dates), np.nan)
        j = 0
        last = np.nan
        for i, d in enumerate(dates):
            while j < len(avail) and avail[j] <= d:
                last = mapped[avail[j]][1]
                j += 1
            series[i] = last
        ccy_daily[ccy] = series

    out = np.full((len(dates), len(syms)), np.nan)
    for j, sym in enumerate(syms):
        base, quote = sym[:3], sym[3:]
        if base in ccy_daily and quote in ccy_daily:
            out[:, j] = ccy_daily[base] - ccy_daily[quote]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="CFTC positioning factor test.")
    ap.add_argument("--data-dir", default="candle_history_daily23")
    ap.add_argument("--thresholds", default="1.0,1.5,2.0")
    ap.add_argument("--horizons", default="5,10,20")
    ap.add_argument("--split", default="2020-01-01")
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = DATA_DIR / args.data_dir
    cot = load_cot(DATA_DIR / "cot")
    if not cot:
        print("No COT data — run tools/fetch_cot.py")
        return 1

    symbols = sorted({p.name.split("_")[0] for p in data_dir.glob("*_D.jsonl")})
    panel = load_panel(data_dir, "D", symbols)
    if panel is None:
        print("Panel empty")
        return 1
    dates, syms, closes = panel
    print(f"[FLOW] {len(syms)} pairs x {len(dates)} days ({dates[0]} to {dates[-1]})")
    print(f"[FLOW] positioning series: {', '.join(sorted(cot))}")

    rel = crowding_matrix(dates, syms, cot)
    print(f"[FLOW] relative crowding available on {np.isfinite(rel).mean():.1%} of pair-days\n")

    spreads = measured_spreads(DATA_DIR / "candle_history_12m")
    avg_price = np.nanmean(closes, axis=0)
    cost = np.array([(spreads.get(s, DEFAULT_SPREAD_PIPS) * pip_size(s)) / avg_price[j]
                     for j, s in enumerate(syms)])

    split_idx = next((i for i, d in enumerate(dates) if d >= args.split), len(dates) // 2)
    thresholds = [float(t) for t in args.thresholds.split(",")]
    horizons = [int(h) for h in args.horizons.split(",")]

    fwd_cache = {}
    for h in horizons:
        f = np.full_like(closes, np.nan, dtype=float)
        f[:len(dates) - h] = closes[h:] / closes[:len(dates) - h] - 1.0
        fwd_cache[h] = f

    rows = []
    for h in horizons:
        fwd = fwd_cache[h]
        grid = list(range(0, len(dates) - h, h))
        for thr in thresholds:
            for mode in ("fade", "follow"):
                for era in ("all", "train", "test"):
                    vals, keys, sym_means = [], [], {}
                    for i in grid:
                        if era == "train" and i >= split_idx:
                            continue
                        if era == "test" and i < split_idx:
                            continue
                        r = rel[i]
                        active = np.isfinite(r) & (np.abs(r) > thr) & np.isfinite(fwd[i])
                        if active.sum() < 4:
                            continue
                        direction = -np.sign(r[active]) if mode == "fade" else np.sign(r[active])
                        gross = direction * fwd[i][active]
                        gross = gross - cost[active]
                        vals.append(float(gross.mean()))
                        keys.append(i)
                        for j, g in zip(np.where(active)[0], gross):
                            sym_means.setdefault(syms[j], []).append(g)
                    if len(vals) < 30:
                        continue
                    arr = np.array(vals)
                    sd = arr.std(ddof=1)
                    t = arr.mean() / (sd / math.sqrt(arr.size)) if sd else 0.0
                    half = arr.size // 2
                    pos = sum(1 for v in sym_means.values() if np.mean(v) > 0)
                    rows.append({
                        "label": f"{mode} crowd |z|>{thr} h{h} {era}",
                        "n": arr.size, "bps": float(arr.mean()) * 1e4, "t": float(t),
                        "ann": float(arr.mean()) * (252 // h) * 100,
                        "h1": float(arr[:half].mean()) * 1e4,
                        "h2": float(arr[half:].mean()) * 1e4,
                        "win": float((arr > 0).mean()),
                        "sym_pos": pos / max(len(sym_means), 1),
                    })

    cells = len(rows)
    bar = 3.0 + math.log10(max(cells, 1))
    print(f"{cells} cells; family-wise bar about |t|>{bar:.1f}")
    print(f"\n{'cell':34}{'n':>6}{'bps':>9}{'t':>7}{'ann%':>8}{'h1':>8}{'h2':>8}{'win':>7}{'+sym':>6}  verdict")
    print("-" * 104)
    for r in sorted(rows, key=lambda x: -abs(x["t"]))[:16]:
        if r["bps"] <= 0:
            verdict = "eaten by cost"
        elif abs(r["t"]) < bar:
            verdict = "below bar"
        elif r["h1"] * r["h2"] <= 0:
            verdict = "one era only"
        elif r["sym_pos"] < 0.6:
            verdict = "not broad"
        else:
            verdict = "CANDIDATE"
        print(f"{r['label']:34}{r['n']:>6}{r['bps']:>9.2f}{r['t']:>7.2f}{r['ann']:>8.2f}"
              f"{r['h1']:>8.2f}{r['h2']:>8.2f}{r['win']:>7.0%}{r['sym_pos']:>6.0%}  {verdict}")

    print("\n'fade' bets against the crowded side, 'follow' bets with it; both net of spread.")
    print("train = 2006-2019, test = 2020-2026, halves are chronological within era.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
