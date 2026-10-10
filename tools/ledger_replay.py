#!/usr/bin/env python3
"""Replay a closed live trade against candles, to say where it went and not just where it left.

WHY THIS EXISTS. The live path records fills. It does not record excursions, so for
live trades 1 to 7 the ledger can say a trade lost 1R but cannot say whether it was
ever 1R in profit first, whether the stop was too tight, or whether the target was
too far. The live sampler (tools/oanda_trade.py excursions) answers that for trades
opened after 2026-10-07 and cannot answer it for anything before, because it samples
a position while it is open and by definition cannot sample the past.

So this walks the candles of a closed trade and reports the same two numbers the live
sampler reports: MFE, the furthest the trade ever ran in its own favour, and MAE, the
furthest it ever ran against. It also prices the one counterfactual the record cannot
otherwise test: what the trade would have done if the desk's own 24-hour time stop had
closed it, at market, on the hour.

WHAT IT IS NOT. Nothing here places, moves or closes anything, and it does not touch
the ledger. It is a read-only reading of OANDA's own M5 mid candles.

THE HONEST CAVEAT, and it matters. These excursions are RECONSTRUCTED FROM M5 MIDS,
not sampled live. A spike between two five-minute bars is invisible here and visible
to the live sampler, so every MFE and MAE printed here is a LOWER BOUND on the true
excursion. The two figures are a similar number wearing a similar name and they are
not the same measurement; the row says which one it is.

RULES, fixed before any result was read:
  - MFE and MAE are measured from the entry price on the mid candles, in units of the
    trade's own risk (entry to stop), signed so MFE can only be positive and MAE can
    only be negative.
  - The 24-hour counterfactual exits at market at the first M5 close at or after the
    horizon, and is charged the whole measured spread, because a market exit crosses
    it. A trade that hit its stop or target before the horizon is reported as having
    been decided by its own levels, since the horizon would never have been reached.
  - The stop and target used for that check are the trade's written bracket, adjusted
    by half the spread the way tools/shadow_book.py adjusts them: OANDA candles are
    mids, and an order fills when the side it trades on reaches the level.

Usage:
    python3 tools/ledger_replay.py                 # the table, for every live trade
    python3 tools/ledger_replay.py --json          # machine readable, to logs/
    python3 tools/ledger_replay.py --trade 3       # one trade

Requires OANDA_API_KEY in the environment. Source the secrets file first; never put a
key on a command line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import oanda_trade as ot  # noqa: E402  - the live tool holds the API and pip_size

HISTORY_CMD = [sys.executable, str(REPO / "tools" / "live_trade_history.py"), "--json"]
OUT_PATH = REPO / "logs" / "ledger_replay.json"

HORIZON_HOURS = 24.0


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def history() -> dict:
    """The seven live trades with their brackets, read through the history tool."""
    if not os.environ.get("OANDA_API_KEY"):
        sys.exit("OANDA_API_KEY not set. Source the secrets file first. Nothing was printed.")
    out = subprocess.run(HISTORY_CMD, capture_output=True, text=True, cwd=REPO)
    if out.returncode != 0:
        sys.exit(f"history read failed rc={out.returncode}: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout)


def candles(instrument: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """M5 mid candles across the window. The API caps a request at 5000 candles."""
    r = ot.api("GET", f"/v3/instruments/{instrument}/candles?granularity=M5"
                      f"&from={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                      f"&to={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&price=M")
    rows = []
    for c in r.get("candles", []):
        mid = c.get("mid") or {}
        if not mid:
            continue
        rows.append(dict(t=c["time"], o=float(mid["o"]), h=float(mid["h"]),
                         l=float(mid["l"]), c=float(mid["c"]), complete=c.get("complete", False)))
    return rows


def walk(trade: dict, bars: list[dict]) -> dict:
    """MFE, MAE and the R path of one trade, plus what a 24-hour time stop would have done.

    Pure: a trade and its candles in, measurements out. The R path is what the trade
    looked like while it was open, which is the figure the ledger is missing.
    """
    ins = trade["symbol"]
    ins = ins if "_" in ins else ins[:3] + "_" + ins[3:]
    ps = ot.pip_size(ins)
    entry = float(trade["entry"])
    short = trade["side"] == "short"
    risk = abs(entry - float(trade["stop"]))
    if not risk:
        return {"outcome": "ERROR", "detail": "entry equals stop, R is undefined"}
    spread_pips = 1.7 if trade["spread"].startswith("1.7") else 1.6
    half = spread_pips / 2 * ps
    stop, target = float(trade["stop"]), float(trade["target"])
    stop_at = stop - half if short else stop + half
    target_at = target - half if short else target + half
    opened = parse(trade["opened"])
    horizon = opened + dt.timedelta(hours=HORIZON_HOURS)

    path, mfe, mae = [], 0.0, 0.0
    decided, decided_at = None, None
    horizon_bar = None
    for c in bars:
        t = parse(c["t"])
        r = ((entry - c["c"]) if short else (c["c"] - entry)) / risk
        path.append(dict(t=c["t"], r=round(r, 4), close=c["c"]))
        favourable = ((entry - c["l"]) if short else (c["h"] - entry)) / risk
        adverse = ((entry - c["h"]) if short else (c["l"] - entry)) / risk
        mfe, mae = max(mfe, favourable), min(mae, adverse)
        if decided is None:
            hit_stop = c["h"] >= stop_at if short else c["l"] <= stop_at
            hit_target = c["l"] <= target_at if short else c["h"] >= target_at
            if hit_stop:
                decided, decided_at = "stopped", c["t"]
            elif hit_target:
                decided, decided_at = "target", c["t"]
        if horizon_bar is None and t >= horizon:
            horizon_bar = c
    if not bars:
        return {"outcome": "NO_DATA", "detail": "no candles in the window"}

    # The 24-hour counterfactual: only meaningful when the trade was still open at the
    # horizon, because a trade its own levels already closed never reached it.
    counter = None
    if decided is None and horizon_bar is not None:
        gross = ((entry - horizon_bar["c"]) if short else (horizon_bar["c"] - entry)) / risk
        counter = dict(exit_price=horizon_bar["c"], exit_at=horizon_bar["t"],
                       gross_r=round(gross, 3),
                       cost_r=round((spread_pips / (risk / ps)), 3),
                       net_r=round(gross - (spread_pips / (risk / ps)), 3))
    return {
        "instrument": ins,
        "side": trade["side"],
        "entry": entry, "stop": stop, "target": target,
        "risk_pips": round(risk / ps, 2),
        "spread_pips": spread_pips,
        "opened": trade["opened"], "closed": trade["closed"],
        "actual_r": trade["r"], "actual_pnl": trade["pnl"], "actual_result": trade["result"],
        "mfe_r": round(mfe, 3), "mae_r": round(mae, 3),
        "decided_by_levels": decided, "decided_at": decided_at,
        "horizon": horizon.isoformat(),
        "twenty_four_hour": counter,
        "bars": len(bars),
        "excursion_source": "reconstructed from M5 mid candles, a LOWER bound, not sampled live",
        "path": path,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay closed live trades against candles")
    ap.add_argument("--json", action="store_true", help=f"write {OUT_PATH.name} and print it")
    ap.add_argument("--trade", type=int, help="one trade number only")
    a = ap.parse_args()

    hist = history()
    trades = [t for t in hist["trades"] if a.trade is None or t["n"] == a.trade]
    rows = []
    for t in trades:
        ins = t["symbol"]
        ins = ins if "_" in ins else ins[:3] + "_" + ins[3:]
        bars = candles(ins, parse(t["opened"]), parse(t["closed"]))
        rows.append(dict(n=t["n"], **walk(t, bars)))

    if a.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(as_of=dt.datetime.now(dt.timezone.utc).isoformat(),
                       source="OANDA M5 mid candles, read through tools/ledger_replay.py",
                       trades=rows)
        OUT_PATH.write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload, indent=2))
        return

    print(f"{'#':>2}  {'pair':<8}{'entry':>9}  {'risk':>7}  {'MFE R':>7} {'MAE R':>7} "
          f"{'actual R':>8}  {'24h stop would be':<28}{'held':>10}")
    print("-" * 100)
    for r in rows:
        held = (parse(r["closed"]) - parse(r["opened"]))
        c = r["twenty_four_hour"]
        if c:
            cf = f"{c['net_r']:+.2f}R at {c['exit_at'][:16].replace('T', ' ')}Z"
        elif r["decided_by_levels"]:
            cf = f"n/a, its own {r['decided_by_levels']} got there first"
        else:
            cf = "n/a, no candle at the horizon"
        print(f"{r['n']:>2}  {r['instrument']:<8}{r['entry']:>9.5f}  {r['risk_pips']:>6.1f}p  "
              f"{r['mfe_r']:>+7.2f} {r['mae_r']:>+7.2f} {r['actual_r']:>+8.2f}  {cf:<28}"
              f"{str(held).split('.')[0]:>10}")
    print()
    print("MFE and MAE are RECONSTRUCTED from M5 mid candles, so they are lower bounds:")
    print("a spike between two five-minute bars is not seen here and is seen by the live")
    print("sampler. The live sampler cannot reach back before 2026-10-07, which is why")
    print("trades 1 to 7 had no excursion figure at all until this replay was written.")


if __name__ == "__main__":
    main()
