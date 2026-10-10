#!/usr/bin/env python3
"""OANDA order and state tool for the live trading agent.

This is the ONLY way the agent touches the live account. It exists so that the
operational rails live in code rather than in a prompt: whatever the agent
decides, this tool refuses orders that breach the limits below, refuses to trade
when the market is closed or the spread is abnormal, and refuses to trade at all
once the daily loss cap is hit.

The agent decides WHAT and WHETHER. This decides what is SAFE.

Usage:
  oanda_trade.py state
  oanda_trade.py quote EUR_USD [GBP_USD ...]
  oanda_trade.py candles EUR_USD [M5|M15|H1|H4|D] [count]
  oanda_trade.py size EUR_USD --stop-pips 20 [--risk-pct 6.0]
  oanda_trade.py buy  EUR_USD 1200 --stop 1.0800 [--target 1.0900] --horizon-hours 24 [--reason "..."]
  oanda_trade.py sell EUR_USD 1200 --stop 1.0900 [--target 1.0800] --horizon-hours 24 [--reason "..."]
      # A second position on an instrument that is already open is ADD TO A WINNER, not a
      # second idea: allowed only when the open trade is at +1R or better, one add per
      # position, and the tool moves that trade's stop to its entry BEFORE the add is sent.
  oanda_trade.py modify EUR_USD [--stop 1.0900] [--target 1.0800] [--trail-pips 20] [--trade-id ID]
  oanda_trade.py horizon                 # open trades against their written horizon
  oanda_trade.py time-stop [--enforce]   # close trades whose written horizon has expired
  oanda_trade.py close EUR_USD
  oanda_trade.py close-all
  oanda_trade.py transactions [count]
  oanda_trade.py excursions           # sample open trades' progress into logs/excursions.jsonl
  oanda_trade.py excursions --report  # per-trade MFE / MAE in R, from those samples

Add --dry-run to any order command to validate without sending it.
Every invocation is appended to logs/agent_trades.jsonl.

THREE THINGS THIS TOOL NOW ENFORCES THAT IT USED TO LEAVE TO MEMORY:

1. THE WRITTEN HORIZON. An entry must state how long the thesis is good for, and
   that statement is carried on the order itself as an OANDA client-extension
   comment, so it survives outside this repo. `time-stop` closes any trade whose
   horizon has passed, and `_preflight` refuses new entries while an overdue
   trade is still open. The rule exists because of live trade 3: opened
   2026-09-23 18:01Z with "expect 1.1340 within 24h" written in the reason field,
   never closed by anything, and shut 43.0 hours later by hand for -0.73 USD
   (tradebot_sci facts id 135).
2. THE STOP IS NOT WRITE-ONCE. `modify` moves a stop or target, or attaches a
   broker-side trailing stop, with the same risk cap applied to the new stop, so
   a winner can be protected without closing it and re-paying the spread.
3. EVERY TRADE CAN BE MEASURED IN R. Every entry writes the stop it was opened with
   onto the trade as `entry_stop=`, which fixes R for the life of the position, and
   `state` reports how far each position has run in R at the price it would actually
   be closed at. R is deliberately not recomputed from the live stop: a tightened
   stop would drag the 1R level down and the same move would score twice. This is
   measurement only. There is no partial exit: a position leaves whole, at its
   target, its stop, its trail or its horizon (policy 16, 2026-10-01).
4. SIZE IS ADDED TO A WINNER OR NOT AT ALL. A new entry in an instrument that already
   has an open position is an ADD TO A WINNER, and it is allowed only when that
   position has reached +1R measured at the price it would actually be closed at.
   The tool then moves the open trade's stop to its entry before sending the add, so
   the pair risks one risk unit and not two, and one add per position is the limit.
   Built 2026-10-07 at Steven's instruction that the desk stop trading as if the
   capital were large: the audit behind it found the seven live entries were 7 of 7
   sells and 6 of 7 EUR_USD, every one the same USD-strength continuation, which is
   the same bet taken repeatedly rather than a second idea.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zoneinfo

REPO = pathlib.Path(__file__).resolve().parents[1]
CONFIG = pathlib.Path.home() / ".config" / "tradebot-sci-gui" / "local" / "config.json"
LOG = REPO / "logs" / "agent_trades.jsonl"
EXCURSIONS = REPO / "logs" / "excursions.jsonl"
HALT_FILE = REPO / "logs" / "AGENT_TRADING_HALT"
DB_ENV_FILE = pathlib.Path.home() / ".config" / "secrets" / ".env.secrets"

# ── Operational rails. The agent cannot override these from the prompt. ──
# THE SIZE CEILING IS 6% OF NAV AND IT HAS BEEN RAISED TWICE. Running at 1% was the
# old desk's habit; 2% became the ceiling on 2026-09-17, 4% on 2026-10-01 when
# Steven asked for a figure that was more readable, and 6% on 2026-10-07 when he
# said the desk was still trading too small for a 250 USD account whose target is
# the 7,000 USD he once funded it with. On low capital the way back up is size and
# compounding, and a ceiling that keeps every trade at pocket change is a decision
# to stay small rather than a cautious one.
# TWO RAILS MOVED WITH IT. The daily halt went 6% to 12%, because at a 6% risk unit
# the old halt was a single stopped trade and would have ended the day on the first
# loss. Max open positions went 2 to 3, because a desk that trades one instrument
# was using two slots to take the same bet twice.
# The cost side does not move with size: the toll measured on every live fill is
# 1.5 to 1.6 pips, about 5% of a 30-pip risk unit, so it scales with the trade and
# not against it.
MAX_RISK_PCT_PER_TRADE = float(os.getenv("AGENT_MAX_RISK_PCT", "6.0"))
MAX_OPEN_POSITIONS = int(os.getenv("AGENT_MAX_OPEN", "3"))
MAX_TRADES_PER_DAY = int(os.getenv("AGENT_MAX_TRADES_DAY", "4"))
MAX_DAILY_LOSS_PCT = float(os.getenv("AGENT_MAX_DAILY_LOSS_PCT", "12.0"))
MAX_SPREAD_PIPS = float(os.getenv("AGENT_MAX_SPREAD_PIPS", "3.0"))
MIN_UNITS = 1
MIN_STOP_PIPS = float(os.getenv("AGENT_MIN_STOP_PIPS", "1.0"))

# Every entry states how long its thesis is good for, and the statement travels
# on the order itself so it outlives the journal, this repo and the session that
# wrote it. Set AGENT_HORIZON_REQUIRED=0 to allow entries with no horizon, which
# also means those trades can never be closed by the time stop.
HORIZON_REQUIRED = os.getenv("AGENT_HORIZON_REQUIRED", "1") not in ("0", "false", "no")
CLIENT_TAG = "tradebot-sci"
HORIZON_PREFIX = "horizon="

# The trade's own rules travel on the trade, in the same client-extension comment
# as the horizon. entry_stop is the stop that was written when the position was
# opened: it defines R for the life of the trade and does not move when the live
# stop does. It is read for measurement; no exit is driven by it.
ENTRY_STOP_PREFIX = "entry_stop="

PIP = {"JPY": 0.01}
DEFAULT_PIP = 0.0001


def pip_size(instrument: str) -> float:
    return PIP.get(instrument.split("_")[-1], DEFAULT_PIP)


def log(record: dict) -> None:
    record["at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def cfg() -> tuple[str, str, str, str]:
    c = json.loads(CONFIG.read_text())["brokers"]["oanda"]
    env = c.get("environment", "live")
    host = "https://api-fxtrade.oanda.com" if env == "live" else "https://api-fxpractice.oanda.com"
    key = os.environ.get("OANDA_API_KEY", "")
    if not key:
        sys.exit("OANDA_API_KEY not set. Source ~/.config/secrets/.env.secrets first.")
    return host, key, c["account_id"], env


def api(method: str, path: str, body: dict | None = None):
    host, key, acct, _ = cfg()
    url = host + path.replace("{acct}", acct)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        sys.exit(f"OANDA {e.code} on {method} {path}: {detail}")


def summary() -> dict:
    return api("GET", "/v3/accounts/{acct}/summary")["account"]


def nav() -> float:
    return float(summary().get("NAV", 0))


def realized_pl_today(now: dt.datetime | None = None) -> float:
    """Everything the account has actually banked since 00:00Z today, from the ledger.

    Read from the broker rather than from our own journal, because the whole point of
    the anchor is to be right about money that moved before anything of ours ran. The
    sweep is bounded to the last 200 transactions, which is far more than a day's work
    on this account; if it ever is not, the anchor is wrong in the safe direction,
    because an unread fill shows up as profit that the loss cap will then count as
    budget spent.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last = int(summary().get("lastTransactionID", 0) or 0)
    if last <= 1:
        return 0.0
    tx = api("GET", f"/v3/accounts/{{acct}}/transactions/sinceid?id={max(1, last - 200)}")
    total = 0.0
    for t in tx.get("transactions", []):
        at = parse_iso(t.get("time"))
        if at is not None and at >= start:
            total += float(t.get("pl") or 0.0)
    return total


def _db_secret(name: str) -> str:
    """Read one TRADEBOT_DB_* value, preferring the environment.

    The env file is not valid shell (it carries a bare word and an unquoted
    address), so it is parsed key by key rather than sourced. Nothing here is
    ever printed: a secret echoed for debugging is a secret in the transcript.
    """
    val = os.environ.get(name, "")
    if val:
        return val
    try:
        with DB_ENV_FILE.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def db_query(sql: str) -> str:
    """Run one SQL statement through the mysql CLI and return its stdout.

    There is no Python MySQL driver on this host, so this is the house pattern.
    The statement goes on stdin, never in argv, so it cannot be read out of the
    process list; the password rides in MYSQL_PWD, never on the command line,
    so it cannot be read out of the journal. -N -B gives tab-separated rows with
    a literal NULL, which is what the callers parse.
    """
    pwd = _db_secret("TRADEBOT_DB_PASSWORD")
    if not pwd:
        raise RuntimeError("TRADEBOT_DB_PASSWORD not set and not readable from "
                           f"{DB_ENV_FILE}")
    env = dict(os.environ)
    env["MYSQL_PWD"] = pwd
    cmd = ["mysql",
           "-h", _db_secret("TRADEBOT_DB_HOST"),
           "-u", _db_secret("TRADEBOT_DB_USER"),
           _db_secret("TRADEBOT_DB_SCHEMA"),
           "-N", "-B"]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True,
                          env=env, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip()[:300] or
                           f"mysql exited {proc.returncode}")
    return proc.stdout


def sql_quote(text) -> str:
    """MySQL string literal. Backslash first, or the quote escape eats itself."""
    return "'" + str(text).replace("\\", "\\\\").replace("'", "''") + "'"


def _sql_num(value) -> str:
    return "NULL" if value is None else repr(float(value))


def anchor_load(day: str) -> dict | None:
    """The stored anchor for one UTC day, or None when there is no row yet."""
    out = db_query(
        "SELECT nav, nav_at_first_read, realized_before_first_read, "
        "ledger_corrected, ledger_read_failed FROM day_anchor "
        f"WHERE day = {sql_quote(day)};")
    rows = [r for r in out.splitlines() if r.strip()]
    if not rows:
        return None
    fields = rows[0].split("\t")
    if len(fields) < 5:
        return None
    nums = [None if f == "NULL" else float(f) for f in fields[:3]]
    return {
        "nav": nums[0], "nav_at_first_read": nums[1],
        "realized_before_first_read": nums[2],
        "ledger_corrected": fields[3] not in ("0", "NULL"),
        "ledger_read_failed": fields[4] not in ("0", "NULL"),
    }


def anchor_store(day: str, row: dict) -> None:
    """Write the day's anchor row. The first write for a day is the one that counts."""
    db_query(
        "INSERT INTO day_anchor "
        "(day, nav, nav_at_first_read, realized_before_first_read, "
        "ledger_corrected, ledger_read_failed) VALUES ("
        f"{sql_quote(day)}, {_sql_num(row['nav'])}, {_sql_num(row['nav_at_first_read'])}, "
        f"{_sql_num(row['realized_before_first_read'])}, "
        f"{1 if row['ledger_corrected'] else 0}, "
        f"{1 if row['ledger_read_failed'] else 0}) "
        "ON DUPLICATE KEY UPDATE nav=VALUES(nav), "
        "nav_at_first_read=VALUES(nav_at_first_read), "
        "realized_before_first_read=VALUES(realized_before_first_read), "
        "ledger_corrected=VALUES(ledger_corrected), "
        "ledger_read_failed=VALUES(ledger_read_failed);")


def day_anchor() -> float:
    """NAV at the START of the current UTC day, for the daily loss cap.

    It used to be the NAV at the first run of the day, which is a different number and
    a dangerous one: anything realized before that first run was absorbed into the
    baseline. Measured twice. On 2026-10-07 the +18.94 win closed at 07:52Z and the
    first run was 13:03Z, so the day reported 0.00 profit; on 2026-10-06 a -9.40 stop
    closed at 07:53Z and that day reported -0.45, a -3.9% day wearing a rounding error
    as a disguise. The second case is the one that matters, because the same anchor
    sets the 6% daily loss halt, so a loss that lands before the first run of the day
    was silently granting itself a fresh budget. See incident 15.

    So the day's realized result is read back off the ledger and subtracted before the
    anchor is stored. The row lives in tradebot_sci.day_anchor, one per UTC day, because
    a hand-edited JSON file is the thing this schema exists to replace. A row without
    the ledger_corrected marker is corrected on sight rather than trusted: it predates
    the fix and cannot be assumed to be a day-start figure.
    """
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    try:
        row = anchor_load(today)
    except Exception:                                 # noqa: BLE001 - a state read must not fail here
        row = None
    if row and row.get("ledger_corrected") and row.get("nav") is not None:
        return float(row["nav"])
    at_first_read = nav()
    degraded = False
    try:
        realized = realized_pl_today()
    except Exception:                                 # noqa: BLE001 - a state read must not fail here
        # A dead ledger read falls back to the old behaviour and says so in the row,
        # because silently pretending the day started at the current NAV is the fault
        # this function was fixed for.
        realized, degraded = 0.0, True
    start = at_first_read - realized
    try:
        anchor_store(today, {
            "nav": start, "nav_at_first_read": at_first_read,
            "realized_before_first_read": round(realized, 2), "ledger_corrected": True,
            "ledger_read_failed": degraded,
        })
    except Exception as exc:                          # noqa: BLE001 - the rail must still return
        print(f"WARN could not store the day anchor: {exc}", file=sys.stderr)
    return start


def market_open(now: dt.datetime | None = None) -> tuple[bool, str]:
    """Forex: opens Sunday 17:00 ET, closes Friday 17:00 ET."""
    now = now or dt.datetime.now(dt.timezone.utc)
    et = now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    wd, h = et.weekday(), et.hour
    if wd == 4 and h >= 17:
        return False, "Friday after 17:00 ET - market closed for the week"
    if wd == 5:
        return False, "Saturday - market closed"
    if wd == 6 and h < 17:
        return False, "Sunday before 17:00 ET - market not yet open"
    return True, "open"


def friday_manage_only(now: dt.datetime | None = None) -> tuple[bool, str]:
    """Friday is for managing what is open, not for opening anything new.

    The reason a NEW entry has to carry is the reason the hour-band study gave, and
    that study pooled all weekdays: it excludes the ~2.5-day weekend gap a stop
    cannot cover (fact 126). So on Friday the justification does not hold for any
    window, and the desk's own two hand closes were Friday trims taken against
    exactly that gap risk. The 20:00Z Friday window stays enabled for this and
    nothing else: it is the last hour before the week shuts at 21:00Z, and
    disabling it would remove the only scheduled pre-weekend exit.

    The weekday is read in New York, because that is the frame the trading week is
    defined in. It opens Sunday 17:00 ET and closes Friday 17:00 ET, and the two
    frames disagree about the small hours of Saturday in UTC.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    et = now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    if et.weekday() == 4:
        return True, "Friday in New York - manage what is open, open nothing new"
    return False, "not Friday"


def open_positions() -> list[dict]:
    return api("GET", "/v3/accounts/{acct}/openPositions").get("positions", [])


def open_trades() -> list[dict]:
    return api("GET", "/v3/accounts/{acct}/openTrades").get("trades", [])


# ── The written horizon ─────────────────────────────────────────────────
#
# A horizon is a statement of how long the reason for a trade stays valid. It is
# put on the order as a client-extension comment, which OANDA echoes back on
# every read of that trade, so the answer to "when does this expire" does not
# depend on a journal line staying in step with the account.

_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$")


def parse_iso(raw: object) -> dt.datetime | None:
    """Parse an OANDA timestamp. Nanosecond precision is truncated, not rejected."""
    m = _ISO.match(str(raw or "").strip())
    if not m:
        return None
    date, clock, frac, tz = m.group(1), m.group(2), (m.group(3) or "")[:6].ljust(6, "0"), m.group(4) or "Z"
    if tz not in ("Z",) and len(tz) == 5 and ":" not in tz:
        tz = tz[:3] + ":" + tz[3:]
    try:
        return dt.datetime.fromisoformat(f"{date}T{clock}.{frac}{tz}")
    except ValueError:
        return None


def _token(comment: object, prefix: str) -> str | None:
    """The value of one `key=value` token in a client-extension comment."""
    for tok in str(comment or "").split():
        if tok.startswith(prefix):
            return tok[len(prefix):]
    return None


def parse_horizon(comment: object) -> dt.datetime | None:
    """Read the horizon back out of a client-extension comment.

    Format: 'horizon=2026-09-24T18:01:55Z'. A comment that does not carry one
    returns None, and a trade with no readable horizon is NEVER closed by the
    time stop: a missing horizon is a missing instruction, not an expired one.
    Inventing a deadline the session never wrote would be the same fault as
    ignoring the one it did.
    """
    return parse_iso(_token(comment, HORIZON_PREFIX))


def parse_entry_stop(comment: object) -> float | None:
    """The stop written when the trade was opened, which is what R is measured from.

    Missing or unreadable returns None, and no level is then invented: a trade with
    no recorded entry stop simply has no R to report against.
    """
    raw = _token(comment, ENTRY_STOP_PREFIX)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _fmt_horizon(when: dt.datetime) -> str:
    return HORIZON_PREFIX + when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_entry_stop(instrument: str, value: float) -> str:
    return ENTRY_STOP_PREFIX + _fmt_price(instrument, value)


def update_comment(comment: object, instrument: str, horizon_at: dt.datetime | None = None,
                   entry_stop: float | None = None) -> str:
    """Rewrite the known rule tokens, keeping every token that is not one of ours.

    Rebuilding from parsed values alone would quietly delete anything a human or a
    later version wrote into that comment, so unrecognised tokens are carried over —
    including a `partial=` marker written by the version that banked the first R,
    which is left in place as history rather than silently erased.
    """
    keep = [t for t in str(comment or "").split()
            if not t.startswith((HORIZON_PREFIX, ENTRY_STOP_PREFIX))]
    parts: list[str] = []
    if horizon_at is not None:
        parts.append(_fmt_horizon(horizon_at))
    if entry_stop is not None:
        parts.append(_fmt_entry_stop(instrument, entry_stop))
    parts.extend(keep)
    return " ".join(parts)


def _fmt_price(instrument: str, value: float) -> str:
    """OANDA rejects excess precision, so prices go out at the pair's own scale."""
    return f"{value:.3f}" if pip_size(instrument) == 0.01 else f"{value:.5f}"


def horizon_row(trade: dict, now: dt.datetime | None = None) -> dict:
    """One open trade, the rules written on it, and whether its horizon has passed.

    The row carries the trade's own R as well as its deadline, because a session
    that is managing a position has to see both in the same breath: what it is
    risking, and whether the reason it exists has expired.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    opened = parse_iso(trade.get("openTime"))
    comment = (trade.get("clientExtensions") or {}).get("comment")
    expiry = parse_horizon(comment)
    plan = r_plan(trade)
    row = {
        "trade_id": str(trade.get("id")),
        "instrument": trade.get("instrument"),
        "units": trade.get("currentUnits"),
        "entry": trade.get("price"),
        "unrealizedPL": float(trade.get("unrealizedPL") or 0.0),
        "opened_at": opened.isoformat() if opened else None,
        "age_hours": round((now - opened).total_seconds() / 3600, 1) if opened else None,
        "stop": ((trade.get("stopLossOrder") or {}) or {}).get("price"),
        "target": ((trade.get("takeProfitOrder") or {}) or {}).get("price"),
        "trailing": ((trade.get("trailingStopLossOrder") or {}) or {}).get("distance"),
        "horizon_hours": None,
        "horizon_at": None,
        "overdue_hours": None,
        "expired": False,
        # R, fixed at the entry, reported for measurement only.
        "entry_stop": plan["entry_stop"],
        "risk_pips": plan["risk_pips"],
        "r_level": plan["r_level"],
    }
    if expiry is not None:
        row["horizon_at"] = expiry.isoformat()
        row["overdue_hours"] = round((now - expiry).total_seconds() / 3600, 1)
        row["expired"] = now >= expiry
        if opened is not None:
            row["horizon_hours"] = round((expiry - opened).total_seconds() / 3600, 1)
    return row


def r_plan(trade: dict) -> dict:
    """The trade's own R, read off the trade rather than recalled.

    R is the distance from the entry to the stop that was written WHEN THE TRADE
    WAS OPENED, and it is fixed for the life of the trade. It is deliberately not
    recomputed from the live stop: the stop is allowed to move, and a stop
    tightened to protect a winner would shrink R and drag the 1R level down with
    it, so the same move would appear to score twice.

    Returns r_level = None when the trade carries no readable entry stop. No level
    is invented in that case; the row reports no R.
    """
    ins = str(trade.get("instrument") or "")
    comment = (trade.get("clientExtensions") or {}).get("comment")
    entry = float(trade.get("price") or 0.0)
    stop = parse_entry_stop(comment)
    out = {"entry": entry or None, "entry_stop": stop, "risk_pips": None,
           "r_level": None}
    if stop and entry and ins:
        ps = pip_size(ins)
        out["risk_pips"] = round(abs(entry - stop) / ps, 1)
        # 1R in the direction the trade is running: for a short, entry - R.
        out["r_level"] = round(2 * entry - stop, 3 if ps == 0.01 else 5)
    return out


def r_progress(trade: dict, quote: dict) -> dict:
    """How far into its own first R a trade has run, measured at the exit price.

    The exit reference is where the position would actually be closed - the bid for
    a long, the ask for a short - so "has it reached 1R" is answered with the price
    that would be paid, not the flattering one.
    """
    ins = str(trade.get("instrument") or "")
    plan = r_plan(trade)
    units = float(trade.get("currentUnits") or 0)
    entry = float(trade.get("price") or 0.0)
    if not entry or not plan["risk_pips"]:
        return {}
    ref = float(quote["bid"] if units > 0 else quote["ask"])
    direction = 1.0 if units > 0 else -1.0
    pips = (ref - entry) / pip_size(ins) * direction
    return {
        "exit_reference": ref,
        "pips": round(pips, 1),
        "r_multiple": round(pips / plan["risk_pips"], 2),
        "r_level": plan["r_level"],
        "pips_to_1r": round(plan["risk_pips"] - pips, 1),
        "at_1r": pips >= plan["risk_pips"],
    }


def horizon_rows(now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    return [horizon_row(t, now) for t in open_trades()]


def entry_pl_usd(instrument: str, entry: float, exit_price: float, units: float) -> float:
    """USD result if that exit fills, measured from the entry. Negative is a loss.

    Used on both sides of a stop move: the number is the risk when it is negative
    and the locked-in profit when it is positive, so a stop that is already past
    the entry is never mistaken for a wider risk.
    """
    direction = 1.0 if units > 0 else -1.0
    pips = (exit_price - entry) / pip_size(instrument) * direction
    return pips * abs(units) * _per_pip_value(instrument)


def trades_today() -> int:
    """How many orders have been sent today (UTC).

    Two independent sources, and the LARGER is used. The journal is primary
    because every order this system places goes through this tool, so it is
    authoritative and cannot be affected by API quirks. The account's own fills
    are checked as well, so a trade placed by hand outside this tool still counts
    against the daily cap.

    NOTE: OANDA's /transactions?from=<time> filter returns nothing on this
    account, so the API side uses /transactions/sinceid instead.
    """
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    journal = 0
    try:
        for line in LOG.read_text().splitlines():
            r = json.loads(line)
            if r.get("event") == "order_attempt" and r.get("sent") is True \
               and str(r.get("at", "")).startswith(today):
                journal += 1
    except Exception:
        journal = 0

    api_fills = 0
    try:
        last = int(summary().get("lastTransactionID", 0))
        if last > 1:
            tx = api("GET", f"/v3/accounts/{{acct}}/transactions/sinceid?id={max(1, last - 200)}")
            for t in tx.get("transactions", []):
                if (t.get("type") == "ORDER_FILL" and t.get("reason") == "MARKET_ORDER"
                        and str(t.get("time", "")).startswith(today)):
                    api_fills += 1
    except Exception:
        api_fills = 0

    return max(journal, api_fills)


def quote_one(instrument: str) -> dict:
    p = api("GET", f"/v3/accounts/{{acct}}/pricing?instruments={instrument}")["prices"][0]
    bid, ask = float(p["bids"][0]["price"]), float(p["asks"][0]["price"])
    ps = pip_size(instrument)
    return {"instrument": instrument, "bid": bid, "ask": ask,
            "spread_pips": round((ask - bid) / ps, 2), "tradeable": p.get("tradeable", False)}


def r_progress_rows(trades: list[dict]) -> list[dict]:
    """R progress for each open trade, priced at the exit side. Never fatal.

    A quote that fails leaves the row without progress rather than failing the
    whole state read: the account summary, the deadlines and the written rules are
    all still worth having when pricing is down.
    """
    out: list[dict] = []
    for t in trades:
        row = {"trade_id": str(t.get("id")), "instrument": t.get("instrument")}
        try:
            prog = r_progress(t, quote_one(str(t.get("instrument") or "")))
        except Exception as exc:                      # noqa: BLE001 - a read must not fail on a quote
            prog = {}
            row["error"] = str(exc)[:120]
        out.append({**row, **prog})
    return out


def excursion_rows(trades: list[dict]) -> list[dict]:
    """One sample per open trade: where the position is in its own R right now.

    A trade's best and worst points can only be measured while the position is open.
    The fill ledger records where a trade entered and where it left; it says nothing
    about the move in between, so "the stop was too tight" and "the target was too
    far" have been opinions on this desk rather than measurements. This samples the
    middle. Every sample is priced at the exit side, the bid for a long and the ask
    for a short, so a sample is never flattering.
    """
    out: list[dict] = []
    for t in trades:
        row = horizon_row(t)
        try:
            prog = r_progress(t, quote_one(str(t.get("instrument") or "")))
        except Exception as exc:                      # noqa: BLE001 - a sample must not fail the run
            prog = {"error": str(exc)[:120]}
        sample = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "trade_id": row["trade_id"], "instrument": row["instrument"],
            "units": row["units"], "entry": row["entry"], "stop": row["stop"],
            "target": row["target"], "risk_pips": row["risk_pips"],
            "horizon_at": row["horizon_at"], "age_hours": row["age_hours"],
            "unrealizedPL": row["unrealizedPL"],
        }
        sample.update(prog)
        out.append(sample)
    return out


def excursion_report(path: pathlib.Path | None = None) -> dict:
    """Per-trade MFE and MAE in R, from the samples on disk.

    Both figures are a LOWER bound on the true excursion, because the sampler runs
    every ten minutes and a spike between two samples is not seen. The sample count
    travels with them, and the honest reading of an MFE of 0.4R from twelve samples
    is "at least 0.4R", never "exactly 0.4R".
    """
    path = path or EXCURSIONS
    trades: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                s = json.loads(line)
            except Exception:                         # noqa: BLE001 - a torn line is skipped, not fatal
                continue
            tid = str(s.get("trade_id"))
            row = trades.setdefault(tid, {
                "trade_id": tid, "instrument": s.get("instrument"),
                "entry": s.get("entry"), "stop": s.get("stop"), "target": s.get("target"),
                "risk_pips": s.get("risk_pips"),
                "first_sample": s.get("at"), "last_sample": s.get("at"),
                "samples": 0, "unscored_samples": 0,
                "mfe_r": None, "mae_r": None, "mfe_pips": None, "mae_pips": None,
            })
            row["samples"] += 1
            row["last_sample"] = s.get("at")
            r, pips = s.get("r_multiple"), s.get("pips")
            if r is None or pips is None:
                row["unscored_samples"] += 1
                continue
            row["mfe_r"] = r if row["mfe_r"] is None else max(row["mfe_r"], r)
            row["mae_r"] = r if row["mae_r"] is None else min(row["mae_r"], r)
            row["mfe_pips"] = pips if row["mfe_pips"] is None else max(row["mfe_pips"], pips)
            row["mae_pips"] = pips if row["mae_pips"] is None else min(row["mae_pips"], pips)
    rows = sorted(trades.values(), key=lambda r: str(r["first_sample"] or ""))
    return {
        "source": str(path),
        "trades_sampled": len(rows),
        "note": "MFE and MAE are LOWER bounds: the sampler runs every ten minutes, so a "
                "spike between two samples is not seen, and a sample priced at the exit "
                "side is never flattering.",
        "trades": rows,
    }


def cmd_excursions(a) -> None:
    """Sample every open trade's progress, or report the samples already taken.

    Called by scripts/agent_time_stop.sh on the same ten-minute timer as the time
    stop, so recording costs no extra schedule and needs no model. Nothing here can
    place, move or close an order: it reads the account and appends to a file.
    """
    if getattr(a, "report", False):
        print(json.dumps(excursion_report(), indent=2))
        return
    trades = open_trades()
    samples = excursion_rows(trades)
    EXCURSIONS.parent.mkdir(parents=True, exist_ok=True)
    with EXCURSIONS.open("a") as fh:
        for s in samples:
            fh.write(json.dumps(s) + "\n")
    print(json.dumps({
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "open_trades": len(trades), "sampled": len(samples),
        "scored": sum(1 for s in samples if s.get("r_multiple") is not None),
        "samples": samples,
    }, indent=2))


def cmd_state(_a) -> None:
    s = summary()
    op, trades = open_positions(), open_trades()
    anchor = day_anchor()
    cur = float(s["NAV"])
    day_pl = cur - anchor
    horizons = [horizon_row(t) for t in trades]
    progress = r_progress_rows(trades)
    print(json.dumps({
        "balance": float(s["balance"]), "NAV": cur, "unrealizedPL": float(s["unrealizedPL"]),
        "marginAvailable": float(s["marginAvailable"]), "marginUsed": float(s["marginUsed"]),
        "open_positions": len(op), "open_trades": len(trades),
        "day_anchor_nav": anchor, "day_pl": round(day_pl, 2),
        "day_pl_pct": round(100 * day_pl / anchor, 2) if anchor else 0.0,
        "trades_today": trades_today(),
        "limits": {"max_risk_pct_per_trade": MAX_RISK_PCT_PER_TRADE,
                   "max_open_positions": MAX_OPEN_POSITIONS,
                   "max_trades_per_day": MAX_TRADES_PER_DAY,
                   "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
                   "max_spread_pips": MAX_SPREAD_PIPS},
        "day_pl_halt_triggered": (day_pl <= -abs(MAX_DAILY_LOSS_PCT) / 100 * anchor),
        # Shown on every state read, because a Friday session that does not know it
        # is Friday will find out from a refusal instead of from its brief.
        "friday_manage_only": friday_manage_only()[0],
        "friday_manage_only_reason": friday_manage_only()[1],
        "positions": [{"instrument": p["instrument"], "long": p["long"]["units"],
                       "short": p["short"]["units"], "unrealizedPL": p["unrealizedPL"]}
                      for p in op],
        # Shown on every state read so a session cannot manage a position without
        # seeing, in the same breath, whether the reason it exists has expired.
        "overdue_horizons": sum(1 for h in horizons if h["expired"]),
        "horizons": horizons,
        # And how far each position has run in its own R, so a session managing a
        # trade can report what it did in the units the trade was sized in.
        "r_progress": progress,
        # Which open trades have paid their first R and can therefore be added to,
        # so the aggressive technique is visible at the moment it is available rather
        # than remembered from the brief.
        "adds_available": add_opportunities(trades, progress),
    }, indent=2))


def cmd_quote(a) -> None:
    for ins in a.instruments:
        print(json.dumps(quote_one(ins)))


def cmd_candles(a) -> None:
    gran = a.granularity or "M15"
    n = a.count or 120
    r = api("GET", f"/v3/instruments/{a.instrument}/candles?granularity={gran}"
                   f"&count={n}&price=M")
    print(json.dumps([{"t": c["time"], "o": c["mid"]["o"], "h": c["mid"]["h"],
                       "l": c["mid"]["l"], "c": c["mid"]["c"], "complete": c["complete"]}
                      for c in r.get("candles", [])]))


def cmd_size(a) -> None:
    bal = nav()
    risk_usd = bal * a.risk_pct / 100
    per_pip = _per_pip_value(a.instrument)
    units = int(risk_usd / (a.stop_pips * per_pip)) if a.stop_pips > 0 else 0
    print(json.dumps({"instrument": a.instrument, "NAV": bal, "risk_usd": round(risk_usd, 2),
                      "stop_pips": a.stop_pips, "suggested_units": _round_units(units),
                      "max_units_by_risk": _max_units(a.instrument)}))


def _per_pip_value(instrument: str) -> float:
    """USD value of one pip for ONE unit, quote-currency approximated as USD."""
    ps = pip_size(instrument)
    q = instrument.split("_")[1]
    if q == "USD":
        return ps
    try:
        px = float(quote_one(instrument)["bid"])
        return ps / px
    except Exception:
        return ps


def _round_units(u: int) -> int:
    return int(u)


def _max_units(instrument: str) -> int:
    """Largest position whose loss at a 20-pip stop stays inside the per-trade cap."""
    bal = nav()
    risk_usd = bal * MAX_RISK_PCT_PER_TRADE / 100
    return _round_units(int(risk_usd / (20 * _per_pip_value(instrument))))


# ── Adding to a winner ──────────────────────────────────────────────────
#
# The one aggressive technique on this desk that adds size without adding risk,
# built 2026-10-07 at Steven's instruction that the desk stop trading as if the
# capital were large. The rule is narrow on purpose:
#
#   * a second position on an instrument that already has one is NOT a second idea,
#     it is either an ADD or the same bet taken twice. The audit of the seven live
#     entries found 7 of 7 sells, 6 of 7 EUR_USD, every one the same USD-strength
#     continuation, so the tool now refuses the same bet and allows the add;
#   * an add is allowed only when the open trade has already reached +1R measured at
#     the price it would actually be closed at, and the tool moves that trade's stop
#     to its entry BEFORE the add is sent, so the pair risks the original 6% and not
#     twelve;
#   * one add per position, inside the same 3-position cap, and the add carries its
#     own stop, target and horizon like any other entry.
#
# Why +1R and not "when it looks strong": both live winners never went past 0.29R
# against at any point and both reached target (fact 155), so a trade that has paid
# the first R is the one profile this desk has measured as worth pressing.
def add_candidate(instrument: str, direction: str) -> dict:
    """What a new entry in this instrument and direction would be, relative to what is open."""
    want_long = direction == "buy"
    out: dict = {"same_side": [], "opposite": None, "candidate": None, "qualified": False,
                 "reason": "", "progress": {}, "stop_move_to": None}
    for t in open_trades():
        if str(t.get("instrument") or "") != instrument:
            continue
        units = float(t.get("currentUnits") or 0)
        if (units > 0) != want_long:
            out["opposite"] = t
            continue
        out["same_side"].append(t)

    if out["opposite"] is not None:
        units = float(out["opposite"].get("currentUnits") or 0)
        out["reason"] = (
            f"{instrument} already has an open {'long' if units > 0 else 'short'} trade "
            f"(id {out['opposite'].get('id')}) and this is the {'short' if units > 0 else 'long'} side "
            f"of the same instrument. A hedge on one instrument pays the spread twice and "
            f"cancels the two theses; if the idea has flipped, close it first: "
            f"oanda_trade.py close {instrument}")
        return out

    if not out["same_side"]:
        return out
    if len(out["same_side"]) >= 2:
        out["candidate"] = out["same_side"][0]
        out["reason"] = (f"{instrument} already has {len(out['same_side'])} open trades and the "
                         f"first one has already been added to once. One add per position.")
        return out

    trade = out["same_side"][0]
    out["candidate"] = trade
    try:
        out["progress"] = r_progress(trade, quote_one(instrument))
    except Exception as exc:                                     # noqa: BLE001
        out["progress"] = {"error": str(exc)[:120]}
    plan = r_plan(trade)
    units = float(trade.get("currentUnits") or 0)
    if plan["entry_stop"] is None:
        out["reason"] = (f"{instrument} already has an open trade (id {trade.get('id')}) carrying no "
                         f"readable entry stop, so its R cannot be measured and it cannot be added to. "
                         f"Close it or leave it alone.")
        return out
    if not out["progress"].get("at_1r"):
        r = out["progress"].get("r_multiple")
        at = f"{r:+.2f}R" if r is not None else "an unmeasurable R"
        out["reason"] = (
            f"{instrument} already has an open trade (id {trade.get('id')}) at {at}. A second "
            f"position here is ADD TO A WINNER, allowed only once that trade has paid its first R "
            f"(it is {out['progress'].get('pips_to_1r')} pips short of 1R at the price it would be "
            f"closed at). Take the idea in another instrument, close this one, or wait.")
        return out
    out["qualified"] = True
    # The add is priced off the trade it is adding to: the original stop goes to its
    # own entry first, so the money at risk after the add is the add's risk alone.
    out["stop_move_to"] = plan["entry"]
    return out


def move_stop_to_breakeven(trade: dict, instrument: str, price: float) -> dict:
    """Move one open trade's stop to its entry. The only stop move the entry path makes."""
    body = {"stopLoss": {"price": _fmt_price(instrument, price), "timeInForce": "GTC"}}
    return api("PUT", f"/v3/accounts/{{acct}}/trades/{trade['id']}/orders", body)


def add_opportunities(trades: list[dict], progress: list[dict]) -> list[dict]:
    """Open trades that have paid their first R and can therefore be added to."""
    by_instrument: dict[str, list[dict]] = {}
    for t in trades:
        by_instrument.setdefault(str(t.get("instrument") or ""), []).append(t)
    rows: list[dict] = []
    for ins, ts in by_instrument.items():
        if len(ts) != 1:            # one add per position, never a chain of them
            continue
        t = ts[0]
        plan = r_plan(t)
        row = next((p for p in progress if p.get("trade_id") == str(t.get("id"))), {})
        if plan["entry_stop"] is None or not row.get("at_1r"):
            continue
        rows.append({"instrument": ins, "trade_id": str(t.get("id")),
                     "side": "buy" if float(t.get("currentUnits") or 0) > 0 else "sell",
                     "r_multiple": row.get("r_multiple"),
                     "note": ("at or past +1R: a same-side add is allowed, and the tool moves this "
                              "trade's stop to its entry before sending it")})
    return rows


def _preflight(instrument: str, units: int, stop: float | None, direction: str,
               horizon_hours: float | None = None) -> list[str]:
    """Refuse anything unsafe. Risk is computed from the ACTUAL stop, not assumed.

    The earlier version capped units on the assumption of a 20-pip stop, which
    left a hole: a permitted size with a 100-pip stop would risk 10% of the
    account, five times the cap. Risk is now derived from the real stop distance.
    """
    problems: list[str] = []
    ok, why = market_open()
    if not ok:
        problems.append(f"market closed: {why}")

    # Friday is manage-only. The market being open is not the question here: the
    # last hour of the week is open and it is the one hour in which the reason an
    # entry needs has been measured not to hold.
    manage_only, why_friday = friday_manage_only()
    if manage_only:
        problems.append(
            f"{why_friday} (fact 126: the hour-band edge was measured on weekday-pooled "
            f"data and excludes the ~2.5-day weekend gap a stop cannot cover)")

    # A trade whose written horizon has passed has lost the reason it was opened,
    # and carrying it while adding risk is how live trade 3 reached 43 hours. The
    # time stop normally closes these; this rail is the backstop for when the
    # timer is not running.
    for r in horizon_rows():
        if r["expired"]:
            problems.append(
                f"open trade {r['trade_id']} {r['instrument']} is {r['overdue_hours']:.1f}h past its "
                f"written horizon ({r['horizon_at']}) - close it before opening anything new: "
                f"oanda_trade.py close {r['instrument']}")

    if units < MIN_UNITS:
        problems.append(f"units {units} below minimum {MIN_UNITS}")
    if stop is None:
        problems.append("no stop supplied - every position must carry a stop loss")
    if HORIZON_REQUIRED and not horizon_hours:
        problems.append(
            "no horizon supplied - every entry must say how long its thesis is good for, "
            "with --horizon-hours N, so it can be closed when that expires")
    if len(open_positions()) >= MAX_OPEN_POSITIONS:
        problems.append(f"already {len(open_positions())} open positions (max {MAX_OPEN_POSITIONS})")

    # A second position on an instrument that already has one. This is the rail that
    # separates an add to a winner from the same bet taken twice, so it is checked
    # here, before anything is sized or sent.
    add = add_candidate(instrument, direction)
    if add["reason"]:
        problems.append(add["reason"])
    tt = trades_today()
    if tt >= MAX_TRADES_PER_DAY:
        problems.append(f"already {tt} trades today (max {MAX_TRADES_PER_DAY})")
    anchor = day_anchor()
    cur = nav()
    if cur - anchor <= -abs(MAX_DAILY_LOSS_PCT) / 100 * anchor:
        problems.append(f"daily loss halt: NAV {cur:.2f} vs anchor {anchor:.2f} "
                        f"is worse than -{MAX_DAILY_LOSS_PCT}%")
    q = quote_one(instrument)
    if not q["tradeable"]:
        problems.append(f"{instrument} not tradeable right now")
    if q["spread_pips"] > MAX_SPREAD_PIPS:
        problems.append(f"spread {q['spread_pips']} pips above the {MAX_SPREAD_PIPS}-pip cap")

    if stop is not None:
        ref = q["ask"] if direction == "buy" else q["bid"]
        ps = pip_size(instrument)
        stop_pips = abs(ref - stop) / ps
        if direction == "buy" and stop >= ref:
            problems.append(f"stop {stop} is not below the ask {ref} for a long")
        elif direction == "sell" and stop <= ref:
            problems.append(f"stop {stop} is not above the bid {ref} for a short")
        elif stop_pips < 1:
            problems.append(f"stop is {stop_pips:.2f} pips away - too tight to be a stop")
        else:
            risk_usd = stop_pips * units * _per_pip_value(instrument)
            cap_usd = nav() * MAX_RISK_PCT_PER_TRADE / 100
            if risk_usd > cap_usd:
                problems.append(
                    f"risk {risk_usd:.2f} USD ({stop_pips:.1f} pips x {units} units) exceeds the "
                    f"{MAX_RISK_PCT_PER_TRADE}% cap of {cap_usd:.2f} USD - reduce units or tighten the stop")
    return problems


def _order(a, direction: str) -> None:
    ins, units = a.instrument, abs(int(a.units))
    horizon_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=float(a.horizon_hours))
                  if getattr(a, "horizon_hours", None) else None)
    problems = _preflight(ins, units, a.stop, direction, a.horizon_hours)
    # An add to a winner is a real entry, not a variant of one: it carries its own
    # stop, target and horizon, and it is priced off the trade it is adding to.
    add = add_candidate(ins, direction)
    add_info: dict = {}
    if add["qualified"]:
        add_info = {"add_to_trade": str(add["candidate"].get("id")),
                    "add_stop_move_to": add["stop_move_to"],
                    "add_of_r": add["progress"].get("r_multiple")}
    # The reward is stated in R at the entry, so "aim 2R" is a number on the record
    # rather than a claim made afterwards. R is the stop distance written here.
    #
    # The toll this entry pays is stated at the same moment, and for the same reason: a
    # spread is only cheap or expensive relative to the risk unit the trade is taking.
    # At a 20-pip stop a 2-pip round trip spends a tenth of R, which is the number that
    # decides whether the trade can clear its own budget; in pips alone it reads like a
    # small number either way. The cap in _preflight refuses the entry when the quote is
    # above MAX_SPREAD_PIPS, so this line says by how much, and a refusal and a taken
    # trade carry the same measurement instead of only the refusal carrying one.
    _q = quote_one(ins)
    _ref = _q["ask"] if direction == "buy" else _q["bid"]
    _toll_stop_pips = abs(_ref - a.stop) / pip_size(ins) if a.stop else None
    entry_toll = {
        "spread_pips": _q["spread_pips"],
        "cap_pips": MAX_SPREAD_PIPS,
        "stop_pips": round(_toll_stop_pips, 2) if _toll_stop_pips else None,
        "share_of_r_pct": (round(100.0 * _q["spread_pips"] / _toll_stop_pips, 1)
                           if _toll_stop_pips else None),
        "above_cap": bool(_q["spread_pips"] > MAX_SPREAD_PIPS),
    }
    reward_r = None
    if a.stop and a.target:
        risk_pips = _toll_stop_pips
        if risk_pips and risk_pips > 0:
            reward_r = round(abs(a.target - _ref) / pip_size(ins) / risk_pips, 2)
    rec = {"event": "order_attempt", "instrument": ins, "direction": direction,
           "units": units, "reason": a.reason or "", "dry_run": bool(a.dry_run),
           "refused": bool(problems), "problems": problems,
           "horizon_hours": a.horizon_hours,
           "horizon_at": horizon_at.isoformat() if horizon_at else None,
           "entry_stop": a.stop, "reward_r": reward_r,
           "entry_toll": entry_toll, **add_info}
    if problems:
        log(rec)
        print(json.dumps({"status": "REFUSED", "problems": problems,
                          "entry_toll": entry_toll}, indent=2))
        sys.exit(3)
    signed = units if direction == "buy" else -units
    body: dict = {"order": {"instrument": ins, "units": str(signed),
                            "type": "MARKET", "timeInForce": "FOK",
                            "positionFill": "DEFAULT"}}
    if a.stop:
        body["order"]["stopLossOnFill"] = {"price": _fmt_price(ins, a.stop), "timeInForce": "GTC"}
    if a.target:
        body["order"]["takeProfitOnFill"] = {"price": _fmt_price(ins, a.target)}
    if horizon_at is not None or a.stop:
        # Written on the ORDER and on the TRADE it creates. OANDA does not copy
        # order client extensions onto the filled trade, and the time stop reads
        # the TRADE - so order-level extensions alone leave the deadline on an
        # object that is gone the moment it fills. The trader needs the deadline
        # to be readable from the open account position, not only from the order.
        # The entry stop rides along for the same reason: it is what R is measured
        # from, and it must not depend on the journal surviving.
        ext = {"tag": CLIENT_TAG,
               "comment": update_comment("", ins, horizon_at=horizon_at, entry_stop=a.stop)}
        body["order"]["clientExtensions"] = dict(ext)
        body["order"]["tradeClientExtensions"] = dict(ext)
    if a.dry_run:
        log({**rec, "sent": False})
        print(json.dumps({"status": "DRY_RUN_OK", "would_send": body,
                          "add": add_info or None, "quote": _q,
                          "entry_toll": entry_toll}, indent=2))
        return
    if add["qualified"]:
        # The risk comes off the open trade FIRST. If this fails, the add is not sent:
        # adding size on top of a position that still carries its full stop would put
        # two risk units on one idea, which is the thing this rule exists to prevent.
        try:
            move_stop_to_breakeven(add["candidate"], ins, add["stop_move_to"])
        except SystemExit:
            log({**rec, "sent": False, "error": "stop move to breakeven failed"})
            print(json.dumps({"status": "REFUSED", "problems": [
                f"could not move trade {add_info['add_to_trade']} stop to its entry "
                f"{add_info['add_stop_move_to']}, so the add was not sent"]}, indent=2))
            sys.exit(3)
        log({"event": "add_stop_to_breakeven", "instrument": ins,
             "trade_id": add_info["add_to_trade"], "stop": add_info["add_stop_move_to"],
             "reason": f"adding to a winner at {add_info['add_of_r']}R"})
    res = api("POST", "/v3/accounts/{acct}/orders", body)
    log({**rec, "sent": True, "response": {k: res.get(k) for k in
         ("orderFillTransaction", "orderCreateTransaction", "errorMessage")}})
    print(json.dumps(res, indent=2))


def cmd_close(a) -> None:
    if a.instrument == "ALL":
        op = open_positions()
        if not op:
            print(json.dumps({"status": "nothing to close"}))
            return
    else:
        op = [p for p in open_positions() if p["instrument"] == a.instrument]
        if not op:
            print(json.dumps({"status": f"no open position in {a.instrument}"}))
            return
    for p in op:
        ins = p["instrument"]
        long_u = int(p["long"]["units"]) if p["long"]["units"] else 0
        short_u = int(p["short"]["units"]) if p["short"]["units"] else 0
        units = -long_u if long_u else -short_u
        if a.dry_run:
            print(json.dumps({"status": "DRY_RUN_CLOSE", "instrument": ins, "units": str(units)}))
            continue
        res = api("POST", "/v3/accounts/{acct}/orders",
                  {"order": {"instrument": ins, "units": str(units), "type": "MARKET",
                             "timeInForce": "FOK", "positionFill": "REDUCE_ONLY"}})
        log({"event": "close", "instrument": ins, "units": str(units)})
        print(json.dumps(res, indent=2))


def _trades_for(instrument: str, trade_id: str | None) -> tuple[list[dict], list[str]]:
    """The open trades a management command applies to, plus why it cannot proceed."""
    trades = [t for t in open_trades() if t.get("instrument") == instrument]
    if trade_id:
        trades = [t for t in trades if str(t.get("id")) == str(trade_id)]
    problems: list[str] = []
    if not trades:
        problems.append(f"no open trade in {instrument}"
                        + (f" with id {trade_id}" if trade_id else ""))
    elif len(trades) > 1:
        problems.append(f"{len(trades)} open trades in {instrument} - pass --trade-id "
                        f"(ids {', '.join(str(t.get('id')) for t in trades)})")
    return trades, problems


def cmd_modify(a) -> None:
    """Move a stop or target, or attach a broker-side trailing stop, on an open trade.

    The entry rail is applied again here, because a stop is a risk limit and moving
    it out is how a bounded loss becomes an unbounded one: if the new stop would put
    more than the per-trade cap at risk measured FROM THE ENTRY, it is refused. A
    stop that is already past the entry - a lock-in - has no risk in it and is
    always allowed.

    The written horizon is NOT changed here. A trade's deadline is set where the
    thesis is stated, at the entry, and only the clock or a close ends it; if a
    session wants a longer life for an idea, it says so when it opens it.
    """
    ins = a.instrument
    ps = pip_size(ins)
    trades, problems = _trades_for(ins, a.trade_id)
    if a.stop is None and a.target is None and a.trail_pips is None:
        problems.append("nothing to change: pass --stop, --target or --trail-pips")
    if a.stop is not None and a.trail_pips is not None:
        problems.append("--stop and --trail-pips are alternatives - OANDA holds one stop per trade")

    trade = trades[0] if trades else None
    previous: dict = {}
    requested: dict = {}
    if trade is not None:
        cur_units = float(trade.get("currentUnits") or 0)
        long_side = cur_units > 0
        entry = float(trade.get("price") or 0)
        cap_usd = nav() * MAX_RISK_PCT_PER_TRADE / 100
        quote = quote_one(ins)
        ref = quote["bid" if long_side else "ask"]   # where an exit would fill
        if not quote["tradeable"]:
            problems.append(f"{ins} is not tradeable right now - a stop cannot be moved while "
                            f"the market is shut, and moving one against a stale price would be a guess")
        previous = {"stop": (trade.get("stopLossOrder") or {}).get("price"),
                    "target": (trade.get("takeProfitOrder") or {}).get("price"),
                    "units": trade.get("currentUnits"), "entry": entry, "exit_reference": ref}
        requested = {"stop": a.stop, "target": a.target, "trail_pips": a.trail_pips}

        if a.stop is not None:
            if long_side and a.stop >= ref:
                problems.append(f"stop {a.stop} is not below the bid {ref} for a long")
            elif (not long_side) and a.stop <= ref:
                problems.append(f"stop {a.stop} is not above the ask {ref} for a short")
            elif abs(ref - a.stop) / ps < MIN_STOP_PIPS:
                problems.append(f"stop is {abs(ref - a.stop) / ps:.2f} pips from the market, "
                                f"below the {MIN_STOP_PIPS}-pip minimum")
            else:
                risk = -entry_pl_usd(ins, entry, a.stop, cur_units)
                if risk > cap_usd:
                    problems.append(
                        f"that stop puts {risk:.2f} USD at risk from the entry {entry}, above the "
                        f"{MAX_RISK_PCT_PER_TRADE}% cap of {cap_usd:.2f} USD - a stop may be "
                        f"tightened or locked in, not widened past the cap")

        if a.target is not None:
            if long_side and a.target <= ref:
                problems.append(f"target {a.target} is not above the bid {ref} for a long")
            elif (not long_side) and a.target >= ref:
                problems.append(f"target {a.target} is not below the ask {ref} for a short")
            elif abs(a.target - ref) / ps < MIN_STOP_PIPS:
                problems.append(f"target is {abs(a.target - ref) / ps:.2f} pips from the market, "
                                f"below the {MIN_STOP_PIPS}-pip minimum")

        if a.trail_pips is not None:
            if a.trail_pips < MIN_STOP_PIPS:
                problems.append(f"trail {a.trail_pips} pips is below the {MIN_STOP_PIPS}-pip minimum")
            else:
                projected = ref - a.trail_pips * ps if long_side else ref + a.trail_pips * ps
                risk = -entry_pl_usd(ins, entry, projected, cur_units)
                if risk > cap_usd:
                    problems.append(
                        f"a {a.trail_pips}-pip trail would place the stop at {projected}, "
                        f"{risk:.2f} USD at risk from the entry {entry}, above the "
                        f"{MAX_RISK_PCT_PER_TRADE}% cap of {cap_usd:.2f} USD")

    rec = {"event": "modify_attempt", "instrument": ins,
           "trade_id": str(trade.get("id")) if trade else None,
           "requested": requested, "previous": previous, "reason": a.reason or "",
           "dry_run": bool(a.dry_run), "refused": bool(problems), "problems": problems}
    if problems:
        log(rec)
        print(json.dumps({"status": "REFUSED", "problems": problems}, indent=2))
        sys.exit(3)

    body: dict = {}
    if a.stop is not None:
        body["stopLoss"] = {"price": _fmt_price(ins, a.stop), "timeInForce": "GTC"}
    if a.target is not None:
        body["takeProfit"] = {"price": _fmt_price(ins, a.target)}
    if a.trail_pips is not None:
        body["trailingStopLoss"] = {"distance": _fmt_price(ins, a.trail_pips * ps),
                                    "timeInForce": "GTC"}
    if a.dry_run:
        log({**rec, "sent": False})
        print(json.dumps({"status": "DRY_RUN_OK", "trade_id": rec["trade_id"],
                          "would_send": body, "previous": previous}, indent=2))
        return
    res = api("PUT", f"/v3/accounts/{{acct}}/trades/{trade['id']}/orders", body)
    log({**rec, "sent": True,
         "response": {k: res.get(k) for k in
                      ("stopLossOrder", "takeProfitOrder", "trailingStopLossOrder",
                       "lastTransactionID", "errorMessage")}})
    print(json.dumps(res, indent=2))


def cmd_horizon(_a) -> None:
    """Every open trade against the horizon written on it. Read-only."""
    now = dt.datetime.now(dt.timezone.utc)
    rows = horizon_rows(now)
    print(json.dumps({
        "now": now.isoformat(),
        "open_trades": len(rows),
        "expired": sum(1 for r in rows if r["expired"]),
        "no_horizon": sum(1 for r in rows if r["horizon_at"] is None),
        "trades": rows,
    }, indent=2))


def cmd_time_stop(a) -> None:
    """Close any open trade whose written horizon has passed.

    This is the rule that makes a horizon mean something, and it is deliberately
    mechanical: the thesis was given a lifetime when it was written, and the clock
    ending it is the discipline, not a second opinion about the market. It reports
    and does nothing unless --enforce is passed, so a human can always dry-run it.

    It will not invent a deadline. A trade with no readable horizon is reported as
    NO_HORIZON and left alone, because closing a position on a deadline nobody
    wrote would be the same fault as ignoring one that was written.

    The kill switch stops this too. Closing reduces risk rather than adding it, so
    there is an argument for running through a halt, but a halt that still places
    orders is not a halt. It reports SKIPPED_HALTED and stays out of the way.
    """
    now = dt.datetime.now(dt.timezone.utc)
    halted = HALT_FILE.exists()
    open_now, why = market_open(now)
    actions: list[dict] = []
    for t in open_trades():
        row = horizon_row(t, now)
        if row["horizon_at"] is None:
            row["action"] = "NO_HORIZON"
            row["detail"] = ("the order carries no horizon - the time stop will not invent one; "
                             "close it by hand or let its stop or target do it")
        elif not row["expired"]:
            row["action"] = "HELD"
        elif halted:
            row["action"] = "SKIPPED_HALTED"
            row["detail"] = f"{HALT_FILE.name} is present - the kill switch stops automated orders"
        elif not open_now:
            row["action"] = "SKIPPED_MARKET_CLOSED"
            row["detail"] = f"{why}; it closes at the next open"
        elif not a.enforce:
            row["action"] = "WOULD_CLOSE"
        else:
            units = int(-float(t.get("currentUnits") or 0))
            res = api("POST", "/v3/accounts/{acct}/orders",
                      {"order": {"instrument": row["instrument"], "units": str(units),
                                 "type": "MARKET", "timeInForce": "FOK",
                                 "positionFill": "REDUCE_ONLY"}})
            fill = res.get("orderFillTransaction") or {}
            log({"event": "time_stop", "instrument": row["instrument"],
                 "trade_id": row["trade_id"], "units": str(units),
                 "opened_at": row["opened_at"], "horizon_at": row["horizon_at"],
                 "overdue_hours": row["overdue_hours"],
                 "fill_price": fill.get("price"), "pl": fill.get("pl")})
            row["action"] = "CLOSED"
            row["fill_price"] = fill.get("price")
            row["realized_pl"] = fill.get("pl")
        actions.append(row)
    print(json.dumps({
        "now": now.isoformat(), "enforce": bool(a.enforce), "halted": halted,
        "market_open": open_now,
        "closed": sum(1 for r in actions if r["action"] == "CLOSED"),
        "actions": actions,
    }, indent=2))


def cmd_transactions(a) -> None:
    """Recent fills. Uses sinceid: the /transactions?from= filter returns nothing here."""
    tx = api("GET", "/v3/accounts/{acct}/transactions/sinceid?id="
                    f"{max(1, int(summary().get('lastTransactionID', 0)) - int(a.count or 20) * 3)}")
    out = []
    for t in tx.get("transactions", []):
        if t.get("type") != "ORDER_FILL":
            continue
        out.append({"time": t.get("time"), "instrument": t.get("instrument"),
                    "units": t.get("units"), "price": t.get("price"),
                    "pl": t.get("pl"), "reason": t.get("reason")})
    print(json.dumps(out[-int(a.count or 20):], indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="OANDA tool for the trading agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state").set_defaults(fn=cmd_state)
    p = sub.add_parser("quote"); p.add_argument("instruments", nargs="+"); p.set_defaults(fn=cmd_quote)
    p = sub.add_parser("candles"); p.add_argument("instrument")
    p.add_argument("granularity", nargs="?", default="M15")
    p.add_argument("count", nargs="?", type=int, default=120); p.set_defaults(fn=cmd_candles)
    p = sub.add_parser("size"); p.add_argument("instrument")
    p.add_argument("--stop-pips", type=float, default=20.0)
    p.add_argument("--risk-pct", type=float, default=MAX_RISK_PCT_PER_TRADE); p.set_defaults(fn=cmd_size)
    for name in ("buy", "sell"):
        p = sub.add_parser(name)
        p.add_argument("instrument"); p.add_argument("units", type=int)
        p.add_argument("--stop", type=float); p.add_argument("--target", type=float)
        p.add_argument("--horizon-hours", type=float, default=None,
                       help="how long this thesis stays valid; the trade is closed when it expires")
        p.add_argument("--reason", default=""); p.add_argument("--dry-run", action="store_true")
        p.set_defaults(fn=lambda a, d=name: _order(a, d))
    p = sub.add_parser("modify")
    p.add_argument("instrument")
    p.add_argument("--stop", type=float); p.add_argument("--target", type=float)
    p.add_argument("--trail-pips", type=float,
                   help="attach a broker-side trailing stop at this distance")
    p.add_argument("--trade-id"); p.add_argument("--reason", default="")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_modify)
    p = sub.add_parser("horizon").set_defaults(fn=cmd_horizon)
    p = sub.add_parser("time-stop"); p.add_argument("--enforce", action="store_true")
    p.set_defaults(fn=cmd_time_stop)
    p = sub.add_parser("close"); p.add_argument("instrument"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_close)
    p = sub.add_parser("close-all"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=lambda a: (setattr(a, "instrument", "ALL"), cmd_close(a))[1])
    p = sub.add_parser("transactions"); p.add_argument("count", nargs="?", type=int, default=20)
    p.set_defaults(fn=cmd_transactions)
    p = sub.add_parser("excursions"); p.add_argument("--report", action="store_true")
    p.set_defaults(fn=cmd_excursions)
    p = sub.add_parser("market"); p.set_defaults(fn=lambda a: print(json.dumps(
        {"open": market_open()[0], "detail": market_open()[1]})))

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
