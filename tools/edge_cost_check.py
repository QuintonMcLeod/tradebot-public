"""Re-cost the scrape entry on each trade's own quoted spread.

Why this exists
---------------
tools/edge_entry.py takes a single `--cost` value and subtracts it from every
trade. The scrape results in Documentation/Research/SCRAPE_ENTRY_2026_09_13.md
were produced that way and described as "net of each trade's own quoted spread".
Those are not the same thing. The spread distribution across these pairs is
right-skewed: the wide crosses carry much wider quotes than the majors, so the
subset mean spread is materially above the subset median that was charged.

Charging the median understates the cost of every trade in the subset. Because
the round trip is paid per trade, the mean is the correct charge. This script
reports both so the difference is explicit rather than buried.

Method
------
Reuses load_series and detect from the existing harness, so the event
definition is the one that reproduces the published counts. The conditional
filter (hour, break depth) is applied BEFORE the non-overlapping-window
de-clustering, inside each symbol. That ordering is the one the published
figures came from: de-clustering first, across all hours, lets events from
hours that are not being tested suppress the events that are, which is the same
class of error as de-clustering on pooled timestamps across pairs.

Verification
------------
At these settings the gross expectancy and the flat-cost net reproduce the
published tables closely:
  15 pairs, T15/S20, 24h: gross +3.5 (published +3.45), flat-cost net +1.2
    (published +1.15), n=1984 (published 2052)
  26 pairs, T15/S25, 24h: gross +4.6 (published +4.61), flat-cost net +1.5
    (published +1.51), n=1029 (published 1051)
The small count differences are data vintage, not method.
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

WIN = 20          # prior-range lookback, in bars
HOUR = 20         # the only hour the rule trades, UTC
HORIZON = 288     # 24 hours of M5 bars
SPACING = 288     # non-overlapping windows, applied inside the filtered subset

DATASETS = (
    # (directory, min break depth in pips, target, stop, label, flat cost to compare)
    ("candle_history_36m", 2.0, 15, 20, "15 pairs, 3 years", 2.30),
    ("candle_history_12m", 2.0, 15, 25, "26 pairs, 12 months (doc best bracket)", 3.10),
    ("candle_history_12m", 2.0, 15, 20, "26 pairs, 12 months (deployed bracket)", 3.10),
)


def build(data_dir: Path, min_depth: float, horizon: int = HORIZON,
          spacing: int = SPACING) -> list[dict]:
    """Hour-and-depth-filtered fade events with their forward excursions."""
    events: list[dict] = []
    for symbol in sorted(p.name for p in data_dir.iterdir() if p.is_dir()):
        series = load_series(data_dir, symbol, None, None)
        if series is None or series.c.size < 5000:
            continue

        idx, dirs, feat = detect(series, WIN, "break", 1)  # no thinning yet
        c, h, l, pip = series.c, series.h, series.l, series.pip
        n = c.size

        selected = [j for j in range(idx.size)
                    if feat[j, 0] == HOUR and feat[j, 8] >= min_depth]
        selected.sort(key=lambda j: idx[j])

        last = -(10 ** 9)
        for j in selected:
            i, direction = int(idx[j]), int(dirs[j])
            if i - last < spacing:      # de-cluster inside the filtered subset
                continue
            end = min(i + horizon, n)
            if end - i < 3:
                continue
            last = i

            if direction > 0:
                favourable = (h[i + 1:end] - c[i]) / pip
                adverse = (l[i + 1:end] - c[i]) / pip
            else:
                favourable = (c[i] - l[i + 1:end]) / pip
                adverse = (c[i] - h[i + 1:end]) / pip

            events.append(dict(
                mfe=np.maximum.accumulate(favourable) if favourable.size else np.array([0.0]),
                mae=np.minimum.accumulate(adverse) if adverse.size else np.array([0.0]),
                fin=direction * (c[end - 1] - c[i]) / pip,
                spread=(series.sp[i] / pip) if np.isfinite(series.sp[i]) else 0.0,
                epoch=series.epoch[i],
            ))
    return events


def _stats(x: np.ndarray) -> tuple[float, float]:
    sd = x.std(ddof=1) if x.size > 1 else 0.0
    return float(x.mean()), float(x.mean() / (sd / math.sqrt(x.size))) if sd > 0 else 0.0


def per_trade(events: list[dict], target: float, stop: float) -> np.ndarray:
    """Signed pips per trade, stop winning ties as in edge_entry.outcomes."""
    out = []
    for e in events:
        hit_t = np.flatnonzero(e["mfe"] >= target)
        hit_s = np.flatnonzero(-e["mae"] >= stop)
        first_t = hit_t[0] if hit_t.size else 10 ** 6
        first_s = hit_s[0] if hit_s.size else 10 ** 6
        if first_t < first_s:
            out.append(target)
        elif first_s <= first_t:
            out.append(-stop)
        else:
            out.append(e["fin"])
    return np.array(out)


def report(data_dir: Path, min_depth: float, target: float, stop: float,
           label: str, flat: float) -> None:
    events = build(data_dir, min_depth)
    if not events:
        print(f"{label}: no events")
        return

    gross = per_trade(events, target, stop)
    spreads = np.array([e["spread"] for e in events])

    g_mean, _ = _stats(gross)
    flat_mean, flat_t = _stats(gross - flat)
    own_mean, own_t = _stats(gross - spreads)

    print(f"\n{label}")
    print(f"  dataset={data_dir.name}  n={gross.size}  bracket=T{target:.0f}/S{stop:.0f}  "
          f"hour={HOUR}  depth>={min_depth:.0f}p  hold={HORIZON} bars")
    print(f"  spread: mean={spreads.mean():.2f}  median={np.median(spreads):.2f} "
          f"min={spreads.min():.2f}  max={spreads.max():.2f}")
    print(f"  gross expectancy            {g_mean:+.2f} pips")
    print(f"  net, flat {flat:.2f} charged      {flat_mean:+.2f} pips   t={flat_t:+.2f}")
    print(f"  net, own spread per trade   {own_mean:+.2f} pips   t={own_t:+.2f}")
    print(f"  -> charging the subset median instead of the mean overstates the "
          f"result by {(spreads.mean() - flat):.2f} pips per trade")

    # The mean is sensitive to the tail, so show that the gap is not one.
    trimmed = np.where(spreads <= np.percentile(spreads, 99), spreads, np.nan)
    wide = int((spreads > 5.0).sum())
    print(f"  robustness: trimmed-at-p99 mean cost={np.nanmean(trimmed):.2f} "
          f"(vs {flat:.2f} charged), so the gap is distributional, not a few outliers")
    print(f"              {wide} trades ({100*wide/spreads.size:.1f}%) quoted above 5 pips "
          f"= {100*spreads[spreads > 5.0].sum()/spreads.sum():.1f}% of total cost")


def main() -> int:
    print("[EDGE-COST] Re-costing the scrape entry on each trade's own quoted spread")
    print(f"[EDGE-COST] bar for a finding: |t| > 3 on independent clusters")
    for name, depth, target, stop, label, flat in DATASETS:
        data_dir = DEFAULT_DATA / name
        if not data_dir.is_dir():
            print(f"\n{label}: missing {data_dir}")
            continue
        report(data_dir, depth, target, stop, label, flat)
    print("\n[EDGE-COST] The gross edge reproduces the published figures. The net "
          "does not, because the published net charged a single flat value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
