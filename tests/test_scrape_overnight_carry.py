"""The overnight carry decision in forex_scrape_fade.

Steven's order, 2026-10-10: give the bot the ability to make calls on whether it holds
a trade past its written 24-hour horizon, the way the live desk did. Measured before it
was written, in scratch/overnight_carry.py, on the same de-clustering the deployed rule
uses: the trades still open at the horizon are 12 of 1,983 on the fifteen-pair set and
11 of 1,028 on the twenty-six-pair set, carrying those trades one more horizon is worth
+3.68 pips a trade (paired t +1.11) and +2.47 (t +0.72), and carrying only the ones
already in profit is +2.97 (t +2.07) and +1.61 (t +1.92). Eleven trades is not a sample,
so what these tests pin is the mechanism, not the edge: the bot must carry a trade that
is working, must close one that is not, must close at the second horizon whatever it is
doing, must still close at the written horizon when the rule is switched off, and must
never carry a trade whose standing it cannot read.

The decision is taken at the horizon and not at entry, because the fact that decides it
is how the trade stands by then.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState  # noqa: E402
from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade  # noqa: E402

PIP = 0.0001
HORIZON = 288


def snapshot(symbol="EURUSD", close=1.16000, bars=3):
    """A quiet 5m series whose last close is the price the decision reads."""
    last_ts = datetime(2026, 10, 9, 20, 55, tzinfo=timezone.utc)
    t0 = last_ts - timedelta(minutes=5 * (bars - 1))
    candles = [
        Candle(timestamp=t0 + timedelta(minutes=5 * i), open=close, high=close,
               low=close, close=close, volume=100.0)
        for i in range(bars)
    ]
    flat = TrendState(direction=0, strength=0.0)
    return MarketSnapshot(symbol=symbol, timeframe="5m", candles=candles, trend_htf=flat,
                          trend_ltf=flat)


def position(bars_held, side="long", entry=1.16000, stop=1.15800, pnl=None, risk=160.0):
    """An open position as the engine hands it to the strategy."""
    return {
        "symbol": "EURUSD",
        "direction": side,
        "side": side,
        "entry_price": entry,
        "stop_price": stop,
        "stop_loss": stop,
        "size": 8000.0,
        "bars_held": bars_held,
        "unrealized_pnl": pnl,
        "risk_usd": risk,
    }


# ── the decision at the horizon ──────────────────────────────────────────────────

def test_a_winner_is_carried_past_the_horizon():
    f = ForexScrapeFade()
    # +40 USD against a 160 USD risk unit is a quarter of the risk unit in profit.
    d = f.check_exit_signal(snapshot(), position(HORIZON, pnl=40.0), {})
    assert d is None, "a trade in profit at the horizon must be carried, not closed"


def test_a_loser_is_closed_at_the_horizon():
    f = ForexScrapeFade()
    d = f.check_exit_signal(snapshot(), position(HORIZON, pnl=-40.0), {})
    assert d is not None
    assert d.action == "close_position"
    assert "time stop" in str(d.structure_summary).lower()


def test_a_flat_trade_is_closed_at_the_horizon():
    f = ForexScrapeFade()
    d = f.check_exit_signal(snapshot(), position(HORIZON, pnl=0.0), {})
    assert d is not None, "the carry asks for profit, and flat is not profit"


def test_the_second_horizon_closes_even_a_winner():
    f = ForexScrapeFade()
    d = f.check_exit_signal(snapshot(), position(HORIZON + f.carry_bars, pnl=40.0), {})
    assert d is not None, "the carry may be taken once, never twice"


def test_a_winner_between_the_two_horizons_is_still_carried():
    f = ForexScrapeFade()
    d = f.check_exit_signal(snapshot(), position(HORIZON + 100, pnl=40.0), {})
    assert d is None


def test_the_carry_is_re_decided_every_bar():
    """A carried trade that stops working closes on the next bar, not a day later."""
    f = ForexScrapeFade()
    assert f.check_exit_signal(snapshot(), position(HORIZON, pnl=40.0), {}) is None
    d = f.check_exit_signal(snapshot(), position(HORIZON + 1, pnl=-5.0), {})
    assert d is not None


# ── the switches and the refusals ────────────────────────────────────────────────

def test_one_flag_puts_the_wall_back():
    f = ForexScrapeFade(scrape_carry_enabled=False)
    d = f.check_exit_signal(snapshot(), position(HORIZON, pnl=40.0), {})
    assert d is not None, "with the carry off the written horizon is the stop again"


def test_below_the_horizon_nothing_changes():
    f = ForexScrapeFade()
    assert f.check_exit_signal(snapshot(), position(HORIZON - 1, pnl=40.0), {}) is None
    assert f.check_exit_signal(snapshot(), position(10, pnl=-500.0), {}) is None


def test_an_unreadable_standing_is_not_carried():
    """No floating P&L and no entry price means no decision, so the trade closes."""
    f = ForexScrapeFade()
    pos = {"direction": "long", "size": 8000.0, "bars_held": HORIZON}
    d = f.check_exit_signal(snapshot(), pos, {})
    assert d is not None


def test_the_standing_falls_back_to_price_against_the_position_stop():
    f = ForexScrapeFade()
    # entry 1.16000, stop 1.15800 (20 pips), price 5 pips in favour: +0.25R
    px = 1.16050
    pos = {"direction": "long", "side": "long", "entry_price": 1.16000,
           "stop_price": 1.15800, "size": 8000.0, "bars_held": HORIZON,
           "unrealized_pnl": None, "risk_usd": None}
    d = f.check_exit_signal(snapshot(close=px), pos, {})
    assert d is None
    assert f._position_r(pos, snapshot(close=px)) == pytest.approx(0.25, abs=0.01)


def test_the_standing_is_signed_for_a_short():
    f = ForexScrapeFade()
    px = 1.15950                                   # 5 pips in favour of a short
    pos = {"direction": "short", "side": "short", "entry_price": 1.16000,
           "stop_price": 1.16200, "size": 8000.0, "bars_held": HORIZON,
           "unrealized_pnl": None, "risk_usd": None}
    assert f._position_r(pos, snapshot(close=px)) == pytest.approx(0.25, abs=0.01)


def test_the_threshold_is_configurable():
    f = ForexScrapeFade(scrape_carry_min_profit_r=0.5)
    d = f.check_exit_signal(snapshot(), position(HORIZON, pnl=40.0), {})   # +0.25R
    assert d is not None, "a raised threshold must refuse a quarter of a risk unit"


def test_the_extension_is_configurable():
    f = ForexScrapeFade(scrape_carry_bars=48)
    assert f.check_exit_signal(snapshot(), position(HORIZON + 47, pnl=40.0), {}) is None
    assert f.check_exit_signal(snapshot(), position(HORIZON + 48, pnl=40.0), {}) is not None


def test_the_startup_line_says_which_mode_is_on(caplog):
    import logging
    with caplog.at_level(logging.INFO):
        ForexScrapeFade()
        ForexScrapeFade(scrape_carry_enabled=False)
    text = caplog.text
    assert "overnight_carry=on" in text
    assert "overnight_carry=off" in text
