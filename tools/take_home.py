#!/usr/bin/env python3
"""Take-home calculation for the live desk.

Steven's order, 2026-10-12, in the Office room: "I also need you to calculate a take
home profit on wins. That way i can profit before you put the winnings back out on the
market." He picked the rule the same day: per win, the bot's own tiers, and pay only
once the account is back at its own peak.

THE RULE IS TRADEBOT SCI'S, READ FROM IT RATHER THAN INVENTED. The Payout Mentor lives
in src/tradebot_sci/electron_gui/analytics.js (the live card) and tools/paper_replay.py
(the replay card), and Documentation/RTFM/53_TARGET.md writes it out for a reader:

    take 50 percent of a winning trade's realized profit;
    take 75 percent when that win is 2.5 percent or more of the account;
    take nothing while a position is open, which the mentor calls LOCKED, because
    pulling capital with a trade live cuts the margin under it;
    take nothing while the account sits below its own peak, which the mentor calls
    SHIELDED, because those winners are rebuilding a drawdown and not paying a wage.

THE PEAK is the highest balance since the last payout. That is the mentor's "active
capital base": after a payout the account is re-based, so the next payout comes out of
new ground rather than out of capital already paid from.

MONEY THAT LEAVES IS ADDED BACK IN THE ARITHMETIC. A withdrawal is not a fill, so the
ledger knows nothing about it, and every balance reconstructed backwards from the
balance today is short by whatever has been taken out since. Two consequences, both
fixed here rather than estimated: the peak has to be held on the as-it-stood basis
(so a payout does not permanently shield the desk it just paid from), and a balance
recorded before a withdrawal has to have that withdrawal added back before it is
compared with the peak.

WHAT THIS TOOL DOES: reads the live ledger, decides the state, and records a row in
tradebot_sci.payouts for every win it evaluates, so the same closing fill can never be
paid twice. It places no orders, moves no money and needs no model. The day the money
actually leaves OANDA that is his act in the fxTrade portal, and `--withdrawn REF`
writes it on the rows' withdrawn_at column — the record of it, not the moving of it.

Usage:
    python3 tools/take_home.py            # what to take home, in words
    python3 tools/take_home.py --json     # machine readable
    python3 tools/take_home.py --due      # only the amount owed and not yet withdrawn
    python3 tools/take_home.py --withdrawn "fxTrade portal 2026-10-13"   # record that it left

Requires the OANDA key and the database credentials in the environment; run it through
the vault accessor, never with a secret on the command line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import live_trade_history as lth  # noqa: E402  - the ledger reader, already written and tested
import oanda_trade as ot  # noqa: E402  - the live tool holds the API, the rails and the DB path

# The mentor's tiers. Changing either one changes what he is paid, so both are quoted in
# the rule row (run_state.take_home) and in Documentation/RTFM/53_TARGET.md.
TAKE_LOW = 0.50
TAKE_HIGH = 0.75
VELOCITY_TIER_PCT = 2.5

# The peak lives in the database, not in a file, because every session of me has to see
# the same one. Plain decimal in run_state, one row.
PEAK_KEY = "take_home_high_water"

STATE_LOCKED = "LOCKED"
STATE_SHIELDED = "SHIELDED"
STATE_PAYDAY = "PAYDAY"
STATE_WAITING = "WAITING"   # flat, at or above the peak, and no new winner to pay

# The day the rule took effect. Wins that closed before it are the record the rule was
# written from, not payouts it owes: paying them now would be paying him twice for
# trades that were never his wage. Their balances still set the peak.
RULE_START = "2026-10-12"


def db_rows(sql: str) -> list[list[str]]:
    out = ot.db_query(sql)
    return [line.split("\t") for line in out.splitlines() if line.strip()]


def read_peak() -> float | None:
    rows = db_rows(f"SELECT v FROM run_state WHERE k = {ot.sql_quote(PEAK_KEY)};")
    if not rows:
        return None
    try:
        return float(rows[0][0])
    except ValueError:
        return None


def paid_fills() -> dict[str, str]:
    """Every closing fill already decided on, with the state it was decided in.

    The state matters as much as the fill: a PAYDAY has already re-based the peak, so
    reading its balance again on a later run would put the peak back up where the
    payout took it down from.
    """
    return {r[0]: r[1] for r in db_rows(
        "SELECT closing_fill, state FROM payouts WHERE closing_fill IS NOT NULL;")}


def withdrawals() -> list[tuple[str, float]]:
    """Money that has actually left OANDA: (the day it left, the amount).

    One row per payout, so a partial transfer is representable. Nothing is inferred:
    a row with no withdrawn_at is money still sitting in the account.
    """
    out = []
    for r in db_rows("SELECT withdrawn_at, take_usd FROM payouts "
                     "WHERE withdrawn_at IS NOT NULL AND take_usd IS NOT NULL;"):
        try:
            out.append((r[0], float(r[1])))
        except (ValueError, IndexError):
            continue
    return out


def as_was(balance: float, closed_at: str, taken_out: list[tuple[str, float]]) -> float:
    """The balance as it stood at closed_at, with later withdrawals added back.

    The ledger reconstructs balances by walking today's balance back through the fills'
    own P/L, and a withdrawal is not a fill: without this, every pre-withdrawal balance
    reads low by whatever has left since, and a desk that has paid him once would be
    measured as permanently below its own peak.
    """
    return balance + sum(amt for at, amt in taken_out if at > closed_at)


def write_peak(value: float) -> None:
    """Store the peak. It is written whenever it moves, in either direction.

    Downward is the whole point: policy 22 says the peak is re-based after each payout,
    and a peak that may only rise is not re-based at all.
    """
    ot.db_query(
        "INSERT INTO run_state (k, v) VALUES ("
        f"{ot.sql_quote(PEAK_KEY)}, {ot.sql_quote(f'{value:.4f}')}) "
        "ON DUPLICATE KEY UPDATE v = VALUES(v);")


def record(row: dict) -> None:
    row = dict(row)
    row["computed_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cols = ["computed_at", "state", "closing_fill", "closed_at", "instrument", "win_usd",
            "balance_before", "high_water", "velocity_pct", "take_pct", "take_usd",
            "kept_usd", "note"]
    vals = []
    for c in cols:
        v = row.get(c)
        if v is None:
            vals.append("NULL")
        elif isinstance(v, (int, float)):
            vals.append(f"{v:.4f}" if isinstance(v, float) else str(v))
        else:
            vals.append(ot.sql_quote(str(v)))
    ot.db_query("INSERT INTO payouts (" + ", ".join(cols) + ") VALUES (" + ", ".join(vals) + ") "
                "ON DUPLICATE KEY UPDATE state = VALUES(state), take_usd = VALUES(take_usd);")


def closing_fills() -> list[dict]:
    """Every closed desk trade, oldest first, with the balance it started from.

    The balance before each close is reconstructed backwards from the balance now using
    the ledger's own P/L, the same way tools/live_trade_history.py does it and for the
    same reason: the ledger holds fills, and a balance history is not one of them.
    """
    pairs = lth.pair_trades(lth.ledger())
    balance_now = float(ot.summary()["balance"])
    out = []
    bal = balance_now
    for entry, exit_ in ((p["entry"], p["exit"]) for p in reversed(pairs)):
        pnl = float(exit_["pl"])
        before = bal - pnl
        out.insert(0, dict(
            closed_at=exit_["time"][:19].replace("T", " "),
            key=exit_["time"],
            instrument=entry["instrument"].replace("_", ""),
            pnl=pnl,
            balance_before=before,
            balance_after=bal,
        ))
        bal = before
    return out


def decide(fills: list[dict], stored_peak: float | None, paid: dict[str, str],
           taken_out: list[tuple[str, float]], balance_now: float) -> tuple[float, list[dict]]:
    """The rule itself: pure arithmetic over the fills. No database, no broker, no clock.

    Returns the peak as it now stands and the rows to record. Evaluated oldest first,
    because the peak a trade is judged against is the one that stood before it closed:
    reading it after the win instead would make every win its own new high, which is the
    opposite of the rule.
    """
    if stored_peak is not None:
        peak = stored_peak
    else:
        before_rule = [as_was(f["balance_after"], f["closed_at"], taken_out)
                       for f in fills if f["closed_at"][:10] < RULE_START]
        in_scope = [f for f in fills if f["closed_at"][:10] >= RULE_START]
        peak = (max(before_rule) if before_rule
                else (as_was(in_scope[0]["balance_before"], in_scope[0]["closed_at"], taken_out)
                      if in_scope else balance_now))

    rows = []
    for f in fills:
        before = as_was(f["balance_before"], f["closed_at"], taken_out)
        after = as_was(f["balance_after"], f["closed_at"], taken_out)
        if paid.get(f["key"]) == STATE_PAYDAY:
            # Already paid. Its balance was the high water the payout was taken from and
            # a new peak was set below it, so letting it raise the peak now would cancel
            # that payout's re-basing on the next run.
            continue
        peak = max(peak, before)
        if f["pnl"] <= 0 or f["closed_at"][:10] < RULE_START:
            peak = max(peak, after)
            continue        # a loss, or before the rule: nothing paid, and the peak stands
        if f["key"] in paid:
            peak = max(peak, after)     # decided on an earlier run: shielded, or pre-rule
            continue
        velocity = f["pnl"] / before * 100.0
        if before < peak:
            rows.append(dict(state=STATE_SHIELDED, closing_fill=f["key"],
                             closed_at=f["closed_at"], instrument=f["instrument"],
                             win_usd=f["pnl"], balance_before=before, high_water=peak,
                             velocity_pct=velocity, take_pct=0.0, take_usd=0.0,
                             kept_usd=f["pnl"],
                             note=(f"The account was {peak - before:.2f} USD below its peak "
                                   f"{peak:.2f} before this win, so the win rebuilds the "
                                   f"drawdown and nothing is paid. Steven chose the shielded "
                                   f"version on 2026-10-12.")))
            peak = max(peak, after)
            continue
        pct = TAKE_HIGH if velocity >= VELOCITY_TIER_PCT else TAKE_LOW
        take = f["pnl"] * pct
        rows.append(dict(state=STATE_PAYDAY, closing_fill=f["key"],
                         closed_at=f["closed_at"], instrument=f["instrument"],
                         win_usd=f["pnl"], balance_before=before, high_water=peak,
                         velocity_pct=velocity, take_pct=pct * 100.0, take_usd=take,
                         kept_usd=f["pnl"] - take,
                         note=(f"Win of {f['pnl']:.4f} USD on {f['instrument']} closed at or "
                               f"above the peak {peak:.4f}; {pct:.0%} is taken home and "
                               f"{f['pnl'] - take:.4f} USD stays to compound. The account is "
                               f"re-based to {after - take:.4f} USD for the next payout.")))
        peak = after - take          # the mentor's active capital base, re-based
    return peak, rows


def resolve_state(open_trades: int, owed: float, balance_now: float, peak: float) -> str:
    """LOCKED beats owing beats shielded beats nothing to do."""
    if open_trades:
        return STATE_LOCKED
    if owed > 0:
        return STATE_PAYDAY
    if balance_now < peak:
        return STATE_SHIELDED
    return STATE_WAITING


def evaluate(record_rows: bool = True) -> dict:
    fills = closing_fills()
    balance_now = float(ot.summary()["balance"])
    open_trades = len(ot.open_trades())
    paid = paid_fills()
    taken_out = withdrawals()

    stored_peak = read_peak()
    peak, rows = decide(fills, stored_peak, paid, taken_out, balance_now)

    for row in rows:
        if record_rows:
            record(row)

    if stored_peak is None or abs(peak - stored_peak) > 0.0001:
        write_peak(peak)

    owed_rows = db_rows("SELECT COALESCE(SUM(take_usd), 0) FROM payouts "
                        "WHERE state = 'PAYDAY' AND withdrawn_at IS NULL;")
    owed = float(owed_rows[0][0]) if owed_rows else 0.0
    return dict(as_of=dt.datetime.now(dt.timezone.utc).isoformat(),
                state=resolve_state(open_trades, owed, balance_now, peak),
                balance=balance_now, peak=peak, open_trades=open_trades,
                owed_not_withdrawn=round(owed, 4), evaluated=rows,
                withdrawn=round(sum(a for _, a in taken_out), 4))


def mark_withdrawn(ref: str, at: str | None = None) -> tuple[int, float]:
    """Record that the owed money actually left OANDA. Returns (rows, amount).

    It moves nothing: the transfer is his, in the fxTrade portal, and this writes the day
    and his reference on the rows it paid out, which is what makes the desk's arithmetic
    treat the money as gone rather than as capital it can risk again. Every un-withdrawn
    PAYDAY row is marked, because one transfer settles the whole amount owed.
    """
    when = at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = db_rows("SELECT COALESCE(SUM(take_usd), 0), COUNT(*) FROM payouts "
                   "WHERE state = 'PAYDAY' AND withdrawn_at IS NULL;")
    total = float(rows[0][0]) if rows else 0.0
    count = int(rows[0][1]) if rows else 0
    if count:
        ot.db_query("UPDATE payouts SET withdrawn_at = " + ot.sql_quote(when) +
                    ", withdrawal_ref = " + ot.sql_quote(ref) +
                    " WHERE state = 'PAYDAY' AND withdrawn_at IS NULL;")
    return count, total


def words(d: dict) -> str:
    lines = [f"TAKE HOME  {d['as_of'][:16].replace('T', ' ')}Z",
             f"state {d['state']}  balance {d['balance']:.2f}  peak {d['peak']:.2f}"]
    if d["state"] == STATE_LOCKED:
        lines.append("A position is open. The desk pulls no capital while a trade is live.")
    if d["evaluated"]:
        for r in d["evaluated"]:
            if r["state"] == STATE_PAYDAY:
                lines.append(f"  PAYDAY  {r['closed_at']} {r['instrument']} win {r['win_usd']:+.4f}: "
                             f"take {r['take_usd']:.2f} ({r['take_pct']:.0f}%), keep {r['kept_usd']:.2f}")
            else:
                lines.append(f"  SHIELDED  {r['closed_at']} {r['instrument']} win {r['win_usd']:+.4f}: "
                             f"rebuilding to the peak {r['high_water']:.2f}")
    else:
        lines.append("  no new winner to evaluate")
    lines.append(f"  owed and not yet withdrawn: {d['owed_not_withdrawn']:.2f} USD")
    if d.get("withdrawn"):
        lines.append(f"  already taken home and out of the account: {d['withdrawn']:.2f} USD")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine readable output")
    ap.add_argument("--due", action="store_true", help="only the amount owed and not withdrawn")
    ap.add_argument("--withdrawn", metavar="REF",
                    help="record that the owed amount has left OANDA, with his reference")
    ap.add_argument("--at", metavar="YYYY-MM-DD HH:MM:SS",
                    help="when it left (UTC, default now); only used with --withdrawn")
    a = ap.parse_args()
    if a.withdrawn:
        count, total = mark_withdrawn(a.withdrawn, a.at)
        if count:
            print(f"recorded: {total:.2f} USD withdrawn across {count} payout row(s), "
                  f"ref {a.withdrawn}. It is not a gain: that money has left the account.")
        else:
            print("nothing owed and un-withdrawn: no payout row to mark.")
        return
    d = evaluate()
    if a.due:
        print(f"{d['owed_not_withdrawn']:.2f}")
    elif a.json:
        print(json.dumps(d, indent=2))
    else:
        print(words(d))


if __name__ == "__main__":
    main()
