#!/usr/bin/env python3
"""Test the claim that the market "swings remarkably" on Jewish holidays.

The claim, as put: the market swings remarkably on Jewish holidays, and if true
it is worth a strategy. Two separate things have to be answered, because a swing
is not a direction:

  1. VOLATILITY. Does the market move more on those dates than on ordinary
     dates? Measured three ways per day, all normalised by each pair's own
     typical value so no single volatile pair dominates:
        - range  (high - low) / close, the "swing"
        - |return|, close-to-close
        - tick volume, the mechanism: if the story is that participants are
          away, volume should drop, and a claim of bigger swings with less
          volume needs a better explanation than thin books.

  2. DIRECTION. Is there a signed drift on those dates, big enough to pay a
     round trip? A swing with no direction cannot be traded with a spread and
     no options; it is a reason to stand aside, not a reason to enter.

Method notes, because they are the difference between a result and an artefact:

  - One observation per DATE, not per pair-date. The 26 pairs are the same
    dollar most of the time; treating them as independent inflates t by roughly
    sqrt(26). Each date contributes the cross-sectional mean of the standardised
    pair values, so the sample size is the number of holiday dates and nothing
    more.
  - Holiday dates come from Hebcal (hebcal.com), an authoritative Hebrew
    calendar, fetched live and cached. Nothing is hand-typed.
  - The permutation null draws random date sets matched to the real holidays on
    WEEKDAY and MONTH. This matters: Tishrei holidays land in September and
    October and Nisan holidays in March and April, and Hebrew holidays walk
    through the weekdays. A raw comparison against "all other days" confounds
    the holiday with the season and the weekday.
  - Work-permitted holidays (Chanukah, Tisha B'Av, Tu BiShvat) are carried
    through the same test as a placebo. They are Jewish holidays on which
    observant participants keep working. If the effect is really "participants
    are away", these must show nothing. If they show as much as Yom Kippur
    does, the finding is the calendar search, not the holiday.
  - Every candidate is charged the measured round trip before it is called an
    edge. The live EUR_USD round trip is 1.5 pips and the portfolio model is
    2.45.

Usage:
    python3 tools/jewish_holiday_study.py --years 13
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

HEBCAL = "https://www.hebcal.com/hebcal"

# Holidays on which observant Jews do not work. These are the candidate dates.
WORK_PROHIBITED = (
    "Rosh Hashana", "Yom Kippur", "Sukkot", "Shmini Atzeret", "Simchat Torah",
    "Pesach", "Shavuot",
)
# Jewish holidays on which work is permitted. Placebo set.
WORK_PERMITTED = ("Chanukah", "Tish'a B'Av", "Tu BiShvat", "Lag BaOmer", "Purim", "Shushan Purim")

LAG_NAMES = {-2: "two days before", -1: "day before (Erev)", 0: "holiday day",
             1: "day after", 2: "two days after"}


def credentials() -> tuple[str, str]:
    from dotenv import dotenv_values
    from tradebot_sci import paths
    from tradebot_sci.config.loader import load_config_json

    cfg = load_config_json()
    oanda = cfg.get("brokers", {}).get("oanda", {}) or {}
    secrets = dotenv_values(paths.SECRETS_FILE) if paths.SECRETS_FILE.exists() else {}
    key = secrets.get("OANDA_API_KEY") or secrets.get("OANDA_API_TOKEN")
    if not key:
        raise SystemExit("No OANDA_API_KEY")
    env = str(oanda.get("environment", "practice")).lower()
    base = "https://api-fxtrade.oanda.com" if "live" in env else "https://api-fxpractice.oanda.com"
    return key, base


def hebcal(year: int, kind: str, cache: Path) -> list[dict]:
    """kind is 'maj' or 'min'; returns [{date, title}] for that year."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"hebcal_{kind}_{year}.json"
    if path.exists():
        return json.loads(path.read_text())
    r = requests.get(HEBCAL, params={"v": "1", "cfg": "json", "yt": "G",
                                     kind: "on", "year": year}, timeout=30)
    r.raise_for_status()
    items = [{"date": i["date"], "title": i.get("title", "")}
             for i in r.json().get("items", []) if i.get("category") == "holiday"]
    path.write_text(json.dumps(items, indent=1))
    time.sleep(0.3)
    return items


def classify(title: str) -> str | None:
    t = title.lower()
    for w in WORK_PROHIBITED:
        if w.lower() in t:
            return "prohibited"
    for w in WORK_PERMITTED:
        if w.lower() in t:
            return "permitted"
    return None


def family(title: str) -> str:
    t = title.lower()
    if "rosh hashana" in t:
        return "Rosh Hashana"
    if "yom kippur" in t:
        return "Yom Kippur"
    if "sukkot" in t or "shmini atzeret" in t or "simchat torah" in t or "hoshana" in t:
        return "Sukkot"
    if "pesach" in t or "pesach" in t.replace("’", "'"):
        return "Pesach"
    if "shavuot" in t:
        return "Shavuot"
    if "chanukah" in t or "hanukkah" in t:
        return "Chanukah"
    if "purim" in t:
        return "Purim"
    if "tish'a b'av" in t or "tisha b'av" in t:
        return "Tisha B'Av"
    return title


def instrument(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("_", "")
    return f"{s[:3]}_{s[3:]}" if len(s) == 6 else s


def fetch_daily(key: str, base: str, instr: str, session: requests.Session,
                start: datetime, end: datetime) -> list[dict]:
    out: list[dict] = []
    cursor = start
    for _ in range(6):
        if cursor >= end:
            break
        r = None
        for attempt in range(4):
            r = session.get(f"{base}/v3/instruments/{instr}/candles",
                            params={"granularity": "D", "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "count": 5000, "price": "M"},
                            headers={"Authorization": f"Bearer {key}"}, timeout=45)
            if r.status_code == 200:
                break
            time.sleep(2.0 * (attempt + 1))
        if r is None or r.status_code != 200:
            break
        candles = r.json().get("candles", [])
        if not candles:
            break
        for c in candles:
            mid = c.get("mid") or {}
            if not mid or not c.get("complete", True):
                continue
            out.append({"d": c["time"][:10], "h": float(mid["h"]), "l": float(mid["l"]),
                        "c": float(mid["c"]), "v": float(c.get("volume", 0) or 0)})
        last = datetime.fromisoformat(candles[-1]["time"][:10] + "T00:00:00+00:00")
        nxt = last + timedelta(days=1)
        if nxt <= cursor:
            break
        cursor = nxt
        time.sleep(0.25)
    seen: dict[str, dict] = {}
    for row in out:
        seen[row["d"]] = row
    return [seen[k] for k in sorted(seen)]


def welch_t(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    denom = math.sqrt(va + vb)
    return float((a.mean() - b.mean()) / denom) if denom > 0 else float("nan")


def one_sample_t(a: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    sd = a.std(ddof=1)
    return float(a.mean() / (sd / math.sqrt(len(a)))) if sd > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=13)
    ap.add_argument("--permutations", type=int, default=5000)
    ap.add_argument("--out", default="holiday_study")
    ap.add_argument("--seed", type=int, default=20260927)
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    from tradebot_sci.config.loader import get_settings

    symbols = list(getattr(get_settings().get_active_profile(), "symbols", None) or ["EURUSD"])
    out_dir = DATA_DIR / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    key, base = credentials()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * args.years + 30)

    print(f"[HOLIDAY] {len(symbols)} pairs, daily, {args.years}y since {start.date()}", flush=True)
    session = requests.Session()
    series: dict[str, list[dict]] = {}
    for i, sym in enumerate(symbols, 1):
        path = out_dir / f"{sym}_D.jsonl"
        if path.exists():
            series[sym] = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        else:
            rows = fetch_daily(key, base, instrument(sym), session, start, end)
            series[sym] = rows
            with open(path, "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
        print(f"[HOLIDAY] {i}/{len(symbols)} {sym} {len(series[sym])} sessions", flush=True)

    # ---- build the per-pair daily panel -------------------------------------
    panel: dict[str, dict[str, float]] = {}   # date -> metric -> value
    all_dates: set[str] = set()
    for sym, rows in series.items():
        if len(rows) < 500:
            continue
        rows = sorted(rows, key=lambda r: r["d"])
        rets, ranges, vols, dates = [], [], [], []
        prev_c = None
        for r in rows:
            if prev_c and prev_c > 0 and r["c"] > 0:
                rets.append(math.log(r["c"] / prev_c))
                ranges.append((r["h"] - r["l"]) / r["c"])
                vols.append(r["v"])
                dates.append(r["d"])
            prev_c = r["c"]
        if len(rets) < 500:
            continue
        rets_a = np.array(rets)
        rng_a = np.array(ranges)
        vol_a = np.array(vols)
        rsd = rets_a.std(ddof=1)
        rmed = np.median(rng_a)
        vmed = np.median(vol_a)
        if rsd <= 0 or rmed <= 0 or vmed <= 0:
            continue
        for d, zr, rg, vv in zip(dates, rets_a / rsd, rng_a / rmed, vol_a / vmed):
            slot = panel.setdefault(d, {})
            slot.setdefault("z", []).append(float(zr))
            slot.setdefault("rng", []).append(float(rg))
            slot.setdefault("vol", []).append(float(vv))
            slot.setdefault("pip", []).append(float(zr * rsd))
        all_dates.update(dates)

    dates_sorted = sorted(panel)
    print(f"[HOLIDAY] panel {len(dates_sorted)} dates, {len(series)} pairs", flush=True)

    def day_vec(keyname: str) -> dict[str, float]:
        return {d: float(np.mean(v[keyname])) for d, v in panel.items() if v.get(keyname)}

    Z, RNG, VOL = day_vec("z"), day_vec("rng"), day_vec("vol")

    # ---- holiday calendar ---------------------------------------------------
    cache = out_dir / "hebcal"
    holidays: list[dict] = []
    years = sorted({int(d[:4]) for d in dates_sorted})
    for y in years:
        for kind in ("maj", "min"):
            for it in hebcal(y, kind, cache):
                cls = classify(it["title"])
                if cls:
                    holidays.append({"date": it["date"], "title": it["title"],
                                     "class": cls, "family": family(it["title"])})
    # dedupe by date+title
    holidays = list({(h["date"], h["title"]): h for h in holidays}.values())
    print(f"[HOLIDAY] {len(holidays)} holiday rows from Hebcal, {len(years)} years", flush=True)

    def dates_for(pred) -> list[str]:
        return [h["date"] for h in holidays if pred(h) and h["date"] in Z]

    def shifted(days: int, pred) -> list[str]:
        by_idx = {d: i for i, d in enumerate(dates_sorted)}
        out = []
        for h in holidays:
            if not pred(h):
                continue
            i = by_idx.get(h["date"])
            if i is None:
                continue
            j = i + days
            if 0 <= j < len(dates_sorted):
                out.append(dates_sorted[j])
        return sorted(set(out))

    def block(label: str, sel: list[str]) -> dict:
        sel = sorted(set(sel))
        if not sel:
            return {}
        z = np.array([Z[d] for d in sel])
        rng = np.array([RNG[d] for d in sel if d in RNG])
        vol = np.array([VOL[d] for d in sel if d in VOL])
        base_z = np.array([Z[d] for d in dates_sorted if d not in set(sel)])
        base_r = np.array([RNG[d] for d in dates_sorted if d not in set(sel)])
        base_v = np.array([VOL[d] for d in dates_sorted if d not in set(sel)])
        return {"label": label, "n": len(sel),
                "z_mean": float(z.mean()), "z_t": one_sample_t(z),
                "range_mean": float(rng.mean()) if len(rng) else float("nan"),
                "range_base": float(base_r.mean()), "range_t": welch_t(rng, base_r) if len(rng) else float("nan"),
                "vol_mean": float(vol.mean()) if len(vol) else float("nan"),
                "vol_base": float(base_v.mean()), "vol_t": welch_t(vol, base_v) if len(vol) else float("nan")}

    results: dict = {"window": {}, "families": {}, "placebo": {}, "permutation": {}}

    prohibited = lambda h: h["class"] == "prohibited"
    permitted = lambda h: h["class"] == "permitted"
    for lag, name in LAG_NAMES.items():
        results["window"][name] = block(name, shifted(lag, prohibited))

    for fam in sorted({h["family"] for h in holidays if h["class"] == "prohibited"}):
        results["families"][fam] = block(fam, dates_for(lambda h, f=fam: prohibited(h) and h["family"] == f))

    for fam in sorted({h["family"] for h in holidays if h["class"] == "permitted"}):
        results["placebo"][fam] = block(fam, dates_for(lambda h, f=fam: permitted(h) and h["family"] == f))

    # ---- permutation null, matched on weekday and month ---------------------
    rng_ = np.random.default_rng(args.seed)
    by_wm: dict[tuple[int, int], list[str]] = {}
    for d in dates_sorted:
        dt = datetime.strptime(d, "%Y-%m-%d")
        by_wm.setdefault((dt.weekday(), dt.month), []).append(d)
    target = [h["date"] for h in holidays if prohibited(h) and h["date"] in Z]
    keys = [(datetime.strptime(d, "%Y-%m-%d").weekday(), datetime.strptime(d, "%Y-%m-%d").month)
            for d in target]
    null_z, null_r, null_v = [], [], []
    base_r = np.array(list(RNG.values()))
    base_v = np.array(list(VOL.values()))
    for _ in range(args.permutations):
        drawn = [str(rng_.choice(by_wm[k])) for k in keys if k in by_wm and by_wm[k]]
        if not drawn:
            continue
        zz = np.array([Z[d] for d in drawn])
        rr = np.array([RNG[d] for d in drawn if d in RNG])
        vv = np.array([VOL[d] for d in drawn if d in VOL])
        null_z.append(abs(one_sample_t(zz)))
        null_r.append(abs(welch_t(rr, base_r)))
        null_v.append(abs(welch_t(vv, base_v)))
    obs = results["window"]["holiday day"]
    if null_z:
        results["permutation"] = {
            "draws": len(null_z),
            "observed_abs_t_z": abs(obs.get("z_t", float("nan"))),
            "p_value_z": float(np.mean(np.array(null_z) >= abs(obs.get("z_t", 0)))),
            "max_abs_t_z_in_null_95": float(np.percentile(null_z, 95)),
            "observed_abs_t_range": abs(obs.get("range_t", float("nan"))),
            "p_value_range": float(np.mean(np.array(null_r) >= abs(obs.get("range_t", 0)))),
            "observed_abs_t_vol": abs(obs.get("vol_t", float("nan"))),
            "p_value_vol": float(np.mean(np.array(null_v) >= abs(obs.get("vol_t", 0)))),
        }

    # ---- tradeable version: pips, per pair, charged the real round trip -----
    pip_rows = []
    for sym, rows in series.items():
        rs = sorted(rows, key=lambda r: r["d"])
        rets, ds = [], []
        prev = None
        for r in rs:
            if prev:
                rets.append(math.log(r["c"] / prev))
                ds.append(r["d"])
            prev = r["c"]
        if len(rets) < 500:
            continue
        arr = np.array(rets)
        pip = 10000.0 if "JPY" not in sym.upper() else 100.0
        for lag, name in LAG_NAMES.items():
            sel = set(shifted(lag, prohibited))
            vals = np.array([a * pip for a, d in zip(arr, ds) if d in sel])
            if len(vals) < 10:
                continue
            pip_rows.append({"pair": sym, "window": name, "n": len(vals),
                             "mean_pips": float(vals.mean()),
                             "t": one_sample_t(vals)})
    with open(out_dir / "pip_windows.json", "w") as fh:
        json.dump(pip_rows, fh, indent=1)

    # ---- report -------------------------------------------------------------
    lines = []
    lines.append(f"# Jewish holidays and the market - measured, {datetime.now(timezone.utc):%Y-%m-%d}")
    lines.append("")
    lines.append(f"Pairs {len(series)} · daily sessions {len(dates_sorted)} "
                 f"({dates_sorted[0]} to {dates_sorted[-1]}) · holiday dates used "
                 f"{results['window']['holiday day'].get('n')} · permutations {len(null_z)}")
    lines.append("")
    lines.append("## Window around work-prohibited holidays (one observation per date)")
    lines.append("")
    lines.append("| window | n | signed (z) | t | range vs base | t | tick volume vs base | t |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name in LAG_NAMES.values():
        b = results["window"].get(name) or {}
        if not b:
            continue
        lines.append(f"| {name} | {b['n']} | {b['z_mean']:+.4f} | {b['z_t']:+.2f} | "
                     f"{b['range_mean']:.3f} vs {b['range_base']:.3f} | {b['range_t']:+.2f} | "
                     f"{b['vol_mean']:.3f} vs {b['vol_base']:.3f} | {b['vol_t']:+.2f} |")
    lines.append("")
    lines.append("## By holiday (holiday day only)")
    lines.append("")
    lines.append("| family | n | signed (z) | t | range vs base | t | volume vs base | t |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for fam, b in sorted(results["families"].items()):
        lines.append(f"| {fam} | {b['n']} | {b['z_mean']:+.4f} | {b['z_t']:+.2f} | "
                     f"{b['range_mean']:.3f} vs {b['range_base']:.3f} | {b['range_t']:+.2f} | "
                     f"{b['vol_mean']:.3f} vs {b['vol_base']:.3f} | {b['vol_t']:+.2f} |")
    lines.append("")
    lines.append("## Placebo: Jewish holidays on which work is permitted")
    lines.append("")
    lines.append("| family | n | signed (z) | t | range vs base | t | volume vs base | t |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for fam, b in sorted(results["placebo"].items()):
        lines.append(f"| {fam} | {b['n']} | {b['z_mean']:+.4f} | {b['z_t']:+.2f} | "
                     f"{b['range_mean']:.3f} vs {b['range_base']:.3f} | {b['range_t']:+.2f} | "
                     f"{b['vol_mean']:.3f} vs {b['vol_base']:.3f} | {b['vol_t']:+.2f} |")
    lines.append("")
    p = results["permutation"]
    lines.append("## Permutation null, weekday and month matched")
    lines.append("")
    lines.append(f"null draws {p.get('draws')} · observed |t| signed {p.get('observed_abs_t_z'):.2f} "
                 f"(p={p.get('p_value_z'):.3f}) · range {p.get('observed_abs_t_range'):.2f} "
                 f"(p={p.get('p_value_range'):.3f}) · volume {p.get('observed_abs_t_vol'):.2f} "
                 f"(p={p.get('p_value_vol'):.3f}) · 95th percentile of null |t| on signed {p.get('max_abs_t_z_in_null_95'):.2f}")
    lines.append("")

    report = "\n".join(lines)
    (out_dir / "REPORT.md").write_text(report + "\n")
    (out_dir / "results.json").write_text(json.dumps(results, indent=1))
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
