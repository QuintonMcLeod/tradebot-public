#!/usr/bin/env python3
"""The shadow book: the setups the desk looked at and did NOT take, scored like trades.

WHY THIS EXISTS. Seven entries in forty-one logged trade sessions. The other
thirty-four sessions ended in standing aside, and what was passed over was written
as prose in a note, so the busiest part of this desk has never been scored. The
entry filter is therefore a reputation, not a measurement: there is no way to say
whether the caution is earning money or losing it.

So every rejected setup becomes a row with a price and a deadline on it, and later
gets scored against the candles exactly as a real trade would. The answer this file
produces is one number: the net R of the trades the desk declined.

WHAT IT IS NOT. Nothing here places, moves or closes an order, and nothing here
feeds the entry decision. It is a scoreboard, deliberately kept out of the loop, so
reading it cannot flatter the thing it measures.

RULES THE SCORE USES, fixed before any result is read:

  - The stop wins a bar in which both the stop and the target are touched. This
    project already measures its barriers with the stop-wins assumption (facts 145,
    146) and the scoreboard must not be more generous than the test it exists to
    inform. Such a bar is flagged `ambiguous` so it can be excluded later.
  - If neither level is reached by the horizon, the setup is marked out at the last
    close: a setup with an expiry is scored with its expiry.
  - The desk's own measured spread is charged on every outcome. A setup that only
    works before costs is not a setup.
  - MFE and MAE come from the candles, not from live sampling, and are labelled as
    reconstructed. They are a finer measure than the live sampler and they are a
    different number wearing a similar name; do not mix the two.

Usage:
    tools/shadow_book.py add --instrument EUR_USD --side short --stop 1.12900 \
        --target 1.11980 --horizon-hours 24 --reason "retrace of the 76% level" \
        [--entry 1.12613] [--spread-pips 1.7]
    tools/shadow_book.py score          # price every setup whose horizon has passed
    tools/shadow_book.py report         # the table, and the total the passes cost or saved
    tools/shadow_book.py pending        # what is still waiting to be scored

Requires OANDA_API_KEY in the environment for `add` without --entry and for `score`.
Source the secrets file first; never put a key on a command line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import uuid

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import oanda_trade as ot  # noqa: E402  - the live tool holds the API, the rails and pip_size

SETUPS = REPO / "logs" / "shadow_setups.jsonl"
RESULTS = REPO / "logs" / "shadow_results.jsonl"

# The spread this desk actually pays, measured on its fills (1.5 to 1.7 pips). A
# setup added without one is charged this, and the row records which was used.
DEFAULT_SPREAD_PIPS = 1.7

TIE_RULE = "stop"


# ── pure helpers, so the scoring rule can be tested without a network ──

def pip_size(instrument: str) -> float:
    return ot.pip_size(instrument)


def risk_pips(entry: float, stop: float, instrument: str) -> float:
    return abs(entry - stop) / pip_size(instrument)


def reward_ratio(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    return abs(target - entry) / risk if risk else 0.0


def score_setup(setup: dict, candles: list[dict]) -> dict:
    """Walk the candles after the decision and say what taking this setup would have done.

    Pure: candles in, outcome out. No clock, no network, no file. The order of the
    checks is the rule: a stop and a target touched inside the same bar is a stop,
    per TIE_RULE, and each bar is examined high-then-low so the answer never depends
    on which of the two a loop happened to read first.

    THE WALK USES SPREAD-ADJUSTED LEVELS, AND THAT IS NOT A DETAIL. OANDA candles are
    mid prices; a real order fills when the side it trades on reaches the level. A
    short's target is a buy limit at T, so it fills when the ask reaches T, which is
    when the mid reaches T minus half the spread. Walking raw mid levels counts a
    graze as a win: verified against live trade 5, where the mid first touched the
    1.32150 target at 08:40Z and the broker filled it at 08:53Z, thirteen minutes of
    optimism that a scoreboard built to judge the entry filter cannot afford.
    """
    ins = setup["instrument"]
    ps = pip_size(ins)
    entry, stop, target = float(setup["entry"]), float(setup["stop"]), float(setup["target"])
    long = setup["side"] == "long"
    risk = abs(entry - stop)
    if not risk:
        return {"outcome": "ERROR", "detail": "entry equals stop, R is undefined"}
    rr = reward_ratio(entry, stop, target)
    spread_pips = float(setup.get("spread_pips") or DEFAULT_SPREAD_PIPS)
    half = spread_pips / 2 * ps                         # half the spread, in price

    mfe = mae = 0.0
    outcome, exit_price, exit_at, bars, ambiguous = None, None, None, 0, False
    for c in candles:
        bars += 1
        high, low = float(c["h"]), float(c["l"])
        # Measured from the position's own side: a short is best at the bar's low and
        # worst at its high, and the adverse figure is signed, so MAE can only be
        # negative and MFE can only be positive.
        if long:
            favourable, adverse = (high - entry) / ps, (low - entry) / ps
        else:
            favourable, adverse = (entry - low) / ps, (entry - high) / ps
        mfe, mae = max(mfe, favourable), min(mae, adverse)
        # Where the order would actually fill, not where the mid first grazed it.
        stop_at = stop + half if long else stop - half
        target_at = target + half if long else target - half
        hit_stop = low <= stop_at if long else high >= stop_at
        hit_target = high >= target_at if long else low <= target_at
        if hit_stop and hit_target:
            ambiguous = True
        if hit_stop:
            outcome, exit_price, exit_at = "stopped", stop, c["t"]
            break
        if hit_target:
            outcome, exit_price, exit_at = "target", target, c["t"]
            break
    if outcome is None:
        if not candles:
            return {"outcome": "NO_DATA", "detail": "no candles in the window"}
        outcome, exit_price, exit_at = "time", float(candles[-1]["c"]), candles[-1]["t"]

    if outcome == "stopped":
        gross_r = -1.0
    elif outcome == "target":
        gross_r = rr
    else:
        move = (exit_price - entry) if long else (entry - exit_price)
        gross_r = (move / ps) / (risk / ps)             # pips of move over pips of risk
    # The cost, matched to how the setup would have left. A level exit is a limit or a
    # stop filling AT its level, so only the entry has to cross the spread, and half of
    # it is charged. A time exit is a market order at both ends, so the whole spread is
    # charged. The walk above already used the adjusted levels, so nothing is counted
    # twice: the figures used here are pips of spread over pips of risk.
    spread_pips = float(setup.get("spread_pips") or DEFAULT_SPREAD_PIPS)
    cost_r = (spread_pips if outcome == "time" else spread_pips / 2) / (risk / ps)
    return {
        "outcome": outcome,
        "gross_r": round(gross_r, 3),
        "cost_r": round(cost_r, 3),
        "net_r": round(gross_r - cost_r, 3),
        "exit_price": round(exit_price, 6),
        "exit_at": exit_at,
        "bars": bars,
        "ambiguous": ambiguous,
        "levels_adjusted_pips": round(spread_pips / 2, 2),
        "mfe_r": round(mfe / (risk / ps), 3),
        "mae_r": round(mae / (risk / ps), 3),
        "excursion_source": "reconstructed from M5 candles, not sampled live",
        "tie_rule": TIE_RULE,
    }


# ── storage: append only, one setup per line, results kept separately ──

def read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:                             # noqa: BLE001 - a torn line is skipped, not fatal
            continue
    return out


def append_jsonl(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def candles_between(instrument: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """M5 candles across the window, so a stop at 03:12 is not missed by an hourly bar."""
    span_hours = max(1.0, (end - start).total_seconds() / 3600)
    gran = "M5" if span_hours <= 72 else ("M15" if span_hours <= 240 else "H1")
    r = ot.api("GET", f"/v3/instruments/{instrument}/candles?granularity={gran}"
                      f"&from={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                      f"&to={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&price=M")
    return [{"t": c["time"], "o": c["mid"]["o"], "h": c["mid"]["h"],
             "l": c["mid"]["l"], "c": c["mid"]["c"]} for c in r.get("candles", [])]


def resolve_entry(setup: dict) -> dict:
    """Fill in the entry from the live book when the session did not write one down."""
    if setup.get("entry"):
        return setup
    q = ot.quote_one(setup["instrument"])
    setup["entry"] = float(q["ask"] if setup["side"] == "long" else q["bid"])
    setup["entry_source"] = "live quote at add time, exit side"
    return setup


# ── commands ──

def cmd_add(a) -> None:
    ins = a.instrument.upper()
    if "_" not in ins and len(ins) == 6:
        ins = f"{ins[:3]}_{ins[3:]}"
    now = dt.datetime.now(dt.timezone.utc)
    decided = dt.datetime.fromisoformat(a.decided_at) if a.decided_at else now
    if decided.tzinfo is None:
        decided = decided.replace(tzinfo=dt.timezone.utc)
    setup = {
        "id": uuid.uuid4().hex[:12],
        "decided_at": decided.isoformat(),
        "window": f"{decided.strftime('%H')}:00",
        "instrument": ins, "side": a.side.lower(),
        "entry": a.entry, "stop": float(a.stop), "target": float(a.target),
        "horizon_hours": float(a.horizon_hours),
        "horizon_at": (decided + dt.timedelta(hours=float(a.horizon_hours))).isoformat(),
        "spread_pips": float(a.spread_pips) if a.spread_pips else DEFAULT_SPREAD_PIPS,
        "spread_source": "given on the command line" if a.spread_pips
                         else f"desk default {DEFAULT_SPREAD_PIPS} pips, measured on its fills",
        "reason": a.reason,
        "recorded_by": a.recorded_by,
    }
    setup = resolve_entry(setup)
    setup["risk_pips"] = round(risk_pips(setup["entry"], setup["stop"], ins), 1)
    setup["rr"] = round(reward_ratio(setup["entry"], setup["stop"], setup["target"]), 2)
    append_jsonl(pathlib.Path(a.file) if a.file else SETUPS, setup)
    print(json.dumps({"added": setup["id"], "instrument": ins, "side": setup["side"],
                      "entry": setup["entry"], "stop": setup["stop"], "target": setup["target"],
                      "risk_pips": setup["risk_pips"], "rr": setup["rr"],
                      "horizon_at": setup["horizon_at"], "window": setup["window"]}, indent=2))


def cmd_score(a) -> None:
    setups_path = pathlib.Path(a.file) if a.file else SETUPS
    results_path = pathlib.Path(a.results_file) if a.results_file else RESULTS
    setups = read_jsonl(setups_path)
    done = {r["id"] for r in read_jsonl(results_path)}
    now = dt.datetime.now(dt.timezone.utc)
    scored, waiting = [], 0
    for s in setups:
        if s["id"] in done:
            continue
        horizon = dt.datetime.fromisoformat(s["horizon_at"])
        if horizon > now and not a.force:
            waiting += 1
            continue
        start = dt.datetime.fromisoformat(s["decided_at"])
        end = min(horizon, now)
        try:
            candles = candles_between(s["instrument"], start, end)
            result = {"id": s["id"], "scored_at": now.isoformat(),
                      "instrument": s["instrument"], "side": s["side"],
                      "decided_at": s["decided_at"], "window": s.get("window"),
                      "reason": s.get("reason"),
                      "entry": s["entry"], "stop": s["stop"], "target": s["target"],
                      "risk_pips": s.get("risk_pips"), "rr": s.get("rr"),
                      **score_setup(s, candles)}
        except Exception as exc:                      # noqa: BLE001 - one bad row must not stop the sweep
            result = {"id": s["id"], "scored_at": now.isoformat(),
                      "instrument": s["instrument"], "window": s.get("window"),
                      "outcome": "ERROR", "detail": str(exc)[:200]}
        append_jsonl(results_path, result)
        scored.append(result)
    print(json.dumps({"scored": scored, "still_waiting": waiting,
                      "results_file": str(results_path)}, indent=2))


def cmd_report(a) -> None:
    setups_path = pathlib.Path(a.file) if a.file else SETUPS
    results_path = pathlib.Path(a.results_file) if a.results_file else RESULTS
    setups = {s["id"]: s for s in read_jsonl(setups_path)}
    results = [r for r in read_jsonl(results_path) if r.get("outcome") not in (None, "ERROR")]
    if not results:
        print(json.dumps({"setups_recorded": len(setups), "scored": 0,
                          "note": "nothing scored yet; run score after a setup's horizon passes"},
                         indent=2))
        return

    def summarise(rows: list[dict]) -> dict:
        net = [r["net_r"] for r in rows]
        return {
            "n": len(rows),
            "target": sum(1 for r in rows if r["outcome"] == "target"),
            "stopped": sum(1 for r in rows if r["outcome"] == "stopped"),
            "time": sum(1 for r in rows if r["outcome"] == "time"),
            "ambiguous": sum(1 for r in rows if r.get("ambiguous")),
            "sum_net_r": round(sum(net), 3),
            "mean_net_r": round(sum(net) / len(net), 3),
        }

    by_window: dict[str, list[dict]] = {}
    for r in results:
        by_window.setdefault(str(r.get("window") or "?"), []).append(r)

    body = {
        "setups_recorded": len(setups),
        "summary": summarise(results),
        "by_window": {w: summarise(rows) for w, rows in sorted(by_window.items())},
        "reading": "A POSITIVE sum means the setups the desk declined would have made money, "
                   "so the entry filter is too tight. A NEGATIVE sum means the caution is "
                   "earning its keep. Neither is a result at a handful of setups.",
        "trades": [{k: r.get(k) for k in
                    ("decided_at", "window", "instrument", "side", "rr", "outcome",
                     "gross_r", "cost_r", "net_r", "mfe_r", "mae_r", "reason")}
                   for r in sorted(results, key=lambda r: r.get("decided_at") or "")],
    }
    if a.json:
        print(json.dumps(body, indent=2))
        return

    s = body["summary"]
    print(f"shadow book: {s['n']} setups scored, "
          f"{s['target']} would have hit target, {s['stopped']} stopped, {s['time']} timed out")
    print(f"declined setups scored net {s['sum_net_r']:+.2f}R "
          f"({s['mean_net_r']:+.3f}R each, spread charged)")
    print()
    print(f"{'decided (UTC)':<17} {'win':<6} {'inst':<8} {'side':<5} {'R:R':>5} "
          f"{'outcome':<9} {'net R':>7} {'MFE':>6} {'MAE':>6}  reason")
    for r in body["trades"]:
        print(f"{str(r['decided_at'])[:16]:<17} {str(r['window']):<6} {str(r['instrument']):<8} "
              f"{str(r['side']):<5} {float(r['rr'] or 0):>5.2f} {str(r['outcome']):<9} "
              f"{float(r['net_r']):>+7.2f} {float(r['mfe_r']):>6.2f} {float(r['mae_r']):>6.2f}  "
              f"{str(r['reason'] or '')[:60]}")
    print()
    for w, agg in body["by_window"].items():
        print(f"  window {w}: n={agg['n']} net {agg['sum_net_r']:+.2f}R "
              f"(mean {agg['mean_net_r']:+.3f}R)")
    print()
    print(body["reading"])


def cmd_pending(a) -> None:
    setups = read_jsonl(pathlib.Path(a.file) if a.file else SETUPS)
    done = {r["id"] for r in read_jsonl(pathlib.Path(a.results_file) if a.results_file else RESULTS)}
    now = dt.datetime.now(dt.timezone.utc)
    rows = [s for s in setups if s["id"] not in done]
    due = [s for s in rows if dt.datetime.fromisoformat(s["horizon_at"]) <= now]
    print(json.dumps({"unscored": len(rows), "due_now": len(due),
                      "next_due": min((s["horizon_at"] for s in rows), default=None),
                      "setups": [{"id": s["id"], "window": s.get("window"),
                                  "instrument": s["instrument"], "side": s["side"],
                                  "horizon_at": s["horizon_at"]} for s in rows]}, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the setups the desk declined.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="record a setup the desk looked at and passed on")
    p.add_argument("--instrument", required=True)
    p.add_argument("--side", required=True, choices=["long", "short", "Long", "Short"])
    p.add_argument("--stop", required=True, help="where the trade would have been stopped out")
    p.add_argument("--target", required=True, help="where it would have been taken off")
    p.add_argument("--entry", type=float, default=None,
                   help="the price it would have entered at; omitted means the live quote now")
    p.add_argument("--horizon-hours", required=True, type=float,
                   help="how long the thesis would have been good for, in hours")
    p.add_argument("--reason", required=True, help="the thesis, and why it was declined")
    p.add_argument("--spread-pips", type=float, default=None)
    p.add_argument("--decided-at", default=None, help="ISO time of the decision, for backfill")
    p.add_argument("--recorded-by", default="tradebot_sci")
    p.add_argument("--file", default=None, help="override the setups file (tests, experiments)")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("score", help="price every setup whose horizon has passed")
    p.add_argument("--force", action="store_true", help="score before the horizon passes")
    p.add_argument("--file", default=None)
    p.add_argument("--results-file", default=None)
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("report", help="the table, and what the passes cost or saved")
    p.add_argument("--json", action="store_true")
    p.add_argument("--file", default=None)
    p.add_argument("--results-file", default=None)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("pending", help="what is still waiting to be scored")
    p.add_argument("--file", default=None)
    p.add_argument("--results-file", default=None)
    p.set_defaults(fn=cmd_pending)

    a = ap.parse_args()
    if a.cmd in ("score", "add") and not os.environ.get("OANDA_API_KEY"):
        sys.exit("OANDA_API_KEY not set. Source ~/.config/secrets/.env.secrets first.")
    a.fn(a)


if __name__ == "__main__":
    main()
