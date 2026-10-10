#!/usr/bin/env python3
"""End-of-day PnL push to Steven's phone, sent through the secretary's own channel.

WHY THIS EXISTS. Steven asked for it on 2026-10-07, in the Office room: "Send push
notifications on PnL wins and losses at the end of your trading day so I can keep
track. Send through Vera (she handles push notifications)." He is tracking a small
account back toward the 7,000 USD he once funded, and the day's result should reach
him without him having to ask for it.

WHAT IT SENDS. One push per trading day, after the desk's last window, carrying the
day's result, the parts it is made of (trades closed, overnight holding cost, and any
open position priced in), the account in cash and with its open positions priced in,
the whole record of the live desk, and how far the account is from the 7,000 target.

THE DAY FIGURE. It is the account's current value against its value at 00:00Z, so it
agrees with the daily loss cap and with tools/oanda_trade.py state. It is not the money
banked: a day that closed nothing but is holding a position shows the position's move,
labelled as not yet banked. Every part is printed, and a line appears if the parts do
not add up to the figure, so a stale anchor is visible rather than silent.

HOW IT SENDS IT. Through the secretary's notifier, which is the only push path on
this host that can both send and verify a receipt (her Pushover application key and
his device are registered there):

    /home/qchan/Scripts/Secretary/pushover_notify.py --message "..." --title "..."

so the channel, the credentials and the send log stay hers. The same numbers go to
her mailbox on the agent bus, so she holds the record and not only the message.

WHAT IT WILL NOT DO. It places no order, moves no stop and writes nothing to the
account. It reads the OANDA ledger and the day anchor, builds one message and
sends it.

EXIT CODES. 0 whether or not a push went out, because a day with no trade is not a
failure (incident 16 was a timer marked failed on a quiet run). 1 only when the
message could not be built, so a real fault is still visible to systemd.

IT PUSHES ONCE PER DAY. A state file records what was sent, so a timer that fires
twice, or a hand run after the timer, does not push twice.

Usage:
  tools/daily_pnl_push.py --dry-run     # print the message, send nothing
  tools/daily_pnl_push.py               # send if today is not already sent
  tools/daily_pnl_push.py --force       # send even if today was already sent
  tools/daily_pnl_push.py --test        # send labelled "TEST - ", leave the day unmarked
  tools/daily_pnl_push.py --date 2026-10-06   # rebuild and print another day
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import oanda_trade as ot  # noqa: E402  - the credential and ledger code stays in one place

STATE = REPO / "logs" / ".daily_pnl_pushed.json"
LOG = REPO / "logs" / "daily_pnl_push.log"
SECRET_NOTIFIER = pathlib.Path.home() / "Scripts" / "Secretary" / "pushover_notify.py"
AGENTBUS = pathlib.Path.home() / "Scripts" / "Agent Core" / "agentbus.py"
DESK_START = "2026-09-17"          # the first live fill of this desk
GOAL_USD = 7000.0                  # what Steven funded once and is rebuilding toward


def say(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {line}\n")


def ledger(since_day: str) -> list[dict]:
    """Every ORDER_FILL and DAILY_FINANCING from the broker, bounded to the recent window.

    The window is the last 400 transactions, which reaches back past the desk's first
    live fill on 2026-09-17 with room to spare; if it ever stops reaching, the rows
    that are missing are missing from a report and not from the account.
    """
    last = int(ot.summary().get("lastTransactionID", 0) or 0)
    if last <= 1:
        return []
    tx = ot.api("GET", f"/v3/accounts/{{acct}}/transactions/sinceid?id={max(1, last - 400)}")
    rows = []
    for t in tx.get("transactions", []):
        at = ot.parse_iso(t.get("time"))
        if at is None or at.date().isoformat() < since_day:
            continue
        rows.append({"type": t.get("type"), "at": at, "time": t.get("time"),
                     "instrument": t.get("instrument"), "units": t.get("units"),
                     "price": t.get("price"), "pl": float(t.get("pl") or 0.0),
                     "financing": float(t.get("financing") or 0.0),
                     "reason": t.get("reason")})
    return rows


def compose(day: dt.date, dry_note: str = "") -> tuple[str, str, dict]:
    """The message. Everything in it is read from the broker or from our own state."""
    rows = ledger(min(day.isoformat(), DESK_START))
    # An entry fill carries no pl; a closing fill does, whatever its reason. The pl test
    # is used rather than the reason string, because a close by hand is a MARKET_ORDER
    # exactly like an entry is.
    today = [r for r in rows if r["at"].date() == day and r["type"] == "ORDER_FILL"
             and r["pl"] != 0.0]
    opened_today = [r for r in rows if r["at"].date() == day and r["type"] == "ORDER_FILL"
                    and r["pl"] == 0.0]
    financing = sum(r["financing"] for r in rows if r["at"].date() == day)
    closed_pl = sum(r["pl"] for r in today)

    desk = [r for r in rows if r["type"] == "ORDER_FILL" and r["pl"] != 0.0]
    desk_net = sum(r["pl"] for r in desk)
    wins = [r for r in desk if r["pl"] > 0]
    losses = [r for r in desk if r["pl"] < 0]

    state = ot.summary()
    balance = float(state["balance"])
    nav = float(state["NAV"])
    open_pl = float(state.get("unrealizedPL") or 0.0)
    open_trades = ot.open_trades()
    now_day = dt.datetime.now(dt.timezone.utc).date()
    if day == now_day:
        anchor = ot.day_anchor()
        rebuilt = False
        # The day figure is what the account is worth now against what it was worth at
        # 00:00Z, which is the measurement the daily loss cap uses and the one
        # tools/oanda_trade.py state reports. Until 2026-10-08 this counted only closed
        # fills and financing, so it reported "+0.50 USD (+0.2%)" on a day whose one open
        # position was 3.18 USD down: the push and the state read contradicted each other
        # about the same day, and the phone carried the flattering one.
        day_pl = nav - anchor
    else:
        # A past day, rebuilt for the record. Its start-of-day NAV is today's NAV less
        # everything realized since that day began, which is exact arithmetic on the
        # ledger while no deposit or withdrawal happened in between (none has on this
        # account). The account, desk and goal lines stay as of now and say so. An open
        # position's mark belongs to today rather than to that day, so it is left out.
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
        anchor = nav - sum(r["pl"] + r["financing"] for r in rows if r["at"] >= start)
        rebuilt = True
        open_pl = 0.0
        day_pl = closed_pl + financing
    pct = (100 * day_pl / anchor) if anchor else 0.0
    # The parts have to add up to the day figure. When they do not, the anchor and the
    # ledger are telling two different stories; the message says so rather than printing
    # whichever one it happened to be holding.
    gap = 0.0 if rebuilt else round(day_pl - (closed_pl + financing + open_pl), 2) + 0.0
    explained = closed_pl + financing + open_pl

    sign = "+" if day_pl >= 0 else ""
    # The title has to be readable at a glance on a phone lock screen, which is why the
    # direction is in it and not only in the body: the secretary, whose channel this is,
    # asked for that on 2026-10-07. A figure that comes from a position still open says
    # so, so the number is never mistaken for money already banked.
    if today or financing or open_trades:
        title = f"Tradebot day: {sign}{day_pl:.2f} USD ({sign}{pct:.1f}%)"
        if open_trades:
            title += f", {len(open_trades)} open"
    else:
        title = f"Tradebot day: no trades ({day.strftime('%a %m-%d')})"

    lines = [f"{day.strftime('%a %Y-%m-%d')}, end of the trading day (UTC).", ""]
    lines.append(f"DAY {sign}{day_pl:.2f} USD ({sign}{pct:.1f}% from {anchor:.2f} at 00:00Z)")
    if today:
        for r in sorted(today, key=lambda x: x["at"]):
            units = abs(int(float(r["units"] or 0)))
            # These are CLOSING fills, so the position was the other side of the fill:
            # buying 2987 back closed a short of 2987.
            side = "short" if float(r["units"] or 0) > 0 else "long"
            lines.append(f"  {'win ' if r['pl'] > 0 else 'loss'} {r['instrument']} {side} "
                         f"{units}: {r['pl']:+.2f} ({str(r['reason']).replace('_', ' ').lower()})")
    else:
        lines.append("  nothing closed today")
    if financing:
        lines.append(f"  overnight holding cost: {financing:+.2f}")
    if open_trades:
        lines.append(f"  open position{'s' if len(open_trades) > 1 else ''} priced in: "
                     f"{open_pl:+.2f}, not banked until closed")
    elif not today:
        lines.append(f"  {len(opened_today)} entr"
                     f"{'y' if len(opened_today) == 1 else 'ies'} taken, nothing open")
    if gap:
        lines.append(f"  WARNING the parts above add up to {explained:+.2f}, which is not the "
                     f"day figure {day_pl:+.2f}: the day anchor and the ledger disagree")
    lines.append("")
    if open_trades:
        lines.append(f"ACCOUNT {balance:.2f} USD cash, {nav:.2f} USD with the open "
                     f"position{'s' if len(open_trades) > 1 else ''} priced in, "
                     f"{len(open_trades)} open.")
    else:
        lines.append(f"ACCOUNT {balance:.2f} USD, nothing open.")
    for t in open_trades:
        try:
            row = ot.r_progress(t, ot.quote_one(str(t.get("instrument"))))
        except Exception:                                      # noqa: BLE001
            row = {}
        r = row.get("r_multiple")
        usd = float(t.get("unrealizedPL") or 0.0)
        direction = "long" if float(t.get("currentUnits") or 0) > 0 else "short"
        units = abs(int(float(t.get("currentUnits") or 0)))
        lines.append(f"  {t.get('instrument')} {direction} {units} at "
                     f"{('%+.2fR' % r) if r is not None else 'an unmeasured R'}, "
                     f"{usd:+.2f} USD")
    lines.append("")
    lines.append(f"DESK since {DESK_START}: net {desk_net:+.2f} USD over {len(desk)} trades "
                 f"({len(wins)} wins / {len(losses)} losses).")
    lines.append(f"GOAL {balance:.2f} of {GOAL_USD:,.0f} "
                 f"({100 * balance / GOAL_USD:.1f} percent).")
    lines.append("")
    lines.append(f"Source: OANDA ledger read {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%MZ}.")
    if rebuilt:
        lines.append("Rebuilt for a past day: the day figure and the 00:00Z anchor are that day's, "
                     "the account, desk and goal lines are as of now.")
    if dry_note:
        lines.append(dry_note)
    meta = {"day_pl": round(day_pl, 4), "pct": round(pct, 2), "balance": balance, "nav": nav,
            "closed_pl": round(closed_pl, 4), "financing": round(financing, 4),
            "open_pl": round(open_pl, 4), "components_gap": gap,
            "closed_today": len(today), "open": len(open_trades), "desk_net": round(desk_net, 4),
            "desk_trades": len(desk), "wins": len(wins), "losses": len(losses)}
    return title, "\n".join(lines), meta


def push(title: str, body: str, dry_run: bool = False) -> tuple[bool, str]:
    """Hand the message to the secretary's notifier. Her channel, her credentials."""
    if not SECRET_NOTIFIER.exists():
        return False, f"notifier missing at {SECRET_NOTIFIER}"
    cmd = [sys.executable, str(SECRET_NOTIFIER), "--message", body, "--title", title]
    if dry_run:
        cmd.append("--dry-run")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except Exception as exc:                                   # noqa: BLE001
        return False, f"notifier failed to run: {exc}"
    out = (r.stdout or "").strip()
    return r.returncode == 0 and out.startswith("sent"), out[:300] or (r.stderr or "")[:300]


def tell_secretary(title: str, body: str) -> str:
    """Put the same numbers in her mailbox. Best effort: the push matters more."""
    if not AGENTBUS.exists():
        return "agentbus missing"
    env = {**os.environ, "AGENTBUS_ID": "tradebot_sci"}
    try:
        r = subprocess.run([sys.executable, str(AGENTBUS), "send", "secretary",
                            f"{title}\n\n{body}"],
                           capture_output=True, text=True, timeout=60, env=env)
        return (r.stdout or r.stderr or "").strip()[:200]
    except Exception as exc:                                   # noqa: BLE001
        return f"agentbus failed: {exc}"


def already_sent(day: str) -> dict | None:
    try:
        st = json.loads(STATE.read_text())
        return st if st.get("date") == day else None
    except Exception:                                          # noqa: BLE001
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="End-of-day PnL push through the secretary")
    p.add_argument("--dry-run", action="store_true", help="print, send nothing")
    p.add_argument("--force", action="store_true", help="send even if today was already sent")
    p.add_argument("--test", action="store_true",
                   help="send a push labelled TEST - and do not mark the day as sent")
    p.add_argument("--date", help="report another UTC day (YYYY-MM-DD); never sends")
    p.add_argument("--no-bus", action="store_true", help="do not mail the secretary")
    a = p.parse_args()

    day = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(dt.timezone.utc).date()
    try:
        title, body, meta = compose(day, dry_note="(dry run: this is the exact message)"
                                    if (a.dry_run or a.date) else "")
    except Exception as exc:                                   # noqa: BLE001
        say(f"ABORT could not build the message: {exc}")
        print(f"could not build the message: {exc}", file=sys.stderr)
        return 1

    # The secretary's channel, and the secretary asked on 2026-10-07 that a test push
    # be readable as one at a glance: the prefix is added here rather than left to the
    # operator, so no future run can send an unlabelled test to his phone.
    if a.test:
        title = f"TEST - {title}"

    print(f"--- {title} ---\n{body}\n--- {json.dumps(meta)}")

    if a.dry_run or a.date:
        say(f"dry_run day={day} day_pl={meta['day_pl']}")
        return 0

    if not a.test and not meta["closed_today"] and not meta["open"] and meta["day_pl"] == 0:
        # No noise on an empty day: silence means nothing happened, not that the push broke.
        say(f"skipped day={day} no trades and nothing open")
        print("nothing to report - no push sent")
        return 0

    seen = already_sent(day.isoformat())
    if seen and not a.force and not a.test:
        say(f"already sent day={day} at {seen.get('at')}")
        print(f"already pushed for {day}: {seen.get('title')}")
        return 0

    ok, detail = push(title, body)
    say(f"{'SENT' if ok else 'FAILED'} day={day} title={title!r} {detail}")
    if ok:
        # A test proves the path; it must not consume the day, or tonight's real push
        # would be suppressed by the once-a-day guard.
        if not a.test:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"date": day.isoformat(), "title": title,
                                         "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                         "meta": meta}, indent=1))
        if not a.no_bus:
            say(f"bus {tell_secretary(title, body)}")
    elif not a.no_bus:
        # A failed push is still a message Steven is owed, and the phone is not the only
        # channel: hand it to the secretary and say plainly that the automatic path did
        # not work, so the notification arrives by a human rather than by a retry at
        # tomorrow's timer. Nothing is written to the state file, so a later run retries.
        say(f"bus {tell_secretary('[PUSH FAILED, please send by hand] ' + title, body)}")
    print(("pushed" if ok else "push failed"), "-", detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
