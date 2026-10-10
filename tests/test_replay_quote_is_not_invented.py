"""The replay must not hand the strategy a quote it made up.

WHY THIS TEST EXISTS. `ReplayMarketProvider.get_ticker` used to return a fixed
synthetic quote, `spread = mid * 0.00003`, for every symbol on every bar. The engine
passes that difference to the strategy as `gates["current_spread"]`, and the strategy
reads it as the toll the entry will pay. The replay's data files hold no spread field,
so the number was not a quote: three basis points works out at 0.17 to 0.63 pips,
where the measured round trip for the same pairs is 1.3 to 9.8 pips. It was also below
the 1.9-pip entry ceiling for every symbol in the profile, which made the cost ceiling
shipped on 2026-10-10 (decision 28) inert in the replay, and made the entry-toll
readout print a fabricated number.

Three cases are pinned here: the replay reports no spread, a zero reading falls back to
the measured table, and a pair that is in neither is refused rather than admitted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradebot_sci.broker import paper_broker
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.market.replay_provider import ReplayMarketProvider
from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade

STRATEGY_LOGGER = "tradebot_sci.strategy.variants.forex_scrape_fade"


def _candle(at: datetime, close: float, spread: float = 0.0002) -> Candle:
    return Candle(timestamp=at, open=close, high=close + spread,
                  low=close - spread, close=close, volume=100.0)


def _break_snapshot(symbol: str = "EURUSD", hour_utc: int = 20) -> MarketSnapshot:
    """A snapshot that clears every non-cost gate: a fresh 2-pip break at hour 20.

    Twenty-four flat bars at 1.1000 (high 1.1002, low 1.0998), then a bar closing at
    1.09960, which is 2.0 pips below the prior range's low. The strategy reads the hour
    and the range off its own candles, so this is enough to reach the cost guards.
    """
    last_at = datetime(2026, 10, 12, hour_utc, 30, tzinfo=timezone.utc)
    first_at = last_at - timedelta(minutes=5 * 24)
    candles = [_candle(first_at + timedelta(minutes=5 * i), 1.1000) for i in range(24)]
    candles.append(_candle(last_at, 1.09960))
    return MarketSnapshot(
        symbol=symbol,
        timeframe="5m",
        candles=candles,
        trend_htf=TrendState(direction="long", strength=0.5),
        trend_ltf=TrendState(direction="long", strength=0.5),
        ltf_candles=candles,
    )


def test_the_replay_reports_no_invented_spread():
    """The ticker quotes no spread, so nothing downstream can read a made-up cost."""
    provider = ReplayMarketProvider(data_dir=Path("/nonexistent"), symbols=["EURUSD"])
    at = datetime(2026, 2, 18, 20, 0, tzinfo=timezone.utc)
    provider._candles = {"EURUSD": {"5m": [_candle(at, 1.09960)]}}
    provider._warmup_by_sym = {"EURUSD": 0}
    provider._cursor = 1

    ticker = provider.get_ticker("EURUSD")

    assert ticker is not None
    assert ticker.bid == ticker.ask == ticker.last, (
        "the replay is quoting a spread it cannot know; the data carries none"
    )


def test_a_zero_quote_falls_back_to_the_measured_table(monkeypatch):
    """Price comes from the table, which is the number the research charged."""
    monkeypatch.setattr(paper_broker, "_measured_spread_bps", lambda symbol: 1.44)
    strategy = ForexScrapeFade()

    # 1.44 bps of 1.10 is 1.58 pips, under the strategy's own 1.9-pip ceiling.
    decision = strategy.check_entry_signal(_break_snapshot(), gates={"current_spread": 0.0})

    assert decision is not None, "an entry priced under the ceiling was refused anyway"


def test_a_pair_with_neither_quote_nor_table_is_refused(monkeypatch, caplog):
    """Unpriced is not cheap. EURNZD is absent from the table and has no live quote."""
    import logging

    monkeypatch.setattr(paper_broker, "_measured_spread_bps", lambda symbol: None)
    strategy = ForexScrapeFade()

    with caplog.at_level(logging.INFO, logger=STRATEGY_LOGGER):
        decision = strategy.check_entry_signal(
            _break_snapshot("EURNZD"), gates={"current_spread": 0.0})

    assert decision is None
    assert any("entry cost unknown" in r.getMessage() for r in caplog.records), (
        "the entry was admitted without any price for its cost"
    )


def test_a_real_quote_above_the_ceiling_is_still_refused(monkeypatch):
    """The live path is unchanged: a wide quote is refused on the entry bar's own spread."""
    monkeypatch.setattr(paper_broker, "_measured_spread_bps", lambda symbol: 1.44)
    strategy = ForexScrapeFade()

    decision = strategy.check_entry_signal(
        _break_snapshot(), gates={"current_spread": 3.0 * 0.0001})

    assert decision is None
