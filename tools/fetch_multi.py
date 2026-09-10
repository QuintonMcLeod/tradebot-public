#!/usr/bin/env python3
"""Fetch long daily history for a diversified multi-asset basket.

The FX study ended on a structural point rather than a signal: on this account the
moves are small and the toll is fixed, and no pattern in the tested families beat
it. That raises a question the FX data cannot answer — is the problem foreign
exchange, or is it systematic trading in general?

To find out, the same harness needs markets whose instruments have carried
documented risk premia for a century. This fetches daily bars from Yahoo's public
chart endpoint for equity indices, commodities and bonds, several of them with
history back to the 1980s or earlier.

Usage:
    python3 tools/fetch_multi.py
    python3 tools/fetch_multi.py --symbols "^GSPC,GC=F"
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# Label -> Yahoo symbol. Chosen for long history and for covering the main
# documented premia: equity risk, commodity carry/trend, and bond duration.
DEFAULT = {
    "SPX": "^GSPC",       # S&P 500, 1927+
    "NDX": "^NDX",        # Nasdaq 100, 1985+
    "DAX": "^GDAXI",      # DAX
    "NIKKEI": "^N225",    # Nikkei 225
    "FTSE": "^FTSE",      # FTSE 100
    "GOLD": "GC=F",       # gold futures
    "SILVER": "SI=F",     # silver futures
    "WTI": "CL=F",        # crude oil futures
    "COPPER": "HG=F",     # copper futures
    "UST10": "ZN=F",      # 10-year note futures
    "UST30": "ZB=F",      # 30-year bond futures
    "DXY": "DX-Y.NYB",    # dollar index
    "TLT": "TLT",         # long bond ETF
    "GLD": "GLD",         # gold ETF
}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch(symbol: str, start: datetime, session: requests.Session) -> list[dict]:
    params = {
        "period1": int(start.timestamp()),
        "period2": int(datetime.now(timezone.utc).timestamp()),
        "interval": "1d",
        "events": "div,splits",
    }
    for attempt in range(4):
        r = session.get(URL.format(sym=requests.utils.quote(symbol)),
                        params=params, headers=HEADERS, timeout=45)
        if r.status_code == 200:
            break
        time.sleep(2.0 * (attempt + 1))
    else:
        return []
    try:
        result = r.json()["chart"]["result"][0]
        stamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []
    adj = None
    try:
        adj = result["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError, TypeError):
        pass

    rows = []
    for i, ts in enumerate(stamps):
        c = quote["close"][i]
        if c is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "open": quote["open"][i] if quote["open"][i] is not None else c,
            "high": quote["high"][i] if quote["high"][i] is not None else c,
            "low": quote["low"][i] if quote["low"][i] is not None else c,
            "close": c,
            "adjclose": (adj[i] if adj and adj[i] is not None else c),
            "volume": quote["volume"][i] if quote["volume"][i] is not None else 0,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=None, help="Comma list of Yahoo symbols")
    ap.add_argument("--years", type=int, default=40)
    args = ap.parse_args()

    from tradebot_sci.paths import DATA_DIR
    out = DATA_DIR / "multi"
    out.mkdir(parents=True, exist_ok=True)

    if args.symbols:
        targets = {s.strip().upper(): s.strip() for s in args.symbols.split(",")}
    else:
        targets = DEFAULT

    start = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - args.years)
    session = requests.Session()
    ok = 0
    for label, sym in targets.items():
        rows = fetch(sym, start, session)
        if len(rows) < 500:
            print(f"[MULTI] {label} ({sym}): only {len(rows)} bars, skipped", flush=True)
            continue
        path = out / f"{label}.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close",
                                               "adjclose", "volume"])
            w.writeheader()
            w.writerows(rows)
        ok += 1
        print(f"[MULTI] {label} ({sym}): {len(rows)} bars, {rows[0]['date']} to {rows[-1]['date']}",
              flush=True)
        time.sleep(0.6)
    print(f"[MULTI] wrote {ok}/{len(targets)} series to {out}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
