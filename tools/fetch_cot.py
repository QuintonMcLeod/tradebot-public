#!/usr/bin/env python3
"""Fetch CFTC positioning history (Traders in Financial Futures report).

Positioning is the one input in this study that is not derived from price. It is
also the oldest idea in the retail book: "the crowd is wrong at extremes". The
TFF report gives weekly net positions for leveraged funds and asset managers in
each currency's CME futures contract, which is the standard measure of
speculative positioning.

Source: CFTC public reporting API (no key). Covers 2006 onward, which overlaps the
23-year price panel from tools/backfill_daily_history.py.

Usage:
    python3 tools/fetch_cot.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

API = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CONTRACTS = {
    "099741": "EUR",
    "096742": "GBP",
    "097741": "JPY",
    "232741": "AUD",
    "112741": "NZD",
    "090741": "CAD",
    "092741": "CHF",
    "098662": "USD",   # dollar index, gives the USD leg
}


def main() -> int:
    from tradebot_sci.paths import DATA_DIR

    out = DATA_DIR / "cot"
    out.mkdir(parents=True, exist_ok=True)
    codes = "','".join(CONTRACTS)
    params = {
        "$where": f"cftc_contract_market_code in('{codes}')",
        "$limit": "50000",
        "$order": "report_date_as_yyyy_mm_dd",
        "$select": ("report_date_as_yyyy_mm_dd,cftc_contract_market_code,open_interest_all,"
                    "lev_money_positions_long,lev_money_positions_short,"
                    "asset_mgr_positions_long,asset_mgr_positions_short,"
                    "dealer_positions_long_all,dealer_positions_short_all"),
    }
    r = requests.get(API, params=params, timeout=90)
    r.raise_for_status()
    rows = r.json()
    print(f"[COT] fetched {len(rows)} weekly contract records")

    by_ccy: dict[str, dict[str, dict]] = {}
    for row in rows:
        code = row.get("cftc_contract_market_code")
        ccy = CONTRACTS.get(code)
        if not ccy:
            continue
        date = str(row.get("report_date_as_yyyy_mm_dd", ""))[:10]
        if not date:
            continue
        try:
            lev_l = float(row.get("lev_money_positions_long") or 0)
            lev_s = float(row.get("lev_money_positions_short") or 0)
            am_l = float(row.get("asset_mgr_positions_long") or 0)
            am_s = float(row.get("asset_mgr_positions_short") or 0)
            oi = float(row.get("open_interest_all") or 0)
        except ValueError:
            continue
        by_ccy.setdefault(ccy, {})[date] = {
            "date": date,
            "lev_net": lev_l - lev_s,
            "am_net": am_l - am_s,
            "open_interest": oi,
        }

    written = 0
    for ccy, series in sorted(by_ccy.items()):
        dates = sorted(series)
        if len(dates) < 52:
            print(f"[COT] {ccy}: only {len(dates)} weeks, skipped")
            continue
        path = out / f"{ccy}.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "lev_net", "am_net", "open_interest"])
            w.writeheader()
            for d in dates:
                w.writerow(series[d])
        written += 1
        print(f"[COT] {ccy}: {len(dates)} weeks, {dates[0]} to {dates[-1]}")
    print(f"[COT] wrote {written} series to {out}")
    return 0 if written >= 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
