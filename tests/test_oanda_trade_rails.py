"""Rails on the live-order tool: the written horizon, R measurement, and stop moves.

These tests never touch the live account. Every network call the tool makes goes
through a module-level `api()` function, so it is replaced with a recorder and the
rails are exercised against a fake broker. The journal is replaced too: a test that
appended to logs/agent_trades.jsonl would corrupt the live trade record.

What is being defended, from the record rather than from taste:

  * live trade 3 was opened 2026-09-23 18:01Z with "expect 1.1340 within 24h" in
    its reason field and closed 43.0 hours later, because a horizon written in
    prose is enforced by nothing (tradebot_sci facts id 135);
  * the stop on a live position could not be moved at all, so a winner could only
    be protected by closing it and paying the spread again;
  * R is measured from the stop a trade was opened with, so a tightened stop cannot
    flatter the result. This is reporting only: the 1R partial close was withdrawn
    on 2026-10-01 (policy 16) and there is no partial exit to test.

Run: python3 -m pytest tests/test_oanda_trade_rails.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "oanda_trade.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("oanda_trade_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tool(monkeypatch, tmp_path):
    """The real module with the broker, the clock's side effects and the journal faked."""
    mod = load_tool()
    calls: dict = {"orders": [], "puts": [], "client_extensions": [], "log": []}
    state = {
        "trades": [],
        "positions": [],
        "market": (True, "open"),
        "nav": 240.0,
        "quote": {"instrument": "EUR_USD", "bid": 1.14000, "ask": 1.14015,
                  "spread_pips": 1.5, "tradeable": True},
        "halt": False,
        "client_extensions_fail": False,
        "fok_killed": False,
        "friday": (False, "not Friday"),
    }

    def fake_api(method, path, body=None):
        if method == "GET" and path.endswith("/summary"):
            return {"account": {"NAV": str(state["nav"]), "balance": str(state["nav"]),
                                "unrealizedPL": "0", "marginAvailable": "0",
                                "marginUsed": "0", "lastTransactionID": "1"}}
        if method == "GET" and path.endswith("/openTrades"):
            return {"trades": state["trades"]}
        if method == "GET" and path.endswith("/openPositions"):
            return {"positions": state["positions"]}
        if method == "POST" and path.endswith("/orders"):
            calls["orders"].append(body)
            if state.get("fok_killed"):
                return {"orderCancelTransaction": {"id": "9", "reason": "FOK_ORDER_NOT_FILLED",
                                                   "rejectReason": "TAKE_PROFIT_ON_FILL_LOSS"},
                        "errorMessage": "The market moved"}
            return {"orderFillTransaction": {"price": "1.14010", "pl": "-0.73"}}
        if method == "PUT" and path.endswith("/clientExtensions"):
            calls["client_extensions"].append((path, body))
            if state.get("client_extensions_fail"):
                raise RuntimeError("OANDA 400 on the write-back")
            return {"clientExtensions": (body or {}).get("clientExtensions"),
                    "lastTransactionID": "1000"}
        if method == "PUT" and "/trades/" in path:
            calls["puts"].append((path, body))
            return {"stopLossOrder": {"price": (body or {}).get("stopLoss", {}).get("price")},
                    "lastTransactionID": "999"}
        raise AssertionError(f"unexpected broker call: {method} {path}")

    monkeypatch.setattr(mod, "api", fake_api)
    monkeypatch.setattr(mod, "log", lambda rec: calls["log"].append(rec))
    monkeypatch.setattr(mod, "market_open", lambda now=None: state["market"])
    # The clock, not just the market. A rail that reads the real weekday would make
    # this file pass six days a week and fail on the seventh, which is the worst
    # kind of test: the failure would look like the change, not like the calendar.
    monkeypatch.setattr(mod, "friday_manage_only", lambda now=None: state["friday"])
    monkeypatch.setattr(mod, "nav", lambda: state["nav"])
    monkeypatch.setattr(mod, "day_anchor", lambda: state["nav"])
    monkeypatch.setattr(mod, "trades_today", lambda: 0)
    monkeypatch.setattr(mod, "open_positions", lambda: state["positions"])
    monkeypatch.setattr(mod, "quote_one", lambda ins: {**state["quote"], "instrument": ins})
    journal = tmp_path / "agent_trades.jsonl"
    monkeypatch.setattr(mod, "LOG", journal)
    halt = tmp_path / "AGENT_TRADING_HALT"
    monkeypatch.setattr(mod, "HALT_FILE", halt)
    return type("Ctx", (), {"mod": mod, "calls": calls, "state": state, "halt": halt,
                            "journal": journal})


def trade(units="-750", entry="1.13908", opened="2026-09-23T18:01:55.858109032Z",
          horizon="horizon=2026-09-24T18:01:55Z", trade_id="30637", entry_stop=None,
          **extra) -> dict:
    t = {
        "id": trade_id, "instrument": "EUR_USD", "currentUnits": units, "price": entry,
        "openTime": opened, "unrealizedPL": "-0.73",
        "stopLossOrder": {"price": "1.14220", "id": "1"},
        "takeProfitOrder": {"price": "1.13380", "id": "2"},
        "clientExtensions": ({"tag": "tradebot-sci",
                              "comment": " ".join(x for x in (horizon, entry_stop) if x)}
                             if (horizon or entry_stop) else {}),
    }
    t.update(extra)
    return t


def args(**kw) -> argparse.Namespace:
    base = {"instrument": "EUR_USD", "stop": None, "target": None, "trail_pips": None,
            "trade_id": None, "reason": "", "dry_run": False, "enforce": False,
            "units": 100, "horizon_hours": None, "instruments": ["EUR_USD"]}
    base.update(kw)
    return argparse.Namespace(**base)


# ── reading the horizon off the order ───────────────────────────────────

def test_iso_parser_handles_oanda_nanosecond_timestamps(tool):
    parsed = tool.mod.parse_iso("2026-09-23T18:01:55.858109032Z")
    assert parsed == dt.datetime(2026, 9, 23, 18, 1, 55, 858109, tzinfo=dt.timezone.utc)


def test_iso_parser_rejects_nonsense(tool):
    assert tool.mod.parse_iso("") is None
    assert tool.mod.parse_iso("not a time") is None
    assert tool.mod.parse_iso(None) is None


def test_horizon_is_read_back_out_of_the_client_comment(tool):
    when = tool.mod.parse_horizon("tradebot-sci horizon=2026-09-24T18:01:55Z")
    assert when == dt.datetime(2026, 9, 24, 18, 1, 55, tzinfo=dt.timezone.utc)


def test_a_comment_without_a_horizon_is_not_a_horizon(tool):
    assert tool.mod.parse_horizon("") is None
    assert tool.mod.parse_horizon(None) is None
    assert tool.mod.parse_horizon("took this off a level, no deadline in mind") is None
    assert tool.mod.parse_horizon("horizon=soon") is None


def test_row_reports_an_expired_horizon_and_its_overshoot(tool):
    now = dt.datetime(2026, 9, 25, 13, 4, 37, tzinfo=dt.timezone.utc)
    row = tool.mod.horizon_row(trade(), now)
    assert row["expired"] is True
    assert row["horizon_hours"] == 24.0
    assert row["age_hours"] == 43.0          # the recorded overshoot, reproduced
    assert row["overdue_hours"] == 19.0


def test_row_reports_a_live_horizon_as_held(tool):
    now = dt.datetime(2026, 9, 24, 12, 1, 55, tzinfo=dt.timezone.utc)
    row = tool.mod.horizon_row(trade(), now)
    assert row["expired"] is False
    assert row["overdue_hours"] == -6.0


def test_row_with_no_horizon_reports_none_not_expired(tool):
    row = tool.mod.horizon_row(trade(horizon=None), dt.datetime.now(dt.timezone.utc))
    assert row["horizon_at"] is None
    assert row["expired"] is False


# ── the entry rail ──────────────────────────────────────────────────────

def test_preflight_refuses_a_new_entry_while_a_trade_is_past_its_horizon(tool):
    tool.state["trades"] = [trade()]
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy", horizon_hours=24)
    assert any("past its written horizon" in p for p in problems), problems
    assert any("oanda_trade.py close EUR_USD" in p for p in problems), problems


def test_preflight_refuses_an_entry_with_no_horizon_at_all(tool):
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy")
    assert any("no horizon supplied" in p for p in problems), problems


def test_preflight_allows_an_entry_with_a_horizon_and_no_overdue_trade(tool):
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy", horizon_hours=24)
    assert problems == []


# ── The size ceiling and the slots, raised 2026-10-07 ───────────────────
#
# Steven raised the per-trade ceiling 4% to 6% of NAV and said the desk should stop
# trading as if the account were large: on 250 USD aiming back at the 7,000 he once
# funded, size and compounding are the levers. Two rails had to move with it, and
# these tests pin all three so a later edit cannot quietly put them back.

def test_the_size_ceiling_and_the_slots_are_the_ones_steven_set(tool):
    assert tool.mod.MAX_RISK_PCT_PER_TRADE == 6.0
    assert tool.mod.MAX_OPEN_POSITIONS == 3
    assert tool.mod.MAX_DAILY_LOSS_PCT == 12.0


def test_preflight_allows_three_open_positions_and_refuses_a_fourth(tool):
    tool.state["positions"] = [{"instrument": "EUR_USD"}, {"instrument": "GBP_USD"},
                               {"instrument": "USD_JPY"}]
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy", horizon_hours=24)
    assert any("already 3 open positions (max 3)" in p for p in problems), problems


def test_preflight_still_allows_the_third_position(tool):
    tool.state["positions"] = [{"instrument": "EUR_USD"}, {"instrument": "GBP_USD"}]
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy", horizon_hours=24)
    assert not any("open positions" in p for p in problems), problems


# ── Adding to a winner ──────────────────────────────────────────────────
#
# The aggressive technique that adds size without adding risk, built 2026-10-07.
# A second position on an instrument that already has one is not a second idea: the
# audit of the seven live entries found 7 of 7 sells and 6 of 7 EUR_USD, every one
# the same USD-strength continuation. So the tool allows the add and refuses the
# repeated bet, and the add is priced off the trade it is adding to.

FUTURE_HORIZON = "horizon=2030-01-01T00:00:00Z"


def at_1r(tool, one_r_met=True):
    """An open short with a readable entry stop, priced either side of its first R."""
    tool.state["trades"] = [trade(horizon=FUTURE_HORIZON, entry_stop="entry_stop=1.14220")]
    # entry 1.13908, stop 1.14220 = 31.2 pips of R, so 1R is 1.13596 on the exit side.
    ask = 1.13500 if one_r_met else 1.14015
    tool.state["quote"] = {**tool.state["quote"], "ask": ask, "bid": ask - 0.00015}


def test_a_second_position_before_the_first_paid_1r_is_refused_as_the_same_bet(tool):
    at_1r(tool, one_r_met=False)
    problems = tool.mod._preflight("EUR_USD", 100, 1.1440, "sell", horizon_hours=24)
    assert any("ADD TO A WINNER" in p for p in problems), problems
    assert any("short of 1R" in p for p in problems), problems


def test_the_add_is_allowed_once_the_open_trade_has_paid_its_first_r(tool):
    at_1r(tool, one_r_met=True)
    problems = tool.mod._preflight("EUR_USD", 100, 1.1380, "sell", horizon_hours=24)
    assert problems == [], problems


def test_the_open_trade_stop_moves_to_its_entry_before_the_add_is_sent(tool, monkeypatch):
    at_1r(tool, one_r_met=True)
    sequence: list[tuple] = []
    inner = tool.mod.api

    def recording(method, path, body=None):
        sequence.append((method, path))
        return inner(method, path, body)

    monkeypatch.setattr(tool.mod, "api", recording)
    tool.mod._order(args(units=100, stop=1.1380, target=1.1330, horizon_hours=24,
                         reason="add to a winner at +1R"), "sell")
    put = sequence.index(("PUT", "/v3/accounts/{acct}/trades/30637/orders"))
    post = sequence.index(("POST", "/v3/accounts/{acct}/orders"))
    assert put < post, "the add was sent before the risk came off the open trade"
    assert tool.calls["puts"][0][1]["stopLoss"]["price"] == "1.13908"     # its own entry
    assert tool.calls["orders"][0]["order"]["units"] == "-100"
    assert [r["event"] for r in tool.calls["log"]] == ["add_stop_to_breakeven", "order_attempt"]
    assert tool.calls["log"][1]["add_to_trade"] == "30637"
    assert tool.calls["log"][1]["add_of_r"] == 1.31


def test_the_add_is_not_sent_when_the_stop_move_fails(tool, monkeypatch, capsys):
    at_1r(tool, one_r_met=True)
    inner = tool.mod.api

    def failing_put(method, path, body=None):
        if method == "PUT":
            raise SystemExit(2)
        return inner(method, path, body)

    monkeypatch.setattr(tool.mod, "api", failing_put)
    with pytest.raises(SystemExit) as exc:
        tool.mod._order(args(units=100, stop=1.1380, target=1.1330, horizon_hours=24), "sell")
    assert exc.value.code == 3
    assert tool.calls["orders"] == []
    assert "the add was not sent" in capsys.readouterr().out


def test_a_hedge_on_an_instrument_that_is_already_open_is_refused(tool):
    tool.state["trades"] = [trade(horizon=FUTURE_HORIZON, entry_stop="entry_stop=1.14220")]
    problems = tool.mod._preflight("EUR_USD", 100, 1.1400, "buy", horizon_hours=24)
    assert any("pays the spread twice" in p for p in problems), problems


def test_state_reports_which_open_trade_can_be_added_to(tool, capsys):
    at_1r(tool, one_r_met=True)
    tool.mod.cmd_state(args())
    out = json.loads(capsys.readouterr().out)
    assert out["adds_available"] == [{"instrument": "EUR_USD", "trade_id": "30637",
                                      "side": "sell", "r_multiple": 1.31,
                                      "note": ("at or past +1R: a same-side add is allowed, and the "
                                               "tool moves this trade's stop to its entry before "
                                               "sending it")}]


def test_a_trade_with_no_readable_entry_stop_cannot_be_added_to(tool):
    tool.state["trades"] = [trade(horizon=FUTURE_HORIZON)]
    problems = tool.mod._preflight("EUR_USD", 100, 1.1440, "sell", horizon_hours=24)
    assert any("no readable entry stop" in p for p in problems), problems


# ── Friday is manage-only ───────────────────────────────────────────────
#
# The window at 20:00Z on Friday sits an hour before the week shuts at 21:00Z, so
# the market gate says the market is open and lets it through. The reason an entry
# needs is the one thing that is not available there: the hour-band edge was
# measured on weekday-pooled data and does not cover the weekend gap (fact 126).

def test_friday_is_read_in_new_york_not_in_utc():
    """20:00Z Friday is 16:00 in New York, and 01:00Z Saturday is still Friday there.

    Loaded without the fixture on purpose: the fixture replaces the clock so the
    rest of this file cannot depend on the day it is run, and this is the one test
    that has to exercise the real calendar arithmetic underneath.
    """
    mod = load_tool()
    assert mod.friday_manage_only(
        dt.datetime(2026, 10, 9, 20, 0, tzinfo=dt.timezone.utc))[0] is True
    assert mod.friday_manage_only(
        dt.datetime(2026, 10, 10, 1, 0, tzinfo=dt.timezone.utc))[0] is True
    assert mod.friday_manage_only(
        dt.datetime(2026, 10, 8, 20, 0, tzinfo=dt.timezone.utc))[0] is False
    assert mod.friday_manage_only(
        dt.datetime(2026, 10, 11, 20, 0, tzinfo=dt.timezone.utc))[0] is False


def test_preflight_refuses_a_new_entry_on_friday(tool):
    tool.state["friday"] = (True, "Friday in New York - manage what is open, open nothing new")
    problems = tool.mod._preflight("EUR_USD", 100, 1.1300, "buy", horizon_hours=24)
    assert any("manage what is open" in p for p in problems), problems
    assert any("weekend gap" in p for p in problems), problems


def test_the_friday_rail_does_not_block_closing_what_is_open(tool, capsys):
    """Manage-only has to mean the managing still works, or it is just closed."""
    tool.state["friday"] = (True, "Friday in New York - manage what is open, open nothing new")
    tool.state["positions"] = [{"instrument": "EUR_USD", "long": {"units": "0"},
                                "short": {"units": "-750"}, "unrealizedPL": "-0.73"}]
    tool.mod.cmd_close(argparse.Namespace(instrument="EUR_USD", trade_id=None, units=None,
                                          dry_run=False))
    assert tool.calls["orders"], "the Friday rail refused a close, which is the one thing it must not do"
    assert tool.calls["orders"][0]["order"]["units"] == "750"
    assert tool.calls["orders"][0]["order"]["positionFill"] == "REDUCE_ONLY"


def test_state_reports_friday_manage_only(tool, capsys):
    tool.state["friday"] = (True, "Friday in New York - manage what is open, open nothing new")
    tool.mod.cmd_state(argparse.Namespace())
    out = json.loads(capsys.readouterr().out)
    assert out["friday_manage_only"] is True
    assert "manage what is open" in out["friday_manage_only_reason"]


def test_order_refusal_exits_nonzero_and_does_not_send(tool, capsys):
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit) as exc:
        tool.mod._order(args(units=100, stop=1.1300, horizon_hours=24), "buy")
    assert exc.value.code == 3
    assert tool.calls["orders"] == []
    assert "past its written horizon" in capsys.readouterr().out


def test_order_puts_the_horizon_on_the_order_itself(tool, capsys):
    tool.mod._order(args(units=100, stop=1.1300, horizon_hours=24, dry_run=True), "buy")
    body = json.loads(capsys.readouterr().out)["would_send"]["order"]
    comment = body["clientExtensions"]["comment"]
    assert comment.startswith("horizon=")
    assert tool.mod.parse_horizon(comment) is not None


# ── the time stop ───────────────────────────────────────────────────────

def test_time_stop_reports_without_enforce_and_places_no_order(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.mod.cmd_time_stop(args(enforce=False))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "WOULD_CLOSE"
    assert out["closed"] == 0
    assert tool.calls["orders"] == []


def test_time_stop_closes_an_expired_trade_reduce_only(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.mod.cmd_time_stop(args(enforce=True))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "CLOSED"
    assert out["closed"] == 1
    order = tool.calls["orders"][0]["order"]
    assert order["positionFill"] == "REDUCE_ONLY"
    assert order["units"] == "750"          # opposite sign to a -750 short: it reduces
    entry = [r for r in tool.calls["log"] if r["event"] == "time_stop"][0]
    # the clock here is the real one, so the overshoot is only asserted to be real
    assert entry["overdue_hours"] > 0
    assert entry["horizon_at"].startswith("2026-09-24T18:01:55")
    assert entry["trade_id"] == "30637"


def test_time_stop_closes_a_long_with_negative_units(tool, capsys):
    tool.state["trades"] = [trade(units="1200", entry="1.14000")]
    tool.mod.cmd_time_stop(args(enforce=True))
    assert tool.calls["orders"][0]["order"]["units"] == "-1200"


def test_time_stop_holds_a_trade_inside_its_horizon(tool, capsys):
    tool.state["trades"] = [trade(horizon="horizon=2099-01-01T00:00:00Z")]
    tool.mod.cmd_time_stop(args(enforce=True))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "HELD"
    assert tool.calls["orders"] == []


def test_time_stop_never_invents_a_deadline(tool, capsys):
    tool.state["trades"] = [trade(horizon=None)]
    tool.mod.cmd_time_stop(args(enforce=True))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "NO_HORIZON"
    assert tool.calls["orders"] == []


def test_time_stop_respects_the_kill_switch(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.halt.write_text("halted")
    tool.mod.cmd_time_stop(args(enforce=True))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "SKIPPED_HALTED"
    assert tool.calls["orders"] == []


def test_time_stop_leaves_a_trade_alone_when_the_market_is_shut(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.state["market"] = (False, "Saturday - market closed")
    tool.mod.cmd_time_stop(args(enforce=True))
    out = json.loads(capsys.readouterr().out)
    assert out["actions"][0]["action"] == "SKIPPED_MARKET_CLOSED"
    assert tool.calls["orders"] == []


# ── moving a stop ───────────────────────────────────────────────────────

def test_entry_pl_is_signed_so_a_lock_in_is_not_read_as_a_loss(tool):
    mod = tool.mod
    # short 750 from 1.13908; a stop below the entry is locked-in profit, above is a loss
    assert mod.entry_pl_usd("EUR_USD", 1.13908, 1.13708, -750) > 0
    assert mod.entry_pl_usd("EUR_USD", 1.13908, 1.14220, -750) < 0
    assert mod.entry_pl_usd("EUR_USD", 1.14000, 1.14200, 1200) > 0


def test_modify_moves_the_stop(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.mod.cmd_modify(args(stop=1.14100, reason="behind the new swing high"))
    path, body = tool.calls["puts"][0]
    assert path.endswith("/trades/30637/orders")
    assert body["stopLoss"]["price"] == "1.14100"
    entry = [r for r in tool.calls["log"] if r["event"] == "modify_attempt"][0]
    assert entry["previous"]["stop"] == "1.14220"


def test_modify_locks_in_a_profit_by_moving_the_stop_past_the_entry(tool):
    # The short is in profit, so a valid stop (above the market) can sit below the
    # 1.13908 entry: the trade can no longer lose, only make less.
    tool.state["trades"] = [trade()]
    tool.state["quote"] = {**tool.state["quote"], "bid": 1.13700, "ask": 1.13715}
    tool.mod.cmd_modify(args(stop=1.13800))
    assert tool.calls["puts"][0][1]["stopLoss"]["price"] == "1.13800"


def test_modify_refuses_to_widen_the_stop_past_the_risk_cap(tool, capsys):
    # 240 USD NAV, 6% cap = 14.40 USD. 750 units is 0.075 USD a pip, so anything
    # more than 192 pips away from the entry breaches the cap.
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit) as exc:
        tool.mod.cmd_modify(args(stop=1.15900))
    assert exc.value.code == 3
    assert tool.calls["puts"] == []
    assert "above the 6.0% cap" in capsys.readouterr().out


def test_modify_refuses_a_stop_on_the_wrong_side_of_the_market(tool, capsys):
    tool.state["trades"] = [trade()]                 # a short, so the stop goes above the ask
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.13000))
    assert tool.calls["puts"] == []
    assert "not above the ask" in capsys.readouterr().out


def test_modify_refuses_a_stop_inside_the_minimum_distance(tool, capsys):
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.14016))
    assert "below the 1.0-pip minimum" in capsys.readouterr().out


def test_modify_attaches_a_trailing_stop_as_a_price_distance(tool):
    tool.state["trades"] = [trade()]
    tool.mod.cmd_modify(args(trail_pips=20))
    body = tool.calls["puts"][0][1]
    assert body["trailingStopLoss"]["distance"] == "0.00200"   # 20 pips on EUR_USD
    assert body["trailingStopLoss"]["timeInForce"] == "GTC"
    assert "stopLoss" not in body                              # OANDA holds one stop per trade


def test_modify_refuses_stop_and_trail_together(tool, capsys):
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.14100, trail_pips=20))
    assert "holds one stop per trade" in capsys.readouterr().out


def test_modify_refuses_a_trail_that_risks_more_than_the_cap(tool, capsys):
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(trail_pips=200))              # 15.80 USD at risk from the entry
    assert "above the 6.0% cap" in capsys.readouterr().out


def test_modify_refuses_when_nothing_was_asked_for(tool, capsys):
    tool.state["trades"] = [trade()]
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args())
    assert "nothing to change" in capsys.readouterr().out


def test_modify_refuses_when_there_is_no_open_trade(tool, capsys):
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.14100))
    assert "no open trade in EUR_USD" in capsys.readouterr().out


def test_modify_demands_a_trade_id_when_two_trades_share_the_instrument(tool, capsys):
    tool.state["trades"] = [trade(trade_id="1"), trade(trade_id="2")]
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.14100))
    assert "--trade-id" in capsys.readouterr().out


def test_modify_can_target_one_of_two_trades(tool):
    tool.state["trades"] = [trade(trade_id="1"), trade(trade_id="2")]
    tool.mod.cmd_modify(args(stop=1.14100, trade_id="2"))
    assert tool.calls["puts"][0][0].endswith("/trades/2/orders")


def test_modify_refuses_when_the_market_is_shut(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.state["quote"] = {**tool.state["quote"], "tradeable": False}
    with pytest.raises(SystemExit):
        tool.mod.cmd_modify(args(stop=1.14100))
    assert tool.calls["puts"] == []
    assert "not tradeable right now" in capsys.readouterr().out


def test_modify_dry_run_does_not_send(tool, capsys):
    tool.state["trades"] = [trade()]
    tool.mod.cmd_modify(args(stop=1.14100, dry_run=True))
    assert tool.calls["puts"] == []
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_RUN_OK"


# ── R, as a measurement ─────────────────────────────────────────────────
#
# R is the stop distance the trade was OPENED with, recorded on the trade as
# `entry_stop=`, and it does not move when the live stop does. It is reported so a
# session can say what a trade did in the units it was sized in. Nothing acts on it:
# the position leaves whole (policy 16, 2026-10-01).

def test_entry_records_the_stop_it_was_opened_with(tool, capsys):
    tool.mod._order(args(units=100, stop=1.1300, horizon_hours=24, dry_run=True), "buy")
    body = json.loads(capsys.readouterr().out)["would_send"]["order"]
    for side in ("clientExtensions", "tradeClientExtensions"):
        comment = body[side]["comment"]
        assert tool.mod.parse_entry_stop(comment) == 1.1300
        assert tool.mod.parse_horizon(comment) is not None


def test_entry_records_the_reward_in_r(tool, capsys):
    # the fake asks 1.14015; a 10-pip stop under it with a 30-pip target is 3R
    tool.mod._order(args(units=100, stop=1.13915, target=1.13715, horizon_hours=24,
                         dry_run=True), "buy")
    capsys.readouterr()
    entry = [r for r in tool.calls["log"] if r["event"] == "order_attempt"][0]
    assert entry["entry_stop"] == 1.13915
    assert entry["reward_r"] == 3.0


# ── the toll at the entry, in pips and in R ─────────────────────────────
#
# A spread is only cheap or expensive relative to the risk unit being taken. The fake
# account here quotes 1.5 pips; against a 10-pip stop that is 15 percent of R and against
# a 30-pip stop it is 5 percent. Same spread, different trade. It is recorded on
# refusals as well as on taken trades, because a refusal that does not say what it
# refused on cannot be audited afterwards.

def test_entry_records_the_toll_in_pips_and_as_a_share_of_r(tool):
    tool.mod._order(args(units=100, stop=1.13915, target=1.13715, horizon_hours=24,
                         dry_run=True), "buy")
    entry = [r for r in tool.calls["log"] if r["event"] == "order_attempt"][0]
    toll = entry["entry_toll"]
    assert toll["spread_pips"] == 1.5
    assert toll["stop_pips"] == 10.0
    assert toll["share_of_r_pct"] == 15.0
    assert toll["cap_pips"] == 3.0
    assert toll["above_cap"] is False


def test_the_same_spread_is_a_smaller_share_of_a_wider_stop(tool):
    tool.mod._order(args(units=100, stop=1.13715, target=1.13115, horizon_hours=24,
                         dry_run=True), "buy")
    entry = [r for r in tool.calls["log"] if r["event"] == "order_attempt"][0]
    assert entry["entry_toll"]["stop_pips"] == 30.0
    assert entry["entry_toll"]["share_of_r_pct"] == 5.0


def test_a_refusal_states_the_toll_it_refused_on(tool, capsys):
    tool.state["quote"] = {**tool.state["quote"], "spread_pips": 4.0}
    with pytest.raises(SystemExit) as exc:
        tool.mod._order(args(units=100, stop=1.13915, target=1.13715, horizon_hours=24),
                        "buy")
    assert exc.value.code == 3
    assert tool.calls["orders"] == []
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "REFUSED"
    assert out["entry_toll"]["above_cap"] is True
    assert out["entry_toll"]["share_of_r_pct"] == 40.0


def test_update_comment_keeps_a_token_it_does_not_own(tool):
    out = tool.mod.update_comment("horizon=2026-10-01T13:05Z took-it-off-a-level",
                                  "GBP_USD", horizon_at=dt.datetime(2026, 10, 1, 13, 5,
                                                                   tzinfo=dt.timezone.utc),
                                  entry_stop=1.332)
    assert "took-it-off-a-level" in out
    assert tool.mod.parse_entry_stop(out) == 1.332
    assert tool.mod.parse_horizon(out) is not None
    # a known token that is not passed is dropped rather than half-kept
    assert tool.mod.parse_horizon(tool.mod.update_comment(out, "GBP_USD")) is None


def test_entry_stop_parser_refuses_nonsense(tool):
    assert tool.mod.parse_entry_stop("") is None
    assert tool.mod.parse_entry_stop(None) is None
    assert tool.mod.parse_entry_stop("entry_stop=soon") is None
    assert tool.mod.parse_entry_stop("horizon=2026-10-01T13:05Z") is None


def test_r_is_measured_from_the_entry_stop_not_the_live_stop(tool):
    # Opened with a 31.2-pip stop (1.13908 entry, 1.14220), then the live stop was
    # tightened to 1.14000. R must stay at 1R = 1.13596: recomputing it from the
    # live stop would make 1R 1.13816 and flatter the trade by a whole R.
    t = trade(entry="1.13908", entry_stop="entry_stop=1.14220",
              stopLossOrder={"price": "1.14000", "id": "1"})
    plan = tool.mod.r_plan(t)
    assert plan["risk_pips"] == 31.2
    assert plan["r_level"] == 1.13596
    assert plan["entry_stop"] == 1.14220


def test_a_trade_with_no_recorded_entry_stop_has_no_level(tool):
    plan = tool.mod.r_plan(trade())
    assert plan["entry_stop"] is None
    assert plan["r_level"] is None
    assert plan["risk_pips"] is None


def test_r_progress_is_priced_where_the_position_would_be_closed(tool):
    t = trade(entry_stop="entry_stop=1.14220")            # short, 1R at 1.13596
    # the bid is past 1R but the ask - where a short actually buys back - is not
    prog = tool.mod.r_progress(t, {"bid": 1.13580, "ask": 1.13610})
    assert prog["pips"] == 29.8
    assert prog["r_multiple"] == 0.96
    assert prog["at_1r"] is False


def test_r_progress_reports_one_r_reached(tool):
    t = trade(entry_stop="entry_stop=1.14220")
    prog = tool.mod.r_progress(t, {"bid": 1.13570, "ask": 1.13590})
    assert prog["at_1r"] is True
    assert prog["pips_to_1r"] < 0


def test_state_reports_how_far_a_trade_has_run_in_r(tool, capsys):
    tool.state["trades"] = [trade(entry_stop="entry_stop=1.14220")]
    tool.state["quote"] = {**tool.state["quote"], "bid": 1.13570, "ask": 1.13590}
    tool.mod.cmd_state(args())
    out = json.loads(capsys.readouterr().out)
    assert out["r_progress"][0]["at_1r"] is True
    assert out["horizons"][0]["r_level"] == 1.13596
    assert out["horizons"][0]["risk_pips"] == 31.2
    # nothing in the report is an instruction to act on that number
    assert "at_1r_unbanked" not in out


def test_state_does_not_list_a_marker_it_does_not_own(tool, capsys):
    # a trade carrying the retired partial= marker still reads, and the state
    # report says nothing about it: that rule is gone (policy 16).
    tool.state["trades"] = [trade(entry_stop="entry_stop=1.14220",
                                  horizon="horizon=2099-01-01T00:00:00Z "
                                           "partial=0.5@2026-09-23T19:00:00Z")]
    tool.state["quote"] = {**tool.state["quote"], "bid": 1.13570, "ask": 1.13590}
    tool.mod.cmd_state(args())
    out = json.loads(capsys.readouterr().out)
    assert "at_1r_unbanked" not in out
    assert out["horizons"][0]["entry_stop"] == 1.14220
    assert out["horizons"][0]["expired"] is False


def test_state_survives_a_quote_failure(tool, capsys):
    tool.state["trades"] = [trade(entry_stop="entry_stop=1.14220")]
    tool.mod.cmd_state(args())
    capsys.readouterr()
    # the fake always prices, so force the failure the way a dead feed would
    tool.mod.quote_one = lambda ins: (_ for _ in ()).throw(RuntimeError("feed down"))
    tool.mod.cmd_state(args())
    out = json.loads(capsys.readouterr().out)
    assert out["r_progress"][0]["error"] == "feed down"
    assert out["horizons"][0]["r_level"] == 1.13596      # the written rules still read




# ── the excursion sampler: where a trade went, not just where it left ────

def test_excursion_sample_prices_a_short_at_the_ask(tool, monkeypatch, tmp_path):
    """A short is measured at the price it would be bought back at, never the flattering one."""
    tool.state["trades"] = [trade(entry_stop="entry_stop=1.14220")]
    out_file = tmp_path / "excursions.jsonl"
    monkeypatch.setattr(tool.mod, "EXCURSIONS", out_file)

    tool.mod.cmd_excursions(args())
    sample = json.loads(out_file.read_text().splitlines()[0])

    # entry 1.13908, ask 1.14015, short: 10.7 pips against, on a 31.2 pip stop
    assert sample["exit_reference"] == 1.14015
    assert sample["pips"] == -10.7
    assert sample["r_multiple"] == -0.34
    assert sample["risk_pips"] == 31.2
    assert sample["trade_id"] == "30637"


def test_excursion_report_bounds_mfe_and_mae(tool, monkeypatch, tmp_path):
    """The report must give the best and worst sample, and say how coarse that is."""
    tool.state["trades"] = [trade(entry_stop="entry_stop=1.14220")]
    out_file = tmp_path / "excursions.jsonl"
    monkeypatch.setattr(tool.mod, "EXCURSIONS", out_file)

    for bid in (1.13800, 1.13600, 1.14100):          # in profit, further in, then against
        tool.state["quote"] = {**tool.state["quote"], "bid": bid, "ask": bid + 0.00015}
        tool.mod.cmd_excursions(args())

    rep = tool.mod.excursion_report()
    row = rep["trades"][0]
    assert row["samples"] == 3
    assert row["mfe_r"] == 0.94                      # best sample, (1.13908-1.13615)/31.2
    assert row["mae_r"] == -0.66                     # worst sample, (1.13908-1.14115)/31.2
    assert "LOWER bound" in rep["note"]


def test_excursion_sampler_writes_nothing_when_flat(tool, monkeypatch, tmp_path):
    """No position, no row, no noise: the file stays empty and the run still succeeds."""
    tool.state["trades"] = []
    out_file = tmp_path / "excursions.jsonl"
    monkeypatch.setattr(tool.mod, "EXCURSIONS", out_file)
    tool.mod.cmd_excursions(args())
    assert out_file.exists()
    assert out_file.read_text() == ""


def test_excursion_sample_survives_a_dead_quote(tool, monkeypatch, tmp_path):
    """A feed that is down must not stop the sampler or lose the trade's identity."""
    tool.state["trades"] = [trade()]
    out_file = tmp_path / "excursions.jsonl"
    monkeypatch.setattr(tool.mod, "EXCURSIONS", out_file)
    tool.mod.quote_one = lambda ins: (_ for _ in ()).throw(RuntimeError("feed down"))

    tool.mod.cmd_excursions(args())
    sample = json.loads(out_file.read_text().splitlines()[0])
    assert sample["error"] == "feed down"
    assert sample["trade_id"] == "30637"
    assert "r_multiple" not in sample


# ── the day anchor: a day is measured from its start, not from its first read ──

def test_anchor_removes_money_already_banked_before_the_first_read(monkeypatch):
    """The 2026-10-07 case: an +18.94 win closed at 07:52Z and the first run was 13:03Z."""
    mod = load_tool()
    stored = {}
    monkeypatch.setattr(mod, "anchor_load", lambda day: None)
    monkeypatch.setattr(mod, "anchor_store", lambda day, row: stored.update(row))
    monkeypatch.setattr(mod, "nav", lambda: 250.518)
    monkeypatch.setattr(mod, "realized_pl_today", lambda now=None: 18.9376)

    anchor = mod.day_anchor()
    assert anchor == pytest.approx(231.5804, abs=0.001)
    assert stored["realized_before_first_read"] == 18.94
    assert stored["ledger_corrected"] is True


def test_anchor_is_written_once_and_then_left_alone(monkeypatch):
    """A second read must return the stored figure, not re-derive it from a moved NAV."""
    mod = load_tool()
    saved = {}

    def load(day):
        return saved.get(day)

    def store(day, row):
        saved[day] = row

    monkeypatch.setattr(mod, "anchor_load", load)
    monkeypatch.setattr(mod, "anchor_store", store)
    monkeypatch.setattr(mod, "nav", lambda: 250.518)
    calls = {"n": 0}

    def once(now=None):
        calls["n"] += 1
        return 18.9376

    monkeypatch.setattr(mod, "realized_pl_today", once)
    assert mod.day_anchor() == pytest.approx(231.5804, abs=0.001)
    monkeypatch.setattr(mod, "nav", lambda: 240.0)
    assert mod.day_anchor() == pytest.approx(231.5804, abs=0.001)
    assert calls["n"] == 1


def test_an_anchor_without_the_ledger_marker_is_corrected_not_trusted(monkeypatch):
    """A stored anchor that predates the ledger fix must be re-derived on sight."""
    mod = load_tool()
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    saved = {today: {"nav": 250.518, "ledger_corrected": False}}
    monkeypatch.setattr(mod, "anchor_load", lambda day: saved.get(day))
    monkeypatch.setattr(mod, "anchor_store", lambda day, row: saved.__setitem__(day, row))
    monkeypatch.setattr(mod, "nav", lambda: 250.518)
    monkeypatch.setattr(mod, "realized_pl_today", lambda now=None: 18.9376)

    assert mod.day_anchor() == pytest.approx(231.5804, abs=0.001)
    assert saved[today]["ledger_corrected"] is True


def test_a_losing_day_is_not_absorbed_into_its_own_anchor(monkeypatch):
    """The 2026-10-06 case, and the safety case: the -9.40 stop must still count."""
    mod = load_tool()
    monkeypatch.setattr(mod, "anchor_load", lambda day: None)
    monkeypatch.setattr(mod, "anchor_store", lambda day, row: None)
    monkeypatch.setattr(mod, "nav", lambda: 231.5804)
    monkeypatch.setattr(mod, "realized_pl_today", lambda now=None: -9.3992)

    anchor = mod.day_anchor()
    assert anchor == pytest.approx(240.9796, abs=0.001)
    assert 231.5804 - anchor == pytest.approx(-9.3992, abs=0.001)   # the day now reports its loss


def test_anchor_still_works_when_the_ledger_read_fails(monkeypatch):
    """A dead ledger read must not stop the state read; it degrades to the old behaviour."""
    mod = load_tool()
    stored = {}
    monkeypatch.setattr(mod, "anchor_load", lambda day: None)
    monkeypatch.setattr(mod, "anchor_store", lambda day, row: stored.update(row))
    monkeypatch.setattr(mod, "nav", lambda: 250.518)
    monkeypatch.setattr(mod, "realized_pl_today",
                        lambda now=None: (_ for _ in ()).throw(RuntimeError("ledger down")))
    assert mod.day_anchor() == pytest.approx(250.518, abs=0.001)
    assert stored["ledger_read_failed"] is True


def test_anchor_round_trips_through_the_database_layer(monkeypatch):
    """anchor_load and anchor_store speak tab-separated SQL to the mysql CLI."""
    mod = load_tool()
    seen = {}

    def fake_db_query(sql):
        seen["sql"] = sql
        if sql.startswith("SELECT"):
            return "231.5804\t250.518\t18.9400\t1\t0\n"
        return ""

    monkeypatch.setattr(mod, "db_query", fake_db_query)
    row = mod.anchor_load("2026-10-07")
    assert row == {"nav": pytest.approx(231.5804), "nav_at_first_read": pytest.approx(250.518),
                   "realized_before_first_read": pytest.approx(18.94),
                   "ledger_corrected": True, "ledger_read_failed": False}
    mod.anchor_store("2026-10-07", {**row, "ledger_corrected": True, "ledger_read_failed": False})
    assert seen["sql"].startswith("INSERT INTO day_anchor")
    assert "'2026-10-07'" in seen["sql"]
