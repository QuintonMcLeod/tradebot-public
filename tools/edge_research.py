#!/usr/bin/env python3
"""Edge research harness — does a signal predict the next move, net of real costs?

Why this exists
---------------
The engine replay answers "what would this strategy have made" but needs a full
strategy, is slow, and cannot tell you *why*. This harness answers the narrower
question an entry edge actually depends on: after a given market condition, is
the next move biased, and is that bias bigger than the spread you must cross?

Method
------
For every signal occurrence on every pair in the sample, measure the forward
price move over one or more horizons. Each result is reported in pips AND as a
multiple of that pair's median spread, because an edge of 2 pips is not an edge
at all if the round trip costs 1.6 pips to cross.

Discipline (this is the part that keeps us honest)
--------------------------------------------------
1. Overlapping windows inflate significance, so events are de-clustered: after a
   signal fires, the same signal is ignored until the horizon has elapsed.
2. Every effect is reported on the first half and the second half of the sample
   separately. An effect that lives in only one half is noise, however pretty
   its t-statistic.
3. The number of hypotheses tested is printed. With ~20 tests, requiring |t|>3
   is roughly a 5% family-wise threshold; |t|>2 is not evidence of anything.

Signals are the ones humans actually describe: fade an overextension, follow a
breakout, trade the session open, respect round numbers, avoid chop, mind the
calendar.

Usage:
    python3 tools/edge_research.py --data-dir candle_history_12m --symbols EURUSD,GBPUSD
    python3 tools/edge_research.py --data-dir candle_history_12m --all
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

PIP = {"JPY": 0.01}          # everything else uses 0.0001
DEFAULT_PIP = 0.0001


def pip_size(symbol: str) -> float:
    return PIP.get(symbol.upper()[-3:], DEFAULT_PIP)


@dataclass
class Series:
    symbol: str
    epoch: np.ndarray      # int64 seconds, UTC
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    sp: np.ndarray         # quoted spread per candle (price units)

    @property
    def pip(self) -> float:
        return pip_size(self.symbol)

    def spread_pips(self) -> float:
        """Median quoted spread; the round-trip cost is about one full spread."""
        good = self.sp[np.isfinite(self.sp) & (self.sp > 0)]
        if good.size == 0:
            return 1.0  # conservative fallback
        return float(np.median(good)) / self.pip


def load_series(data_dir: Path, symbol: str, start: str | None, end: str | None) -> Series | None:
    """Load backfilled daily files into flat arrays."""
    sym_dir = data_dir / symbol
    if not sym_dir.is_dir():
        return None
    rows: list[dict] = []
    for path in sorted(sym_dir.glob(f"{symbol}_*.jsonl")):
        day = path.stem.split("_", 1)[1]
        if start and day < start:
            continue
        if end and day > end:
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.extend(rec.get("ltf", []))
    if len(rows) < 500:
        return None
    rows.sort(key=lambda r: r["t"])
    epoch = np.array([int(datetime.fromisoformat(r["t"]).timestamp()) for r in rows], dtype=np.int64)
    def col(k, default=math.nan):
        return np.array([float(r.get(k, default)) if r.get(k) is not None else default for r in rows])
    return Series(symbol, epoch, col("o"), col("h"), col("l"), col("c"), col("v"), col("sp"))


# ── indicators ────────────────────────────────────────────────────────────────

def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if x.size < n:
        return out
    csum = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (csum[n:] - csum[:-n]) / n
    return out


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    if x.size < n:
        return out
    c1 = np.cumsum(np.insert(x, 0, 0.0))
    c2 = np.cumsum(np.insert(x * x, 0, 0.0))
    s = c1[n:] - c1[:-n]
    ss = c2[n:] - c2[:-n]
    var = np.maximum(ss / n - (s / n) ** 2, 0.0)
    out[n - 1:] = np.sqrt(var)
    return out


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    prev = np.roll(c, 1)
    prev[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return sma(tr, n)


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(n - 1, x.size):
        out[i] = np.max(x[i - n + 1:i + 1])
    return out


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(n - 1, x.size):
        out[i] = np.min(x[i - n + 1:i + 1])
    return out


def hour_of(epoch: np.ndarray) -> np.ndarray:
    return ((epoch // 3600) % 24).astype(int)


def day_of_week(epoch: np.ndarray) -> np.ndarray:
    return ((epoch // 86400 + 4) % 7).astype(int)   # 0=Monday for a Unix epoch


def day_index(epoch: np.ndarray) -> np.ndarray:
    return (epoch // 86400).astype(np.int64)


# ── evaluation ────────────────────────────────────────────────────────────────

@dataclass
class Events:
    """De-clustered signal events for one symbol: when, and what followed."""
    epoch: np.ndarray
    signed_pips: np.ndarray


@dataclass
class Result:
    name: str
    horizon: int
    n: int
    symbols: int
    mean_pips: float
    t_stat: float
    spread_mult: float
    net_pips: float
    half1: float
    half2: float
    symbol_hit_rate: float
    clusters: int = 0

    @property
    def consistent(self) -> bool:
        return self.half1 * self.half2 > 0


def evaluate(series: Series, long_mask: np.ndarray, short_mask: np.ndarray,
             horizon: int) -> Events | None:
    """Signed forward moves after a signal, de-clustered so windows do not overlap.

    Overlapping forward windows are severely autocorrelated; counting every bar
    of a signal episode would manufacture significance out of one move.
    """
    c = series.c
    pip = series.pip
    n = c.size
    if horizon >= n:
        return None
    fwd = np.full(n, np.nan)
    fwd[:n - horizon] = (c[horizon:] - c[:n - horizon]) / pip

    epochs: list[int] = []
    vals: list[float] = []
    last_l = last_s = -(10 ** 9)
    for i in range(n - horizon):
        is_long = bool(long_mask[i])
        is_short = bool(short_mask[i])
        if not (is_long or is_short):
            continue
        if is_long and i - last_l < horizon:
            continue
        if is_short and i - last_s < horizon:
            continue
        val = fwd[i]
        if not np.isfinite(val):
            continue
        if is_long:
            last_l = i
        else:
            last_s = i
        epochs.append(int(series.epoch[i]))
        vals.append(val if is_long else -val)
    if len(vals) < 20:
        return None
    return Events(np.array(epochs, dtype=np.int64), np.array(vals))


def pool(name: str, per_symbol: dict[str, Events], spreads: dict[str, float],
         horizon: int) -> Result | None:
    """Combine every symbol into one panel sample, then cluster it honestly.

    Raw event counts overstate the evidence twice over. Forward windows overlap
    (handled by de-clustering at collection), and the pairs are heavily
    correlated — nine pairs moving on the same Monday is roughly one observation,
    not nine. Averaging the events that share a time bucket collapses both
    effects, so the t-statistic is computed across buckets.
    """
    if not per_symbol:
        return None
    epochs = np.concatenate([e.epoch for e in per_symbol.values()])
    vals = np.concatenate([e.signed_pips for e in per_symbol.values()])
    if vals.size < 50:
        return None

    bar_seconds = 300                      # M5 sampling
    bucket_seconds = max(horizon * bar_seconds, 3600)
    buckets = epochs // bucket_seconds
    order = np.argsort(buckets)
    buckets_sorted = buckets[order]
    vals_sorted = vals[order]
    unique_buckets, starts = np.unique(buckets_sorted, return_index=True)
    bucket_means = np.add.reduceat(vals_sorted, starts) / np.diff(
        np.append(starts, vals_sorted.size))

    med_spread = float(np.median(list(spreads.values()))) if spreads else 1.0
    sd = bucket_means.std(ddof=1)
    t = float(bucket_means.mean() / (sd / math.sqrt(bucket_means.size))) if sd > 0 else 0.0
    mid = bucket_means.size // 2
    h1 = float(bucket_means[:mid].mean()) if mid else 0.0
    h2 = float(bucket_means[mid:].mean()) if mid else 0.0
    hits = sum(1 for e in per_symbol.values() if e.signed_pips.mean() > 0)
    return Result(name, horizon, int(vals.size), len(per_symbol),
                  float(vals.mean()), t,
                  float(vals.mean() / med_spread) if med_spread else 0.0,
                  float(vals.mean() - med_spread),
                  h1, h2, hits / len(per_symbol),
                  int(bucket_means.size))


def build_signals(s: Series) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return {name: (long_mask, short_mask)} for every hypothesis tested."""
    c, h, l = s.c, s.h, s.l
    n = c.size
    z = np.zeros(n, dtype=bool)

    ma20 = sma(c, 20)
    sd20 = rolling_std(c, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        zscore = (c - ma20) / sd20

    atr14 = atr(h, l, c, 14)
    atr_pct = np.full(n, np.nan)
    valid_atr = np.isfinite(atr14)
    if valid_atr.sum() > 100:
        ranks = np.argsort(np.argsort(atr14[valid_atr])) / max(valid_atr.sum() - 1, 1)
        atr_pct[valid_atr] = ranks

    prev_close = np.roll(c, 1); prev_close[0] = c[0]
    ret1 = (c - prev_close) / s.pip
    ret12 = np.full(n, np.nan)
    ret12[12:] = (c[12:] - c[:-12]) / s.pip

    hi_prev_day = np.full(n, np.nan)
    lo_prev_day = np.full(n, np.nan)
    day = day_index(s.epoch)
    uniq_days = np.unique(day)
    for k in range(1, len(uniq_days)):
        prev = uniq_days[k - 1]
        cur = uniq_days[k]
        prev_mask = day == prev
        cur_mask = day == cur
        if prev_mask.sum() > 10:
            hi_prev_day[cur_mask] = h[prev_mask].max()
            lo_prev_day[cur_mask] = l[prev_mask].min()

    hr = hour_of(s.epoch)
    dow = day_of_week(s.epoch)

    # Asian range for the session-open hypothesis (00:00-07:00 UTC)
    asian_hi = np.full(n, np.nan)
    asian_lo = np.full(n, np.nan)
    for d in uniq_days:
        m = day == d
        asia = m & (hr < 7)
        if asia.sum() > 10:
            asian_hi[m] = h[asia].max()
            asian_lo[m] = l[asia].min()

    signals: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def add(name, long_mask, short_mask):
        signals[name] = (np.nan_to_num(long_mask, nan=0).astype(bool),
                         np.nan_to_num(short_mask, nan=0).astype(bool))

    # 1. Mean reversion: fade a 2-sigma stretch from the 20-bar mean
    add("mr: fade 2-sigma (20 bars)", zscore <= -2.0, zscore >= 2.0)
    # 2. Shallower fade, more events
    add("mr: fade 1.5-sigma (20 bars)", zscore <= -1.5, zscore >= 1.5)
    # 2b. Deeper stretches: if the edge is real it should grow with the stretch
    add("mr: fade 2.5-sigma (20 bars)", zscore <= -2.5, zscore >= 2.5)
    add("mr: fade 3-sigma (20 bars)", zscore <= -3.0, zscore >= 3.0)
    add("mr: fade 4-sigma (20 bars)", zscore <= -4.0, zscore >= 4.0)
    # 3. Momentum: last hour's direction continues
    add("mom: follow last 1h move", ret12 > 0, ret12 < 0)
    # 4. Breakout of the previous day's range
    add("brk: prior-day high/low", c > hi_prev_day, c < lo_prev_day)
    # 5. Session open: break of the Asian range during London
    london = (hr >= 7) & (hr < 11)
    add("sess: London breaks Asia range", london & (c > asian_hi), london & (c < asian_lo))
    # 6. Round numbers: fade an approach to a 00-level
    lvl = np.round(c / (100 * s.pip)) * (100 * s.pip)
    near = np.abs(c - lvl) <= 2 * s.pip
    add("lvl: fade 00-level touch", near & (ret1 < 0), near & (ret1 > 0))
    # 7. Breakout only in high volatility
    hi_vol = atr_pct > 0.8
    add("vol: high-vol breakout", hi_vol & (c > hi_prev_day), hi_vol & (c < lo_prev_day))
    # 8. Fade only in low volatility
    lo_vol = atr_pct < 0.2
    add("vol: low-vol fade 2-sigma", lo_vol & (zscore <= -2.0), lo_vol & (zscore >= 2.0))
    # 9. Calendar folklore, stated as the folklore states it:
    #    Monday drifts up, Friday drifts down.
    add("cal: Monday drift (long)", dow == 0, z)
    add("cal: Friday drift (short)", z, dow == 4)
    # 10. Session chop avoidance: does trading Asia lose?
    asia = (hr >= 0) & (hr < 7)
    add("sess: Asia continuation", asia & (ret12 > 0), asia & (ret12 < 0))
    ny = (hr >= 12) & (hr < 17)
    add("sess: NY continuation", ny & (ret12 > 0), ny & (ret12 < 0))

    return signals


HORIZONS = {"15m": 3, "1h": 12, "4h": 48, "1d": 288}


def main() -> int:
    ap = argparse.ArgumentParser(description="Test whether a signal predicts the next move, net of cost.")
    ap.add_argument("--data-dir", default="candle_history_12m")
    ap.add_argument("--symbols", default=None, help="Comma list")
    ap.add_argument("--all", action="store_true", help="Use every symbol in the data dir")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--horizon", default="1h", choices=list(HORIZONS))
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = DATA_DIR / args.data_dir
    if not data_dir.is_dir():
        print(f"No data at {data_dir}")
        return 1

    if args.all:
        symbols = sorted(p.name for p in data_dir.iterdir() if p.is_dir())
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = ["EURUSD", "GBPUSD", "USDJPY"]

    horizon_bars = HORIZONS[args.horizon]
    print(f"[EDGE] {len(symbols)} symbols | horizon {args.horizon} ({horizon_bars} M5 bars) | {data_dir}")

    pooled: dict[str, dict[str, Events]] = {}
    spreads: dict[str, float] = {}
    loaded = 0
    for sym in symbols:
        series = load_series(data_dir, sym, args.start, args.end)
        if series is None:
            continue
        loaded += 1
        spreads[sym] = series.spread_pips()
        for name, (lm, sm) in build_signals(series).items():
            ev = evaluate(series, lm, sm, horizon_bars)
            if ev is not None:
                pooled.setdefault(name, {})[sym] = ev

    names = set(pooled.keys())
    results = [r for name, per_sym in pooled.items()
               if (r := pool(name, per_sym, spreads, horizon_bars)) is not None]

    if not results:
        print("No results — insufficient data.")
        return 1

    print(f"[EDGE] loaded {loaded} symbols | "
          f"{int(np.sum([r.n for r in results]))} de-clustered events | "
          f"{len(names)} hypotheses tested")
    print(f"[EDGE] median spread across pairs: {np.median(list(spreads.values())):.2f} pips\n")

    print(f"{'signal':32}{'n':>7}{'cl':>6}{'sym':>5}{'pips':>8}{'net':>8}{'x spr':>7}"
          f"{'t':>7}{'half1':>7}{'half2':>7}{'+ve sym':>8}  verdict")
    print("-" * 105)
    for r in sorted(results, key=lambda x: -abs(x.t_stat)):
        if abs(r.t_stat) < 3.0:
            verdict = "below bar"
        elif not r.consistent:
            verdict = "one half only"
        elif r.net_pips <= 0:
            verdict = "eaten by spread"
        elif r.symbol_hit_rate < 0.6:
            verdict = "not broad"
        else:
            verdict = "CANDIDATE"
        print(f"{r.name:32}{r.n:>7}{r.clusters:>6}{r.symbols:>5}{r.mean_pips:>8.2f}{r.net_pips:>8.2f}"
              f"{r.spread_mult:>7.2f}{r.t_stat:>7.2f}{r.half1:>7.2f}{r.half2:>7.2f}"
              f"{r.symbol_hit_rate:>8.0%}  {verdict}")

    print()
    print("'cl' = independent time clusters: the t-statistic is computed across these, not events.")
    print("Bar for CANDIDATE: |t|>3 (family-wise, ~20 tests), same sign in both halves,")
    print("positive after deducting the median spread, and positive on 60%+ of symbols.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
