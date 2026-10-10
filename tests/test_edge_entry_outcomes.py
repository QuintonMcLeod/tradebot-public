"""Pins the outcome rule in tools/edge_entry.py:outcomes.

The rule decides what a trade is worth when it reaches neither its target nor its stop
inside the horizon. It used to charge the whole stop, because `lost = fs <= ft` is true
when both barriers are absent and both indexes sit at the 10**6 sentinel, which made
the `open_` bucket unreachable and left `fin` as dead code. At a four-hour horizon on
this venue about 35 percent of trades time out, so that decision moved the answer by
several pips per trade and produced the recorded "the deployed bracket cannot work"
figures (facts 176 and 177 in the tradebot_sci schema).

Four cases are pinned here, one per branch, plus the two that must not change: a
genuine same-bar tie is still a loss, and a real stop-out is still charged the stop.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from edge_entry import outcomes  # noqa: E402

HORIZON = 4
TARGET, STOP, COST = 15.0, 20.0, 3.0


def run(mfe_rows, mae_rows, fin, cost=COST):
    """One call to outcomes() over the given per-trade excursion paths."""
    return outcomes(np.array(mfe_rows, dtype=float), np.array(mae_rows, dtype=float),
                    np.array(fin, dtype=float), TARGET, STOP, cost)


def test_trade_that_hits_the_target_is_a_win():
    # reaches +15 pips on bar 1, never goes 20 against
    out = run([[1.0, 16.0, 16.0, 16.0]], [[-2.0, -2.0, -2.0, -2.0]], [9.0])
    assert out["hit"] == pytest.approx(100.0)
    assert out["open"] == pytest.approx(0.0)
    assert out["gross"] == pytest.approx(TARGET)


def test_trade_that_hits_the_stop_is_charged_the_stop():
    # reaches -20 pips on bar 1
    out = run([[1.0, 1.0, 1.0, 1.0]], [[-3.0, -20.0, -20.0, -20.0]], [-12.0])
    assert out["hit"] == pytest.approx(0.0)
    assert out["open"] == pytest.approx(0.0)
    assert out["gross"] == pytest.approx(-STOP)


def test_trade_that_reaches_neither_barrier_exits_at_its_own_close():
    """The regression. It used to be charged -20 pips instead of its +2 pips close."""
    out = run([[1.0, 4.0, 5.0, 6.0]], [[-1.0, -3.0, -4.0, -5.0]], [2.0])
    assert out["hit"] == pytest.approx(0.0)
    assert out["open"] == pytest.approx(100.0)
    assert out["gross"] == pytest.approx(2.0), (
        "a trade that times out must exit at its own close, not at the stop")


def test_open_trades_are_not_counted_as_losses_in_the_mean():
    """Half win, half time out: the mean must be the average of the two real outcomes."""
    out = run([[16.0] * HORIZON, [1.0] * HORIZON],
              [[-2.0] * HORIZON, [-2.0] * HORIZON],
              [9.0, 3.0])
    assert out["hit"] == pytest.approx(50.0)
    assert out["open"] == pytest.approx(50.0)
    assert out["gross"] == pytest.approx((TARGET + 3.0) / 2.0)


def test_same_bar_tie_is_still_a_loss():
    """A bar that contains both barriers still counts as the stop, as it always did."""
    out = run([[16.0, 16.0, 16.0, 16.0]], [[-21.0, -21.0, -21.0, -21.0]], [0.0])
    assert out["hit"] == pytest.approx(0.0)
    assert out["open"] == pytest.approx(0.0)
    assert out["gross"] == pytest.approx(-STOP)


def test_open_share_is_reported_so_a_short_horizon_cannot_hide():
    """The category that was dead is now visible to every caller."""
    out = run([[1.0] * HORIZON] * 3 + [[16.0] * HORIZON],
              [[-1.0] * HORIZON] * 3 + [[-1.0] * HORIZON],
              [2.0, 2.0, 2.0, 9.0])
    assert out["open"] == pytest.approx(75.0)
    assert out["n"] == 4


def test_cost_is_charged_once_per_trade():
    out_free = run([[16.0] * HORIZON], [[-1.0] * HORIZON], [9.0], cost=0.0)
    out_paid = run([[16.0] * HORIZON], [[-1.0] * HORIZON], [9.0], cost=3.0)
    assert out_free["gross"] - out_paid["gross"] == pytest.approx(0.0)
    assert out_free["net"] - out_paid["net"] == pytest.approx(3.0)
