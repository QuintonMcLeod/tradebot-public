"""The scrape-fade entry is a bar CLOSE, and the live path was giving it a poke.

The rule documented at the top of the strategy and validated on three years of data
is: long when price *closes* below the lowest low of the prior 20 bars, short when it
closes above the highest high, inside the 20:00-21:00 UTC hour. The backtest and the
replay feed it closed bars, so there the rule is the rule. The live engine does not:
runtime/cycle.py deliberately hands the strategy the raw provider list, whose last
candle is the bar still being formed, so `last.close` was the price at the instant of
a poll.

What that cost, read from the runner's own journal and the broker's own candles:

  * 2026-10-12 20:48:55Z, the running bot: "EURNZD: declined, break depth 1.2p below
    the 2.0p minimum" — the 20:45Z bar, part formed;
  * the same bar closed at 20:50Z 2.60 pips beyond its prior twenty-bar range, which
    is an entry by the rule as written;
  * the next poll, 20:55:07Z: "EURNZD: declined, no fresh break of the prior range",
    because by then the 20:50Z bar was newest and the qualifying close had moved into
    the range window.

So the live path could only ever see a break that was already at least at the minimum
depth at the exact moment of a poll. Over the two entry windows since the runner
restarted, the deepest break it reported was 1.8 pips, while the closed bars of those
windows contain a 2.6-pip break it never evaluated.

These tests do not touch the network, the database or the clock: the strategy's own
`datetime` is frozen so a bar is half-formed or closed by construction.

Run: python3 -m pytest tests/test_scrape_fade_bar_close.py -q
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MODULE = REPO / "src" / "tradebot_sci" / "strategy" / "variants" / "forex_scrape_fade.py"
sys.path.insert(0, str(REPO / "src"))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState  # noqa: E402

UTC = timezone.utc


def load_strategy_module():
    spec = importlib.util.spec_from_file_location("scrape_fade_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def frozen(monkeypatch):
    """Freeze the strategy's clock. Returns a function that sets the new 'now'."""
    mod = load_strategy_module()
    state = {"now": datetime(2026, 10, 14, 20, 48, tzinfo=UTC)}

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return state["now"].astimezone(tz) if tz else state["now"].replace(tzinfo=None)

    monkeypatch.setattr(mod, "datetime", FrozenDatetime)

    def set_now(when: datetime):
        state["now"] = when

    return mod, set_now


def candle(mod, when: datetime, *, high: float, low: float, close: float):
    return Candle(timestamp=when, open=(high + low) / 2, high=high, low=low,
                      close=close, volume=1.0)


def quiet_range(mod, end: datetime, bars: int = 20, top: float = 1.10000,
                bottom: float = 1.09900):
    """A flat twenty-bar range ending at `end`, one bar per five minutes."""
    out = []
    for i in range(bars):
        ts = end - timedelta(minutes=5 * (bars - i))
        out.append(candle(mod, ts, high=top, low=bottom, close=(top + bottom) / 2))
    return out


def snapshot(mod, symbol: str, candles):
    return MarketSnapshot(
        symbol=symbol, timeframe="5m", candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.0),
        trend_ltf=TrendState(direction="neutral", strength=0.0))


# A 1.6-pip live quote on EURUSD: under the strategy's own 1.9-pip ceiling, so the
# toll gate is not what these tests are measuring.
GATES = {"current_spread": 0.00016}


def test_a_half_formed_bar_is_not_a_signal(frozen):
    """The EURNZD case: 2.6 pips beyond the range mid-bar, and it must not fire."""
    mod, set_now = frozen
    set_now(datetime(2026, 10, 14, 20, 48, tzinfo=UTC))      # the 20:45 bar is open
    bars = quiet_range(mod, end=datetime(2026, 10, 14, 20, 40, tzinfo=UTC))
    bars.append(candle(mod, datetime(2026, 10, 14, 20, 45, tzinfo=UTC),
                       high=1.10026, low=1.09990, close=1.10026))   # 2.6 pips out
    strat = mod.ForexScrapeFade()
    assert strat.check_entry_signal(snapshot(mod, "EURUSD", bars), GATES) is None


def test_the_same_bar_fires_once_it_has_closed(frozen):
    """Nothing else changed: the break is real, it just needs the bar to be over."""
    mod, set_now = frozen
    set_now(datetime(2026, 10, 14, 20, 50, 30, tzinfo=UTC))  # 20:45 closed, 20:50 open
    bars = quiet_range(mod, end=datetime(2026, 10, 14, 20, 40, tzinfo=UTC))
    bars.append(candle(mod, datetime(2026, 10, 14, 20, 45, tzinfo=UTC),
                       high=1.10026, low=1.09990, close=1.10026))
    bars.append(candle(mod, datetime(2026, 10, 14, 20, 50, tzinfo=UTC),
                       high=1.10030, low=1.10010, close=1.10020))   # forming, quiet
    strat = mod.ForexScrapeFade()
    decision = strat.check_entry_signal(snapshot(mod, "EURUSD", bars), GATES)
    assert decision is not None, "a closed 2.6-pip break is an entry by the written rule"
    assert decision.action == "enter_short"
    assert decision.entry_price == pytest.approx(1.10026)


def test_a_shallow_half_formed_bar_still_does_not_fire(frozen):
    """And the bar that closed inside the range never fires either."""
    mod, set_now = frozen
    set_now(datetime(2026, 10, 14, 20, 48, tzinfo=UTC))
    bars = quiet_range(mod, end=datetime(2026, 10, 14, 20, 40, tzinfo=UTC))
    bars.append(candle(mod, datetime(2026, 10, 14, 20, 45, tzinfo=UTC),
                       high=1.10005, low=1.09990, close=1.10005))
    strat = mod.ForexScrapeFade()
    assert strat.check_entry_signal(snapshot(mod, "EURUSD", bars), GATES) is None


def test_the_entry_window_is_the_signal_bar_hour(frozen):
    """A bar forming in the 21:00 hour must not drag a 20:55 close out of the window."""
    mod, set_now = frozen
    set_now(datetime(2026, 10, 14, 21, 2, tzinfo=UTC))       # 21:00 bar forming
    bars = quiet_range(mod, end=datetime(2026, 10, 14, 20, 55, tzinfo=UTC))
    bars.append(candle(mod, datetime(2026, 10, 14, 21, 0, tzinfo=UTC),
                       high=1.10010, low=1.09995, close=1.10000))
    strat = mod.ForexScrapeFade()
    assert strat._in_window(snapshot(mod, "EURUSD", bars)) is True

    set_now(datetime(2026, 10, 14, 21, 6, tzinfo=UTC))       # now 21:05 is the signal
    bars.append(candle(mod, datetime(2026, 10, 14, 21, 5, tzinfo=UTC),
                       high=1.10010, low=1.09995, close=1.10000))
    assert strat._in_window(snapshot(mod, "EURUSD", bars)) is False


def test_replay_and_backtest_are_left_alone(frozen):
    """Every bar historical: nothing is dropped and the last bar is the signal."""
    mod, set_now = frozen
    set_now(datetime(2026, 10, 14, 20, 48, tzinfo=UTC))
    bars = quiet_range(mod, end=datetime(2026, 6, 1, 20, 40, tzinfo=UTC))
    bars.append(candle(mod, datetime(2026, 6, 1, 20, 45, tzinfo=UTC),
                       high=1.10026, low=1.09990, close=1.10026))
    strat = mod.ForexScrapeFade()
    assert len(strat._closed_candles(bars, "5m")) == len(bars)


@pytest.mark.parametrize("timeframe,seconds", [("5m", 300), ("1m", 60), ("1h", 3600),
                                               ("4h", 14400), ("1d", 86400)])
def test_bar_lengths_are_parsed(frozen, timeframe, seconds):
    mod, _ = frozen
    assert mod.ForexScrapeFade._bar_seconds(timeframe) == seconds
