"""The end-of-day PnL push: what it says, when it stays quiet, and who sends it.

These tests never touch the broker and never touch Steven's phone. The OANDA reads
the message is built from are replaced with a fake ledger, and the notifier is
replaced with a recorder, so what is being defended here is the message and the
decision to send it rather than the network.

What is being defended, from the record rather than from taste:

  * the account is being rebuilt toward the 7,000 USD Steven once funded, and the
    push is how he tracks it, so a wrong sign or a stale figure is worse than no
    push at all;
  * a day with no trade must not push and must not exit non-zero, because a timer
    marked failed for doing nothing is how a working job gets switched off
    (incident 16 was exactly that, on the time-stop timer);
  * one push per day: the timer, a hand run and a retry must not add up to three
    notifications on his phone.

Run: python3 -m pytest tests/test_daily_pnl_push.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "daily_pnl_push.py"
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()


def load_tool():
    sys.path.insert(0, str(REPO / "tools"))
    spec = importlib.util.spec_from_file_location("daily_pnl_push_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fill(when: str, instrument: str, units: str, pl: float, reason: str) -> dict:
    return {"type": "ORDER_FILL", "time": when, "instrument": instrument, "units": units,
            "price": "1.00000", "pl": pl, "reason": reason}


FINANCING = {"type": "DAILY_FINANCING", "time": f"{TODAY}T21:00:00.000000000Z",
             "financing": 0.0418}


@pytest.fixture
def push(monkeypatch, tmp_path):
    """The real module with the broker, the phone and the state file replaced.

    The fake account is kept internally consistent: NAV is the 00:00Z anchor plus
    everything the fake ledger has realized today plus any open position's mark, and the
    balance is the same without the mark. The day figure is read off NAV against the
    anchor, so a mock whose NAV and ledger contradict each other would assert nothing.
    """
    mod = load_tool()
    ledger = [
        fill(f"{TODAY}T07:52:36.000000000Z", "EUR_USD", "2987", 18.9376, "TAKE_PROFIT_ORDER"),
        fill(f"{TODAY}T13:06:50.000000000Z", "EUR_USD", "-2987", 0.0, "MARKET_ORDER"),
    ]
    position = {"unrealizedPL": 0.0}
    sent: list[dict] = []
    real_push = mod.push
    anchor = 231.58

    def balance() -> float:
        realized = sum(float(r.get("pl") or 0.0) for r in ledger)
        fin = sum(float(r.get("financing") or 0.0) for r in ledger)
        return anchor + realized + fin

    def summary() -> dict:
        return {"lastTransactionID": "1000", "balance": f"{balance():.4f}",
                "NAV": f"{balance() + position['unrealizedPL']:.4f}",
                "unrealizedPL": f"{position['unrealizedPL']:.4f}"}

    monkeypatch.setattr(mod.ot, "summary", summary)
    monkeypatch.setattr(mod.ot, "api", lambda *a, **k: {"transactions": ledger})
    monkeypatch.setattr(mod.ot, "open_trades", lambda: [])
    monkeypatch.setattr(mod.ot, "day_anchor", lambda: anchor)
    monkeypatch.setattr(mod, "STATE", tmp_path / ".daily_pnl_pushed.json")
    monkeypatch.setattr(mod, "LOG", tmp_path / "daily_pnl_push.log")
    monkeypatch.setattr(mod, "push", lambda title, body, dry_run=False: (
        sent.append({"title": title, "body": body, "dry_run": dry_run}) or (True, "sent - {}")))
    monkeypatch.setattr(mod, "tell_secretary", lambda title, body: "queued")
    return type("Ctx", (), {"mod": mod, "ledger": ledger, "sent": sent, "tmp": tmp_path,
                            "real_push": real_push, "position": position, "anchor": anchor})


def run_main(push, *argv) -> int:
    old = sys.argv
    sys.argv = ["daily_pnl_push.py", *argv]
    try:
        return push.mod.main()
    finally:
        sys.argv = old


# ── the message ─────────────────────────────────────────────────────────

def test_a_win_is_signed_and_named_on_the_first_line(push, capsys):
    title, body, meta = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert title == "Tradebot day: +18.94 USD (+8.2%)"
    assert "DAY +18.94 USD (+8.2% from 231.58 at 00:00Z)" in body
    assert "win  EUR_USD short 2987: +18.94 (take profit order)" in body
    assert "GOAL 250.52 of 7,000 (3.6 percent)" in body
    assert meta["day_pl"] == 18.9376 and meta["closed_today"] == 1


def test_a_loss_day_carries_its_sign_and_the_holding_cost(push):
    push.ledger[:] = [
        fill(f"{TODAY}T07:53:23.000000000Z", "EUR_USD", "2919", -9.3992, "STOP_LOSS_ORDER"),
        FINANCING,
    ]
    title, body, _ = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert title.startswith("Tradebot day: -9.36 USD (-4.0%)")
    assert "loss EUR_USD short 2919: -9.40 (stop loss order)" in body
    assert "overnight holding cost: +0.04" in body


def test_an_entry_fill_with_no_result_is_not_reported_as_a_trade(push):
    push.ledger[:] = [fill(f"{TODAY}T13:06:50.000000000Z", "EUR_USD", "-2987", 0.0, "MARKET_ORDER")]
    _, body, meta = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert meta["closed_today"] == 0
    assert "nothing closed today" in body


def test_a_day_with_only_an_open_position_reports_the_marked_figure(push, monkeypatch):
    # The regression Steven hit on 2026-10-08: nothing closed and a 0.50 USD rollover
    # credit arrived, so the title read "+0.50 USD (+0.2%)" while the one open position
    # was 3.18 USD down. The day figure now includes the open mark, the parts are printed,
    # and the title says a position is open, so the number cannot be read as money banked.
    push.ledger[:] = [
        fill(f"{TODAY}T13:06:50.000000000Z", "EUR_USD", "-2987", 0.0, "MARKET_ORDER"),
        {"type": "DAILY_FINANCING", "time": f"{TODAY}T21:00:00.000000000Z",
         "financing": 0.5032},
    ]
    push.position["unrealizedPL"] = -3.1841
    monkeypatch.setattr(push.mod.ot, "open_trades", lambda: [
        {"id": "30673", "instrument": "EUR_USD", "currentUnits": "-2987", "price": "1.12613",
         "unrealizedPL": "-3.1841", "stopLossOrder": {"price": "1.12900"},
         "clientExtensions": {"comment": "horizon=2030-01-01T00:00:00Z entry_stop=1.129"},
         "openTime": f"{TODAY}T13:06:50.000000000Z"}])
    monkeypatch.setattr(push.mod.ot, "quote_one",
                        lambda ins: {"bid": 1.12800, "ask": 1.12815, "spread_pips": 1.5,
                                     "tradeable": True, "instrument": ins})
    title, body, meta = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert title == "Tradebot day: -2.68 USD (-1.2%), 1 open"
    assert "nothing closed today" in body
    assert "overnight holding cost: +0.50" in body
    assert "open position priced in: -3.18, not banked until closed" in body
    assert "ACCOUNT 232.08 USD cash, 228.90 USD with the open position priced in, 1 open." in body
    assert "EUR_USD short 2987 at" in body and "-3.18 USD" in body
    assert meta["components_gap"] == 0.0
    assert meta["open"] == 1


def test_a_day_whose_parts_do_not_add_up_says_so(push, monkeypatch):
    # Incident 15 was an anchor that swallowed a realized win, so the day read 0.00 while
    # the account had gained 18.94. The message names the disagreement instead of printing
    # whichever of the two numbers it happens to be holding.
    _, _, meta = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert meta["components_gap"] == 0.0                 # the consistent fixture reconciles
    monkeypatch.setattr(push.mod.ot, "day_anchor", lambda: 250.518)      # the stale anchor
    _, body, meta = push.mod.compose(push.mod.dt.date.fromisoformat(TODAY))
    assert meta["components_gap"] == -18.94
    assert "the day anchor and the ledger disagree" in body


# ── when it stays quiet ─────────────────────────────────────────────────

def test_a_day_with_no_trade_pushes_nothing_and_exits_zero(push, capsys):
    push.ledger.clear()
    assert run_main(push) == 0
    assert push.sent == []
    assert "no push sent" in capsys.readouterr().out


def test_a_day_is_pushed_once_even_when_the_job_runs_twice(push):
    assert run_main(push) == 0
    assert len(push.sent) == 1
    assert run_main(push) == 0                      # the timer firing again
    assert len(push.sent) == 1
    state = json.loads((push.tmp / ".daily_pnl_pushed.json").read_text())
    assert state["date"] == TODAY and state["title"] == push.sent[0]["title"]


def test_a_test_push_is_labelled_and_does_not_consume_the_day(push):
    # The secretary asked on 2026-10-07 that a test push read as a test, and that the
    # real evening push still go out: the prefix is added by the tool and the once-a-day
    # guard is left untouched.
    assert run_main(push, "--test") == 0
    assert len(push.sent) == 1
    assert push.sent[0]["title"].startswith("TEST - Tradebot day: +18.94 USD")
    assert not (push.tmp / ".daily_pnl_pushed.json").exists()
    assert run_main(push) == 0                       # the real push still goes out
    assert len(push.sent) == 2
    assert not push.sent[1]["title"].startswith("TEST")


def test_a_rebuilt_past_day_is_printed_and_never_sent(push):
    assert run_main(push, "--date", "2026-10-06") == 0
    assert push.sent == []


def test_a_dry_run_prints_the_exact_message_and_sends_nothing(push, capsys):
    assert run_main(push, "--dry-run") == 0
    assert push.sent == []
    assert "(dry run: this is the exact message)" in capsys.readouterr().out


# ── who sends it ────────────────────────────────────────────────────────

def test_the_push_goes_through_the_secretary_notifier(push, monkeypatch):
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = "sent - {}"
        stderr = ""

    monkeypatch.setattr(push.mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    ok, detail = push.real_push("Title here", "Body here", dry_run=False)
    assert ok and "sent" in detail
    assert str(push.mod.SECRET_NOTIFIER) in calls[0]
    assert "--message" in calls[0] and "Body here" in calls[0]
    assert "--title" in calls[0] and "Title here" in calls[0]
    assert "--dry-run" not in calls[0]


def test_the_dry_run_flag_reaches_the_notifier(push, monkeypatch):
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = "[dry-run] would push: x"
        stderr = ""

    monkeypatch.setattr(push.mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    push.real_push("T", "B", dry_run=True)
    assert calls[0][-1] == "--dry-run"


def test_a_failed_notifier_is_reported_and_not_recorded_as_sent(push, monkeypatch):
    class Failed:
        returncode = 1
        stdout = "FAILED - {}"
        stderr = ""

    asked: list[str] = []
    monkeypatch.setattr(push.mod, "push", push.real_push)     # the real notifier path
    monkeypatch.setattr(push.mod, "tell_secretary",
                        lambda title, body: asked.append(title) or "queued")
    monkeypatch.setattr(push.mod.subprocess, "run", lambda cmd, **kw: Failed())
    assert run_main(push) == 0                       # a failed push is not a systemd fault
    assert not (push.tmp / ".daily_pnl_pushed.json").exists()
    # The phone is not the only channel: a failed push is handed to the secretary so the
    # message still arrives, and the absent state file means the next run retries it.
    assert asked and asked[0].startswith("[PUSH FAILED, please send by hand]")
