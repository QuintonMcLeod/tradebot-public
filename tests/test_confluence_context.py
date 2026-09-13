from datetime import datetime, timedelta, timezone

from tradebot_sci.confluence.context import build_confluence
from tradebot_sci.market.models import Candle, OrderBook, OrderBookLevel, Ticker


class StubProvider:
    def get_ticker(self, symbol: str) -> Ticker | None:
        return Ticker(symbol=symbol, bid=99.9, ask=100.1, last=100.0, volume_24h_quote_usd=1_000_000.0)

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        levels = [OrderBookLevel(price=100.0, size=1000.0) for _ in range(depth)]
        return OrderBook(symbol=symbol, bids=levels, asks=levels, timestamp=datetime.now(timezone.utc))


class NoTickerProvider:
    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        levels = [OrderBookLevel(price=100.0, size=1000.0) for _ in range(depth)]
        return OrderBook(symbol=symbol, bids=levels, asks=levels, timestamp=datetime.now(timezone.utc))


def _candles(n: int, *, start: datetime) -> list[Candle]:
    candles: list[Candle] = []
    price = 100.0
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        candles.append(Candle(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price + 0.2, volume=1000))
        price += 0.1
    return candles


def test_confluence_vix_fail_safe_caps_equity(monkeypatch):
    monkeypatch.setenv("VIX_FAIL_SAFE", "true")
    monkeypatch.setenv("VIX_RISK_CAP", "0.03")
    provider = StubProvider()
    start = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)  # Monday 10:00 ET
    c = _candles(25, start=start)

    conf = build_confluence(provider, "SPY", c, include_external=False).data
    assert conf["asset_class"] == "equity"
    assert conf["risk_cap_pct"] <= 0.03


def test_confluence_does_not_require_vix_for_crypto(monkeypatch):
    monkeypatch.setenv("VIX_FAIL_SAFE", "true")
    monkeypatch.setenv("VIX_RISK_CAP", "0.03")
    provider = StubProvider()
    start = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    c = _candles(25, start=start)

    conf = build_confluence(provider, "BTCUSD", c, include_external=False).data
    assert conf["asset_class"] == "crypto"
    assert conf["risk_cap_pct"] >= 0.02


def test_confluence_crypto_friction_fail_safe_when_no_ticker(monkeypatch):
    monkeypatch.setenv("FRICTION_FAIL_SAFE", "true")
    monkeypatch.setenv("FRICTION_RISK_CAP", "0.02")
    provider = NoTickerProvider()
    start = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    c = _candles(25, start=start)

    conf = build_confluence(provider, "BTCUSD", c, include_external=False).data
    assert conf["asset_class"] == "crypto"
    assert conf["risk_cap_pct"] == 0.02
