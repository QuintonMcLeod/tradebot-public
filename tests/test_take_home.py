"""The take-home rule: what a win pays, and what a withdrawal does to the peak.

The rule is policy 22 and it is stated in Documentation/AGENT_TRADING_BRIEF.md: per
winning close, 50 percent of the realized win, 75 percent when the win is 2.5 percent
or more of the account, nothing while a position is open, nothing while the balance
sits below its own peak, and the peak re-based after each payout.

`decide()` in tools/take_home.py is that rule as arithmetic: no database, no broker and
no clock, so it can be exercised on a written ledger. Two faults that this file pins
down were live in the tool before it, and both would have shown up as money:

  * the re-basing was computed and then thrown away, because the peak was only written
    when it rose. A payout takes the peak down, so on the next run the paid win's own
    balance put it straight back up and the desk was shielded from paying ever again;
  * a withdrawal is not a fill, so every balance reconstructed backwards from today's
    balance is short by what has left. The account then has to earn back, in cash, the
    money it already paid him before any further payout is allowed.

Run: python3 -m pytest tests/test_take_home.py -q
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "take_home.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("take_home_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def th():
    return load_tool()


def fill(key: str, closed_at: str, pnl: float, before: float, instrument: str = "EURUSD"):
    return dict(key=key, closed_at=closed_at, instrument=instrument,
                pnl=pnl, balance_before=before, balance_after=before + pnl)


# ── the tiers ───────────────────────────────────────────────────────────────

def test_a_win_at_the_peak_pays_the_high_tier(th):
    """240 -> 250 is a 4.2 percent win, so the 75 percent tier applies."""
    fills = [fill("t1", "2026-10-13 12:00:00", 10.0, 240.0)]
    peak, rows = th.decide(fills, 240.0, {}, [], 250.0)
    assert [r["state"] for r in rows] == ["PAYDAY"]
    assert rows[0]["take_pct"] == 75.0
    assert rows[0]["take_usd"] == pytest.approx(7.5)
    assert rows[0]["kept_usd"] == pytest.approx(2.5)
    assert peak == pytest.approx(242.5), "the peak is re-based to 250 minus the 7.50 paid"


def test_a_small_win_pays_half(th):
    """1 percent of the account is under the 2.5 percent tier line."""
    fills = [fill("t1", "2026-10-13 12:00:00", 2.4, 240.0)]
    _, rows = th.decide(fills, 240.0, {}, [], 242.4)
    assert rows[0]["take_pct"] == 50.0
    assert rows[0]["take_usd"] == pytest.approx(1.2)


def test_the_tier_line_is_two_and_a_half_percent(th):
    fills = [fill("t1", "2026-10-13 12:00:00", 6.0, 240.0)]     # exactly 2.5 percent
    _, rows = th.decide(fills, 240.0, {}, [], 246.0)
    assert rows[0]["take_pct"] == 75.0


# ── the shield ──────────────────────────────────────────────────────────────

def test_a_win_below_the_peak_pays_nothing(th):
    fills = [fill("t1", "2026-10-13 12:00:00", 5.0, 250.0)]
    peak, rows = th.decide(fills, 277.0783, {}, [], 255.0)
    assert [r["state"] for r in rows] == ["SHIELDED"]
    assert rows[0]["take_usd"] == 0.0
    assert peak == pytest.approx(277.0783), "a shielded win cannot lower the peak"


def test_a_loss_is_never_paid_and_never_becomes_the_peak(th):
    fills = [fill("t1", "2026-10-13 12:00:00", -16.8275, 277.0783)]
    peak, rows = th.decide(fills, 277.0783, {}, [], 260.2508)
    assert rows == []
    assert peak == pytest.approx(277.0783)


def test_the_peak_a_win_is_judged_against_is_the_one_before_it_closed(th):
    """The win that takes the account to a new high is paid, not shielded by itself."""
    fills = [fill("t1", "2026-10-13 12:00:00", 10.0, 240.0)]
    _, rows = th.decide(fills, 240.0, {}, [], 250.0)
    assert [r["state"] for r in rows] == ["PAYDAY"]


# ── the re-basing has to survive the next run ───────────────────────────────

def test_a_paid_win_does_not_put_the_peak_back_up_on_the_next_run(th):
    """The fault this file exists for: the re-base was computed and then discarded."""
    fills = [fill("t1", "2026-10-13 12:00:00", 10.0, 240.0)]
    peak1, rows1 = th.decide(fills, 240.0, {}, [], 250.0)
    assert peak1 == pytest.approx(242.5)

    # Second run: the row exists, the account has since climbed to 245.
    paid = {r["closing_fill"]: r["state"] for r in rows1}
    peak2, rows2 = th.decide(fills, peak1, paid, [], 245.0)
    assert rows2 == [], "the same closing fill is never paid twice"
    assert peak2 == pytest.approx(242.5), "the stored peak stands; the paid win does not raise it"
    assert th.resolve_state(0, 0.0, 245.0, peak2) == "WAITING"


# ── money that has left the account ─────────────────────────────────────────

def test_a_withdrawal_does_not_shield_the_desk_that_paid_it(th):
    """250 - 7.50 taken out leaves 242.50, which is the re-based peak, not below it."""
    fills = [fill("t1", "2026-10-13 12:00:00", 10.0, 240.0)]
    peak, rows = th.decide(fills, 240.0, {}, [], 250.0)
    paid = {r["closing_fill"]: r["state"] for r in rows}
    taken_out = [("2026-10-13 13:00:00", 7.5)]

    peak2, rows2 = th.decide(fills, peak, paid, taken_out, 242.5)
    assert rows2 == []
    assert peak2 == pytest.approx(242.5)
    assert th.resolve_state(0, 0.0, 242.5, peak2) == "WAITING", \
        "after the transfer the desk is level with its peak, not under it"

    # And the next winner, out of new ground, pays.
    fills3 = fills + [fill("t2", "2026-10-14 12:00:00", 4.0, 242.5)]
    peak3, rows3 = th.decide(fills3, peak2, paid, taken_out, 246.5)
    assert [r["state"] for r in rows3] == ["PAYDAY"]
    assert rows3[0]["take_usd"] == pytest.approx(2.0), "a small win out of new ground pays half"


def test_a_balance_from_before_a_withdrawal_is_read_as_it_stood_then(th):
    """Without the add-back the earlier balance reads 7.50 low and the peak is wrong."""
    taken_out = [("2026-10-13 13:00:00", 7.5)]
    assert th.as_was(232.5, "2026-10-13 12:00:00", taken_out) == pytest.approx(240.0)
    assert th.as_was(232.5, "2026-10-14 12:00:00", taken_out) == pytest.approx(232.5)


def test_money_still_in_the_account_is_not_a_withdrawal(th):
    """A PAYDAY row with no withdrawn_at is capital still at risk, so it adds nothing back."""
    assert th.as_was(232.5, "2026-10-13 12:00:00", []) == pytest.approx(232.5)


# ── what the desk reports ───────────────────────────────────────────────────

def test_locked_beats_everything_while_a_position_is_open(th):
    assert th.resolve_state(1, 12.0, 250.0, 240.0) == "LOCKED"


def test_owing_beats_being_under_the_peak(th):
    assert th.resolve_state(0, 7.5, 230.0, 240.0) == "PAYDAY"


def test_a_shielded_flat_desk_says_so(th):
    assert th.resolve_state(0, 0.0, 230.0, 240.0) == "SHIELDED"


def test_a_flat_desk_at_its_peak_has_nothing_to_pay(th):
    assert th.resolve_state(0, 0.0, 240.0, 240.0) == "WAITING"
