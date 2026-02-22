from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from tradebot_sci.market.models import Candle, MarketSnapshot, OrderBook, OrderBookLevel, Ticker, TrendState

logger = logging.getLogger(__name__)




def _timeframe_to_granularity_seconds(timeframe: str) -> int:
    tf = timeframe.lower().strip()
    seconds = 300
    if tf.endswith("m"):
        seconds = int(tf[:-1]) * 60
    elif tf.endswith("h"):
        seconds = int(tf[:-1]) * 3600
    elif tf.endswith("d"):
        seconds = int(tf[:-1]) * 86400
    
    # Coinbase supported granularities: 60, 300, 900, 3600, 21600, 86400
    supported = [60, 300, 900, 3600, 21600, 86400]
    if seconds in supported:
        return seconds

    # Map 4h (14400) to 6h (21600) silently
    if seconds == 14400:
        return 21600
        
    # Snap to nearest
    closest = min(supported, key=lambda x: abs(x - seconds))
    logger.debug(
        "[COINBASE] Unsupported granularity %ss (%s). Snapping to closest supported: %ss", 
        seconds, timeframe, closest
    )
    return closest


class CoinbaseMarketDataProvider:
    """Public market data via Coinbase Exchange REST API (no auth).

    Used for `market.exchange_provider=alternative` when you want real crypto candles/spreads
    without wiring execution yet.
    """

    def __init__(self, base_url: str = "https://api.exchange.coinbase.com", timeout_seconds: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "tradebot-sci-enterprise/coinbase"},
        )

    def close(self) -> None:
        self._client.close()

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        product = self._product_id(symbol)
        gran = _timeframe_to_granularity_seconds(timeframe)
        # Coinbase has max 300 candles per request; keep it simple for now.
        limit = min(limit, 300)
        end = datetime.now(UTC)
        start = end - timedelta(seconds=gran * limit)
        resp = self._client.get(
            f"/products/{product}/candles",
            params={
                "granularity": gran,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        resp.raise_for_status()
        rows = resp.json() or []
        candles: list[Candle] = []
        # API returns newest-first: [time, low, high, open, close, volume]
        for row in reversed(rows):
            if not isinstance(row, list) or len(row) < 6:
                continue
            ts = datetime.fromtimestamp(float(row[0]), tz=UTC)
            candles.append(
                Candle(
                    timestamp=ts,
                    low=float(row[1]),
                    high=float(row[2]),
                    open=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles[-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        # Neutral defaults — engine.py's Trend Detection sets direction
        _neutral = TrendState(direction="neutral", strength=0.0)
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=candles[-100:],
            ltf_candles=candles[-20:],
            htf_timeframe=timeframe,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        product = self._product_id(symbol)
        resp = self._client.get(f"/products/{product}/ticker")
        resp.raise_for_status()
        data = resp.json() or {}
        try:
            bid = float(data["bid"]) if data.get("bid") is not None else None
            ask = float(data["ask"]) if data.get("ask") is not None else None
            last = float(data["price"]) if data.get("price") is not None else None
            volume = float(data["volume"]) if data.get("volume") is not None else None
        except (TypeError, ValueError, KeyError):
            return None
        # Coinbase's `volume` is base volume; approximate quote volume.
        vol_quote = (volume * last) if (volume is not None and last is not None) else None
        return Ticker(symbol=symbol, bid=bid, ask=ask, last=last, volume_24h_quote_usd=vol_quote)

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        product = self._product_id(symbol)
        resp = self._client.get(f"/products/{product}/book", params={"level": 2})
        resp.raise_for_status()
        data = resp.json() or {}
        try:
            bids_raw = data.get("bids") or []
            asks_raw = data.get("asks") or []
        except AttributeError:
            return None
        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []
        for row in bids_raw[:depth]:
            try:
                bids.append(OrderBookLevel(price=float(row[0]), size=float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
        for row in asks_raw[:depth]:
            try:
                asks.append(OrderBookLevel(price=float(row[0]), size=float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.now(UTC))

    @staticmethod
    def _infer_trend(candles: list[Candle]) -> TrendState:
        """Legacy stub — returns neutral. Direction set by engine.py."""
        return TrendState(direction="neutral", strength=0.0)

    @staticmethod
    def _product_id(symbol: str) -> str:
        """Map a symbol (e.g. BTCUSD) to a Coinbase product ID (e.g. BTC-USD)."""
        key = symbol.upper().replace("-", "").replace("/", "")
        
        # Common Coinbase products don't always follow the 3-char quote rule in our heuristic.
        # But for BASEQUOTE -> BASE-QUOTE, we try common ones.
        for q in ["USDT", "USDC", "USD", "EUR", "GBP"]:
            if key.endswith(q) and len(key) > len(q):
                return f"{key[:-len(q)]}-{q}"
        
        # If it already has a hyphen, use it
        if "-" in symbol:
            return symbol.upper()
            
        # If no common quote found and it's 6+ chars, assume 3-char quote
        if len(key) >= 6:
            return f"{key[:-3]}-{key[-3:]}"
            
        # Otherwise, just return as is (Coinbase will likely 404, but it's better than -GLD)
        return key
