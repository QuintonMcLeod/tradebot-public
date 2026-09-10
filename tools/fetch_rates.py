#!/usr/bin/env python3
"""Fetch short-term interest-rate history so carry can be tested properly.

Carry is the interest-rate differential between the two legs of a pair, and it is
the best-documented factor in foreign exchange. The earlier attempt used a static
high-yield/low-yield basket, which is not a carry strategy — it is a bet that a
fixed set of currencies keeps winning, and it lost money over 2013-2026. This
pulls the actual rates.

Source: FRED's OECD three-month interbank series, which needs no API key and
covers the whole sample for every currency in the trading panel.

Usage:
    python3 tools/fetch_rates.py
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

SERIES = {
    "USD": "IR3TIB01USM156N",
    "EUR": "IR3TIB01EZM156N",
    "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N",
    "AUD": "IR3TIB01AUM156N",
    "NZD": "IR3TIB01NZM156N",
    "CAD": "IR3TIB01CAM156N",
    "CHF": "IR3TIB01CHM156N",
}
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def main() -> int:
    from tradebot_sci.paths import DATA_DIR

    out = DATA_DIR / "rates"
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    ok = 0
    for ccy, sid in SERIES.items():
        try:
            r = session.get(URL.format(sid=sid), timeout=40)
            r.raise_for_status()
        except requests.RequestException as exc:
            print(f"[RATES] {ccy} ({sid}): FAILED {exc}", flush=True)
            continue
        rows: list[tuple[str, str]] = []
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader, None)
        for row in reader:
            if len(row) < 2 or not row[1] or row[1] in (".", "NaN"):
                continue
            rows.append((row[0], row[1]))
        if not rows:
            print(f"[RATES] {ccy}: no usable rows", flush=True)
            continue
        path = out / f"{ccy}.csv"
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "rate_pct"])
            w.writerows(rows)
        ok += 1
        print(f"[RATES] {ccy} ({sid}): {len(rows)} months, "
              f"{rows[0][0]} to {rows[-1][0]}", flush=True)
    print(f"[RATES] wrote {ok}/{len(SERIES)} series to {out}", flush=True)
    return 0 if ok == len(SERIES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
