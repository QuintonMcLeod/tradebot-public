#!/usr/bin/env python3
"""Live desk trade history, in the same column shape as the GUI Trade History table.

The GUI panel reads paper trades. This reads the LIVE OANDA account instead, so the
two are not interchangeable and must not be mixed. Columns mirror
`electron_gui/index.html` row 7: Time, Symbol, Side, Result, PnL, PnL %, MFE / MAE,
Spread, Duration, Strategy, Reason.

Two of those columns are computed here rather than read:

  PnL %   is PnL divided by the account balance at entry, and the balance at entry is
          reconstructed backwards from the current balance using the ledger P/L only.
          Financing is excluded, so each row is a fraction of a percent out. The
          reconstruction is printed so it can be checked.
  R       is not a GUI column but is added because it is the only scale-free way to
          compare these trades: they were sized at different fractions of NAV.

MFE and MAE are printed as `n/a` on purpose. The live path does not record excursion
data the way the paper store does, and inventing it from candles after the fact would
be a different number wearing the same name. `n/a` is the truth.

Stop, target, horizon and the thesis for each trade come from the written record, not
from the ledger, because the ledger holds fills only. Each row names its source.

`PnL @10k` and `Bal @10k` are a counterfactual: the same seven trades, in the same
order, at the same fraction of NAV that each one actually risked, compounding from a
starting balance given by `--capital` (default 10000) instead of the ~240 USD the desk
really started with. It is a scaling test, not a new strategy test. Because each trade
scaled with the account, the percentage return is IDENTICAL to the real account: only
the dollar figure changes. That is the point of the column, and it is why a bigger
balance does not make a thin edge thicker.

The risk fraction per trade is units times stop distance divided by the balance at
entry, both of which are computed here. The desk risked about 1 percent on trades 1 to
5 and about 3.7 to 4.0 percent on trades 6 and 7, the 4 percent rule having been set
on 2026-10-01.

Usage:
    python3 tools/live_trade_history.py              # aligned table
    python3 tools/live_trade_history.py --json       # machine readable
    python3 tools/live_trade_history.py --capital 25000

Requires OANDA_API_KEY in the environment. Source the secrets file first; never put a
key on a command line.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import oanda_trade as ot  # noqa: E402  - the live tool holds the API and the rails

# The live desk starts here. Everything before it is account history from a different
# experiment and must not enter this table; everything on or after it must, because a
# silently dropped trade shifts every bracket below it by one.
LIVE_START = datetime(2026, 9, 17, tzinfo=timezone.utc)
# A transaction-ID window wide enough to reach the desk start. Recent IDs are sparse
# (about 90 across the first live month), so 900 covers years, and the idrange endpoint
# caps a request at 1000 IDs, which is why this is not larger.
ID_WINDOW = 900

OPEN_REASONS = {"MARKET_ORDER"}

# The OANDA account is denominated in this currency, so every amount this tool reports
# as USD has to end up in it.
ACCOUNT_CURRENCY = "USD"

# Written record for each live trade: when it was opened, its stop and target, and
# where those numbers are recorded. The ledger supplies fills; it does not supply
# the bracket, because the bracket was decided by the session before the fill.
TRADE_META = [
    dict(n=1, opened="2026-09-17T08:36:13", stop=1.14870, target=1.14300,
         source="fact 117, paper_trades row 4"),
    dict(n=2, opened="2026-09-17T20:02:05", stop=1.15015, target=1.14490,
         source="paper_trades row 5 notes"),
    dict(n=3, opened="2026-09-23T18:01:55", stop=1.14220, target=1.13380,
         source="fact 135"),
    dict(n=4, opened="2026-09-29T18:04:21", stop=1.13550, target=1.13550 - 3 * (1.13550 - 1.13278),
         source="fact 142 (stop written 1.13550, filled 1.13551); target not separately recorded, 3R implied"),
    dict(n=5, opened="2026-09-30T13:05:30", stop=1.33200, target=1.32150,
         source="run_state.live_trading_record"),
    dict(n=6, opened="2026-10-05T13:08:00", stop=1.12370, target=1.11400,
         source="session_notes 101"),
    dict(n=7, opened="2026-10-06T13:06:50", stop=1.12900, target=1.11980,
         source="session_notes 105, run_state.live_trading_record"),
    dict(n=8, opened="2026-10-08T18:13:01", stop=1.41980, target=1.42900,
         source="run_state.live_trading_record"),
    dict(n=9, opened="2026-10-12T13:07:00", stop=1.11550, target=1.12330,
         source="session_notes 173, logs/agent_session_20261012T130439Z.out"),
    dict(n=10, opened="2026-10-12T18:06:21", stop=1.11850, target=1.11090,
         source="session_notes 174, logs/agent_session_20261012T180434Z.out"),
]

# Measured round-trip cost where the record holds a measurement. Where it does not,
# the recorded range for that pair and period is shown instead of a single figure.
MEASURED_COST = {
    1: "1.5 pips (round trip, measured at entry)",
    6: "1.7 pips (half spread 0.85 pips, measured on the fill)",
    7: "1.7 pips (half spread 0.85 pips, measured on the fill)",
    8: "1.6 pips (round trip, measured on the fill)",
    9: "1.6 pips (round trip, measured on the fill)",
    10: "1.5 pips (round trip, measured on the fill)",
}
DEFAULT_COST = "1.5 to 1.7 pips (recorded range for these pairs in this period)"

RESULT_LABEL = {
    "STOP_LOSS_ORDER": "stopped",
    "TAKE_PROFIT_ORDER": "target",
    "MARKET_ORDER": "closed by hand",
}


def ledger() -> list:
    """Read the OANDA transaction ledger for the live desk only.

    The transactions/sinceid endpoint used to be called here with its default 20-fill
    window. That window is an ID window scaled by three, and recent IDs are sparse, so
    by 2026-10-09 it began at live trade 2 and silently dropped trade 1; every bracket
    below the gap then shifted up one trade and the replay priced the wrong stop against
    the wrong entry. The desk start is now anchored explicitly with an ID range and the
    fills are filtered to LIVE_START, so a longer account history cannot move it.
    """
    if not os.environ.get("OANDA_API_KEY"):
        sys.exit("OANDA_API_KEY not set. Source the secrets file first. Nothing was printed.")
    last = int(ot.summary().get("lastTransactionID", 0))
    r = ot.api("GET", f"/v3/accounts/{{acct}}/transactions/idrange"
                      f"?from={max(1, last - ID_WINDOW)}&to={last}&type=ORDER_FILL")
    fills = [t for t in r.get("transactions", [])
             if t.get("time") and parse(t["time"]) >= LIVE_START]
    return sorted(fills, key=lambda t: t["time"])


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def pair_trades(txns: list) -> list:
    """Pair each opening fill with the closing fill that follows it in the same instrument.

    Matching on the instrument matters: the desk may hold up to three positions at once,
    and a first-in-first-out queue across instruments would hand one pair's exit to
    another pair's entry. Rows stay in chronological order of entry.
    """
    txns = sorted(txns, key=lambda t: t["time"])
    opens, rows = {}, []
    for t in txns:
        inst = t.get("instrument")
        is_open = (t.get("reason") in OPEN_REASONS
                   and t.get("pl", "0").lstrip("-").strip("0.") in ("", "0"))
        if is_open:
            opens.setdefault(inst, []).append(t)
            continue
        queue = opens.get(inst)
        if not queue:
            continue
        rows.append(dict(entry=queue.pop(0), exit=t))
    rows.sort(key=lambda r: r["entry"]["time"])
    return rows


def risk_in_account_currency(units: float, risk: float, entry_fill: dict) -> float:
    """Price a stop distance in the account's currency, not the pair's quote currency.

    The stop distance is a price in the pair's QUOTE currency, so units times distance is
    an amount of that quote currency. On a pair that is not quoted in the account currency
    the raw product is not dollars. USD_CAD is the case that bites: 6,290 units against a
    32.4-pip stop is 20.38 CAD, which is 14.47 USD, and reporting the unconverted figure
    reads as 8.1 percent of NAV against a 6 percent cap the trade did not breach.

    The rate comes from the broker's own loss-side factor on the entry fill rather than a
    rate invented here, because it is the factor the broker itself would use to convert a
    loss. A fill with no factor on a non-account currency is a hard error: a silent guess
    is the fault this file exists to stop.
    """
    factor = ((entry_fill.get("homeConversionFactors") or {}).get("lossQuoteHome")
              or {}).get("factor")
    if factor:
        return abs(units) * risk * float(factor)
    instrument = entry_fill.get("instrument", "")
    if instrument.split("_")[-1] != ACCOUNT_CURRENCY:
        sys.exit(f"No lossQuoteHome conversion factor on the {instrument} entry fill at "
                 f"{entry_fill.get('time')}, and it is not quoted in {ACCOUNT_CURRENCY}. "
                 f"Risk cannot be priced in account currency.")
    return abs(units) * risk


def build(capital: float = 10000.0) -> dict:
    txns = ledger()
    rows = pair_trades(txns)

    # Reconstruct the balance at each entry, backwards from the live balance, using
    # ledger P/L only. Financing is not in the ledger P/L and is therefore excluded.
    live = json.loads(subprocess.run(
        [sys.executable, str(REPO / "tools" / "oanda_trade.py"), "state"],
        capture_output=True, text=True, cwd=REPO,
    ).stdout or "{}")
    balance_now = float(live.get("balance") or 0.0)

    running = balance_now
    balance_at_entry = {}
    for r in reversed(rows):
        # The balance at ENTRY is the running balance less this trade's own result, so
        # the subtraction comes first. Doing it the other way round shifts every row by
        # one trade and silently corrupts both the percentage and the counterfactual.
        running -= float(r["exit"]["pl"])
        balance_at_entry[id(r["entry"])] = running
    opening_balance = running

    meta_by_open = {m["opened"]: m for m in TRADE_META}
    trades = []
    for i, r in enumerate(rows, start=1):
        e, x = r["entry"], r["exit"]
        # Bracket by the entry's own timestamp, not by position. A positional lookup
        # turns one missing ledger fill into every subsequent trade wearing the wrong
        # stop, which is silent and wrong. A missing bracket is loud instead.
        meta = meta_by_open.get(e["time"][:19])
        if meta is None:
            sys.exit(f"No written bracket for live entry {e.get('instrument')} at "
                     f"{e['time']}. The ledger holds fills only; add stop and target to "
                     f"TRADE_META before this tool can price the trade.")
        units = float(e["units"])
        entry_px, exit_px = float(e["price"]), float(x["price"])
        pnl = float(x["pl"])
        stop = meta.get("stop")
        target = meta.get("target")
        bal = balance_at_entry[id(e)]

        risk = abs(stop - entry_px) if stop else None
        # Short when units are negative: R = (entry - exit) / (stop - entry).
        if risk:
            direction = -1.0 if units < 0 else 1.0
            r_mult = ((exit_px - entry_px) * direction) / (risk if direction < 0 else -risk)
            r_mult = abs(r_mult) if pnl >= 0 else -abs(r_mult)
        else:
            r_mult = None

        opened, closed = parse(e["time"]), parse(x["time"])
        secs = (closed - opened).total_seconds()

        # The stop distance is priced in the pair's QUOTE currency, so convert it into the
        # account's currency before calling it an amount of money.
        risk_usd = risk_in_account_currency(units, risk, e) if risk else None
        risk_frac = (risk_usd / bal) if risk_usd else None

        trades.append(dict(
            n=i,
            opened=opened.isoformat(),
            closed=closed.isoformat(),
            symbol=e["instrument"].replace("_", ""),
            side="short" if units < 0 else "long",
            units=abs(units),
            entry=entry_px,
            exit=exit_px,
            stop=stop,
            target=target,
            pnl=pnl,
            pnl_pct=pnl / bal * 100.0,
            r=r_mult,
            result=RESULT_LABEL.get(x.get("reason"), x.get("reason")),
            reason=x.get("reason"),
            spread=MEASURED_COST.get(i, DEFAULT_COST),
            duration_s=secs,
            duration=fmt_duration(secs),
            strategy="live desk (discretionary)",
            balance_at_entry=bal,
            risk_usd=risk_usd,
            risk_frac=risk_frac,
            source=meta.get("source", "not recorded"),
        ))

    # Counterfactual: same trades, same fraction of NAV risked, different starting
    # capital. Scaling only, so the percentage return must come out the same.
    bal = capital
    for t in trades:
        if t["risk_frac"] is None or t["r"] is None:
            t["pnl_theoretical"], t["balance_theoretical"] = None, bal
            continue
        pnl_t = bal * t["risk_frac"] * t["r"]
        bal += pnl_t
        t["pnl_theoretical"] = pnl_t
        t["balance_theoretical"] = bal

    # Second counterfactual for reference: the desk's current standing rule, a flat
    # 4 percent of NAV on every entry, which is not what trades 1 to 5 actually did.
    bal4 = capital
    for t in trades:
        if t["r"] is None:
            continue
        bal4 += bal4 * 0.04 * t["r"]
    flat4_final = bal4

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    rs = [t["r"] for t in trades if t["r"] is not None]
    return dict(
        as_of=datetime.now(timezone.utc).isoformat(),
        balance=balance_now,
        opening_balance=opening_balance,
        net_pnl=sum(t["pnl"] for t in trades),
        net_pct=(balance_now / opening_balance - 1) * 100.0 if opening_balance else None,
        trades=trades,
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(trades) * 100.0 if trades else None,
        r_sum=sum(rs) if rs else None,
        r_mean=(sum(rs) / len(rs)) if rs else None,
        target_reached=sum(1 for t in trades if t["result"] == "target"),
        stopped=sum(1 for t in trades if t["result"] == "stopped"),
        by_hand=sum(1 for t in trades if t["result"] == "closed by hand"),
        theoretical=dict(
            capital=capital,
            final=bal,
            pnl=bal - capital,
            pct=(bal / capital - 1) * 100.0,
            flat4_final=flat4_final,
            flat4_pct=(flat4_final / capital - 1) * 100.0,
        ),
    )


def fmt_duration(secs: float) -> str:
    h, m = divmod(int(secs) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def table(d: dict) -> str:
    th = d["theoretical"]
    cap = th["capital"]
    tag = f"{cap:,.0f}"
    hdr = (f"  #  Opened (UTC)      Symbol  Side   Result          "
           f" PnL USD   PnL %      R  PnL @{tag:<8} Bal @{tag:<9} Dur     Spread    Reason")
    lines = [hdr, "-" * len(hdr)]
    for t in d["trades"]:
        theo = ("      n/a  " if t["pnl_theoretical"] is None
                else f"{t['pnl_theoretical']:>+11.2f}")
        bal = ("      n/a  " if t["pnl_theoretical"] is None
               else f"{t['balance_theoretical']:>13,.2f}")
        spread = t["spread"].split(" (")[0]
        lines.append(
            f"{t['n']:>3}  {t['opened'][:16].replace('T', ' ')}  {t['symbol']:<6}  "
            f"{t['side']:<5}  {t['result']:<13}  {t['pnl']:>+8.4f}  {t['pnl_pct']:>+6.2f}%  "
            f"{t['r']:>+5.2f}  {theo}  {bal}  {t['duration']:<6}  {spread:<8}  {t['reason']}"
        )
    lines.append("")
    lines.append(f"entries {len(d['trades'])}, wins {d['wins']}, losses {d['losses']}, "
                 f"win rate {d['win_rate']:.0f}%, targets {d['target_reached']}, "
                 f"stops {d['stopped']}, closed by hand {d['by_hand']}")
    lines.append(f"net PnL {d['net_pnl']:+.4f} USD, sum of R {d['r_sum']:+.2f}R, "
                 f"mean {d['r_mean']:+.3f}R per trade")
    lines.append(f"real account: {d['opening_balance']:.2f} -> {d['balance']:.2f} "
                 f"= {d['net_pct']:+.2f}%")
    lines.append(f"at {cap:,.0f}: {cap:,.2f} -> {th['final']:,.2f} "
                 f"= {th['pnl']:+,.2f} USD, {th['pct']:+.2f}%")
    lines.append(f"  the percentage is the same as the real account on purpose. Each trade "
                 f"was sized as a")
    lines.append(f"  fraction of NAV, so scaling the capital scales the dollars and leaves "
                 f"the return")
    lines.append(f"  unchanged. A larger balance does not improve the edge, it only "
                 f"multiplies it.")
    lines.append(f"at {cap:,.0f} risking a flat 4% on every entry (the desk rule since "
                 f"2026-10-01, which trades")
    lines.append(f"  1 to 5 did not follow): {th['flat4_final']:,.2f} = "
                 f"{th['flat4_pct']:+.2f}%. The difference is sizing, not signal.")
    lines.append("")
    lines.append("MFE / MAE: n/a. The live path records fills, not excursions, and a figure")
    lines.append("reconstructed from candles afterwards would be a different number.")
    lines.append("PnL % is against the balance at entry, reconstructed backwards from the live")
    lines.append("balance using ledger P/L only. Financing is excluded from the reconstruction.")
    lines.append("At 10,000 the account would also qualify for OANDA's commission based tier, "
                 "which fact 9")
    lines.append("records as unavailable below that minimum. That cost change is NOT in this "
                 "table and is")
    lines.append("a real reason a larger balance could beat the pure scaling shown here.")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine readable output")
    ap.add_argument("--capital", type=float, default=10000.0,
                    help="starting balance for the counterfactual column (default 10000)")
    args = ap.parse_args()
    data = build(capital=args.capital)
    print(json.dumps(data, indent=2) if args.json else table(data))
