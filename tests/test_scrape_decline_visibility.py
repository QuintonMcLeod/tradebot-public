"""The scrape-fade strategy must say why it declined, and stay quiet outside its hour.

WHY THIS TEST EXISTS. The forward paper test was unreadable for weeks: 19,265 HOLD
lines in the journal carried the engine's generic fallback text and not one of them
named a gate, because 5 of this strategy's 7 decline paths returned None silently and
the other 2 logged at DEBUG, which the journal does not keep. A census on 2026-10-10
could not tell "outside its entry hour" from "evaluated the setup and refused it".

So these tests pin the two halves of the fix: a decline inside the entry hour is
reported at INFO with its reason, and the out-of-window decline stays silent, because
logging that one would add roughly 300 pointless lines a day.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade

STRATEGY_LOGGER = "tradebot_sci.strategy.variants.forex_scrape_fade"


def _snapshot(closes: list[float], hour_utc: int, symbol: str = "EURUSD") -> MarketSnapshot:
    """A snapshot whose LAST candle sits at `hour_utc`:30 UTC.

    The strategy reads the hour off its most recent candle, so the timestamp of the
    final candle is what selects in-window from out-of-window. The earlier candles
    are walked backwards from it, which matters: building forward from the hour
    pushes the last candle past the window and quietly tests the wrong case.
    """
    last_at = datetime(2026, 10, 12, hour_utc, 30, tzinfo=timezone.utc)
    first_at = last_at - timedelta(minutes=5 * (len(closes) - 1))
    candles = [
        Candle(
            timestamp=first_at + timedelta(minutes=5 * i),
            open=c,
            high=c + 0.0002,
            low=c - 0.0002,
            close=c,
            volume=100.0,
        )
        for i, c in enumerate(closes)
    ]
    return MarketSnapshot(
        symbol=symbol,
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="long", strength=0.5),
        trend_ltf=TrendState(direction="long", strength=0.5),
        ltf_candles=candles,
    )


@pytest.fixture()
def strategy() -> ForexScrapeFade:
    return ForexScrapeFade()


def _info_messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]


def test_inside_window_decline_is_reported_at_info(caplog, strategy):
    """Inside the hour, a flat range must produce a named decline, not silence."""
    flat = [1.1000] * 25
    snapshot = _snapshot(flat, hour_utc=20)

    with caplog.at_level(logging.INFO, logger=STRATEGY_LOGGER):
        signal = strategy.check_entry_signal(snapshot, gates={})

    assert signal is None
    messages = _info_messages(caplog)
    assert messages, "a decline inside the entry hour produced no INFO line"
    assert any("declined" in m and "no fresh break" in m for m in messages), messages


def test_out_of_window_decline_stays_quiet(caplog, strategy):
    """Outside the hour every symbol declines every cycle, so it must not log."""
    flat = [1.1000] * 25
    snapshot = _snapshot(flat, hour_utc=9)

    with caplog.at_level(logging.INFO, logger=STRATEGY_LOGGER):
        signal = strategy.check_entry_signal(snapshot, gates={})

    assert signal is None
    assert _info_messages(caplog) == [], "the out-of-window decline logged at INFO"


def test_score_signal_names_the_window_state(caplog, strategy):
    """The engine drops this string into the HOLD line, so it must say which case."""
    inside = strategy.score_signal(_snapshot([1.1] * 25, hour_utc=20), {})
    outside = strategy.score_signal(_snapshot([1.1] * 25, hour_utc=9), {})

    assert inside[2] == "ScrapeFade: inside entry window"
    assert outside[2] == "ScrapeFade: outside entry window"


def test_decline_returns_none_so_callers_are_unchanged(strategy):
    """The helper is additive: the engine still sees the same None it always did."""
    snapshot = _snapshot([1.1] * 25, hour_utc=20)
    assert strategy._decline(snapshot, "anything") is None


def test_synthetic_override_decline_is_reported(caplog, strategy):
    """A synthetic override is a refusal, and it was the other silent path."""
    snapshot = _snapshot([1.1] * 25, hour_utc=20)

    with caplog.at_level(logging.INFO, logger=STRATEGY_LOGGER):
        signal = strategy.check_entry_signal(snapshot, gates={"is_synthetic_override": True})

    assert signal is None
    assert any("synthetic override" in m for m in _info_messages(caplog))
