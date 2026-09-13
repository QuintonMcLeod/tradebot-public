from __future__ import annotations

from datetime import datetime, timezone

from helpers import make_test_profile
from tradebot_sci.market.models import OrderBook, OrderBookLevel, Ticker
from tradebot_sci.runtime.pair_selector import PairSelector


class FixedProvider:
    def __init__(self, tickers: dict[str, Ticker], books: dict[str, OrderBook | None]):
        self.tickers = tickers
        self.books = books
        self.ticker_calls: dict[str, int] = {}

    def get_ticker(self, symbol: str) -> Ticker | None:
        self.ticker_calls[symbol] = self.ticker_calls.get(symbol, 0) + 1
        return self.tickers.get(symbol)

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return self.books.get(symbol)


def _profile(**overrides):
    base = {
        "candle_timeframe": "5m",
        "market_poll_interval_seconds": 10,
        "ai_decision_interval_seconds": 60,
        "crypto_only": True,
        "pair_selector_enabled": True,
        "pair_selector_refresh_seconds": 300,
        "pair_selector_min_volume_usd_24h": 1_000_000.0,
        "pair_selector_max_spread_bps": 25.0,
        "pair_selector_min_depth_usd": 50_000.0,
        "pair_selector_max_pairs": 3,
    }
    base.update(overrides)
    return make_test_profile(**base)


def test_pair_selector_filters_by_volume_spread_and_depth():
    now = datetime.now(timezone.utc)
    profile = _profile()

    good_ticker = Ticker(symbol="BTCUSD", bid=100.0, ask=100.1, last=100.05, volume_24h_quote_usd=10_000_000.0)
    low_vol = Ticker(symbol="ETHUSD", bid=100.0, ask=100.1, last=100.05, volume_24h_quote_usd=10.0)
    wide_spread = Ticker(symbol="SOLUSD", bid=100.0, ask=101.0, last=100.5, volume_24h_quote_usd=10_000_000.0)

    deep_book = OrderBook(
        symbol="BTCUSD",
        bids=[OrderBookLevel(price=100.0, size=400.0)],
        asks=[OrderBookLevel(price=100.1, size=400.0)],
        timestamp=now,
    )
    shallow_book = OrderBook(
        symbol="SOLUSD",
        bids=[OrderBookLevel(price=100.0, size=1.0)],
        asks=[OrderBookLevel(price=101.0, size=1.0)],
        timestamp=now,
    )

    provider = FixedProvider(
        tickers={"BTCUSD": good_ticker, "ETHUSD": low_vol, "SOLUSD": wide_spread},
        books={"BTCUSD": deep_book, "ETHUSD": deep_book, "SOLUSD": shallow_book},
    )
    selector = PairSelector(profile)
    result = selector.select(provider, ["BTCUSD", "ETHUSD", "SOLUSD"], now)
    assert result.selected == ["BTCUSD"]


def test_pair_selector_caches_within_refresh_window():
    now = datetime.now(timezone.utc)
    profile = _profile(pair_selector_refresh_seconds=999)
    ticker = Ticker(symbol="BTCUSD", bid=100.0, ask=100.1, last=100.05, volume_24h_quote_usd=10_000_000.0)
    book = OrderBook(
        symbol="BTCUSD",
        bids=[OrderBookLevel(price=100.0, size=400.0)],
        asks=[OrderBookLevel(price=100.1, size=400.0)],
        timestamp=now,
    )
    provider = FixedProvider(tickers={"BTCUSD": ticker}, books={"BTCUSD": book})
    selector = PairSelector(profile)
    first = selector.select(provider, ["BTCUSD"], now)
    second = selector.select(provider, ["BTCUSD"], now)
    assert first.selected == second.selected
    assert provider.ticker_calls["BTCUSD"] == 2

