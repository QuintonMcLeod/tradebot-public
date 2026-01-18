from __future__ import annotations

import logging
import math
import random
import re
from datetime import datetime, timedelta, timezone
from typing import List, Protocol, Set

import ccxt
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from .contracts import ContractResolutionError, build_contract
from .models import Candle, MarketSnapshot, OrderBook, OrderBookLevel, Ticker, TrendState
from .trend import infer_trend_from_swings
from .symbols import AssetClass, SYMBOL_METADATA


logger = logging.getLogger(__name__)


class MarketDataProvider(Protocol):
    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        ...

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        ...

    # Optional capabilities used by PairSelector (best-effort when implemented).
    def get_ticker(self, symbol: str) -> Ticker | None:  # pragma: no cover - protocol only
        ...

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:  # pragma: no cover - protocol only
        ...

    def get_market_definition(self, symbol: str) -> dict | None:  # pragma: no cover - protocol only
        ...


class MockMarketDataProvider:
    """Generates synthetic OHLCV candles to drive the simulation loop."""

    def __init__(self):
        self._series: dict[str, List[Candle]] = {}

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        series = self._series.setdefault(symbol, self._bootstrap_series(timeframe, limit))
        # extend if needed
        while len(series) < limit:
            series.append(self._next_candle(series[-1], timeframe))
        return series[-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        trend_htf = self._infer_trend(candles[-100:])
        trend_ltf = self._infer_trend(candles[-20:])
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=candles[-100:],
            ltf_candles=candles[-20:],
            htf_timeframe=timeframe,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        candles = self.get_latest_candles(symbol, timeframe="5m", limit=288)
        if not candles:
            return Ticker(symbol=symbol, bid=None, ask=None, last=None, volume_24h_quote_usd=None)
        last = candles[-1].close
        # Deterministic synthetic spread based on symbol hash (1-20 bps typical).
        spread_bps = (abs(hash(symbol)) % 20) + 1
        spread = last * (spread_bps / 10_000.0)
        bid = max(0.0, last - spread / 2)
        ask = last + spread / 2
        volume_usd = sum(c.volume * c.close for c in candles)
        return Ticker(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            volume_24h_quote_usd=volume_usd,
        )

    def get_market_definition(self, symbol: str) -> dict | None:
        return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        ticker = self.get_ticker(symbol)
        if not ticker or not ticker.last:
            return None
        mid = ticker.last
        base_size = max(1.0, (abs(hash(symbol)) % 50) + 10.0)
        bids = [OrderBookLevel(price=round(mid * (1 - 0.0005 * i), 4), size=base_size / (i + 1)) for i in range(depth)]
        asks = [OrderBookLevel(price=round(mid * (1 + 0.0005 * i), 4), size=base_size / (i + 1)) for i in range(depth)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.utcnow())

    def _bootstrap_series(self, timeframe: str, limit: int) -> List[Candle]:
        now = datetime.utcnow()
        start = now - timedelta(seconds=_timeframe_to_seconds(timeframe) * limit)
        price = 100.0
        candles: List[Candle] = []
        timestamp = start
        for _ in range(limit):
            candle = self._random_candle(timestamp, price)
            candles.append(candle)
            price = candle.close
            timestamp += timedelta(seconds=_timeframe_to_seconds(timeframe))
        return candles

    def _next_candle(self, last: Candle, timeframe: str) -> Candle:
        timestamp = last.timestamp + timedelta(seconds=_timeframe_to_seconds(timeframe))
        return self._random_candle(timestamp, last.close)

    def _random_candle(self, timestamp: datetime, anchor_price: float) -> Candle:
        drift = random.uniform(-0.3, 0.3)
        vol = random.uniform(0.5, 1.5)
        open_price = anchor_price + drift
        high = open_price + abs(random.gauss(0.5, 0.3))
        low = open_price - abs(random.gauss(0.5, 0.3))
        close = low + (high - low) * random.random()
        volume = abs(random.gauss(1000, 300)) * vol
        return Candle(
            timestamp=timestamp,
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=round(volume, 2),
        )

    def _infer_trend(self, candles: List[Candle]) -> TrendState:
        return infer_trend_from_swings(candles)


def _timeframe_to_seconds(tf: str) -> int:
    match = re.match(r"(\d+)([smhd])", tf.lower())
    if not match:
        return 60
    value, unit = match.groups()
    value_int = int(value)
    if unit == "s":
        return value_int
    if unit == "m":
        return value_int * 60
    if unit == "h":
        return value_int * 3600
    if unit == "d":
        return value_int * 86400
    return 60


class IbkrMarketDataProvider:
    """Pulls real market data from IBKR so the AI stops guessing in the dark."""

    def __init__(self, ib_client):
        self.ib = ib_client
        self._invalid_symbols: Set[str] = set()
        self._no_data_symbols: Set[str] = set()

    @retry(
        wait=wait_random_exponential(min=2, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, ConnectionRefusedError, OSError)),
        before_sleep=lambda retry_state: logger.warning(
            "[RETRY] Retrying IBKR connection for %s: attempt %s, waiting %.1fs...",
            retry_state.args[1],  # symbol
            retry_state.attempt_number,
            retry_state.next_action.sleep,
        ),
    )
    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        if symbol in self._invalid_symbols:
            raise ContractResolutionError(symbol)

        try:
            contract = build_contract(symbol)
        except ContractResolutionError as exc:
            self._invalid_symbols.add(symbol)
            logger.warning(
                "[STRUCTURE] %s contract build failed; skipping (%s)",
                symbol,
                exc,
            )
            logger.warning("[GUARD] Disabling %s for this run due to contract resolution failure", symbol)
            raise ContractResolutionError(symbol) from exc
        metadata = self._metadata_for_symbol(symbol)
        asset_class = metadata.asset_class if metadata else AssetClass.EQUITY
        bar_size = self._ib_bar_size(timeframe, asset_class)
        duration = self._ib_duration(timeframe, limit, asset_class)
        what_to_show = self._what_to_show_for_asset_class(asset_class)
        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=False,
                formatDate=1,
                keepUpToDate=False,
            )
        except Exception as exc:  # pragma: no cover
            if self._treat_as_no_signal(symbol, asset_class, exc):
                return []
            reason = self._classify_historical_error(symbol, exc)
            if reason:
                self._invalid_symbols.add(symbol)
                logger.warning("[STRUCTURE] %s %s; disabling for this run (%s)", symbol, reason, exc)
                raise ContractResolutionError(symbol) from exc
            raise
        candles: List[Candle] = []
        for b in bars[-limit:]:
            candles.append(
                Candle(
                    timestamp=b.date if isinstance(b.date, datetime) else datetime.strptime(b.date, "%Y%m%d %H:%M:%S"),
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(b.volume),
                )
            )
        return candles[-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        trend_htf = self._infer_trend(candles[-100:])
        trend_ltf = self._infer_trend(candles[-20:])
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=candles[-100:],
            ltf_candles=candles[-20:],
            htf_timeframe=timeframe,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        return None

    def get_market_definition(self, symbol: str) -> dict | None:
        return None

    def _metadata_for_symbol(self, symbol: str) -> SymbolMetadata | None:
        return SYMBOL_METADATA.get(symbol.upper())

    @staticmethod
    def _classify_historical_error(*args, **kwargs) -> str | None: # Temporarily modify for debugging
        symbol = "UNKNOWN_SYMBOL"
        exc = None

        if len(args) > 0:
            if isinstance(args[0], str):
                symbol = args[0]
            if len(args) > 1 and isinstance(args[1], Exception):
                exc = args[1]
            elif len(args) == 1 and isinstance(args[0], Exception):
                exc = args[0] # Handle case where only exception might be passed

        if 'symbol' in kwargs and isinstance(kwargs['symbol'], str):
            symbol = kwargs['symbol']
        if 'exc' in kwargs and isinstance(kwargs['exc'], Exception):
            exc = kwargs['exc']
        
        logger.error(
            "DEBUG: _classify_historical_error received args: %s, kwargs: %s (symbol: %s, exc: %s)",
            args, kwargs, symbol, exc
        )

        if exc is None:
            return "unknown error: exception object missing"

        try:
            text = str(exc)
        except Exception as e:
            logger.error(
                "Error processing exception in _classify_historical_error for symbol %s: %s (type: %s, repr: %s)",
                symbol,
                e,
                type(exc),
                repr(exc),
            )
            return f"failed to classify error due to internal error ({type(exc).__name__}: {repr(exc)})"

        # ... rest of the method as before ...


    def _treat_as_no_signal(self, symbol: str, asset_class: AssetClass, exc: Exception) -> bool:
        text = str(exc)
        if asset_class == AssetClass.EQUITY and "HMDS query returned no data" in text:
            if symbol not in self._no_data_symbols:
                logger.info(
                    "[STRUCTURE] %s: no historical data in current window (treating as no signal this cycle)",
                    symbol,
                )
                self._no_data_symbols.add(symbol)
            return True
        return False


    @staticmethod
    def _is_invalid_destination_error(exc: Exception) -> bool:
        text = str(exc)
        return "exchange selected is Invalid" in text

    def _ib_bar_size(self, tf: str, asset_class: AssetClass) -> str:
        mapping = {
            "1m": "1 min",
            "5m": "5 mins",
            "15m": "15 mins",
            "1h": "1 hour",
        }
        if asset_class == AssetClass.FOREX:
            return "5 mins"
        return mapping.get(tf.lower(), "5 mins")

    def _ib_duration(self, tf: str, limit: int, asset_class: AssetClass) -> str:
        seconds = _timeframe_to_seconds(tf) * max(limit, 50)
        if asset_class == AssetClass.FOREX:
            return "2 D"
        if asset_class == AssetClass.CRYPTO:
            return "3 D"
        if seconds <= 60 * 60 * 24:
            return "1 D"
        if seconds <= 60 * 60 * 24 * 7:
            return "1 W"
        return "2 W"

    def _what_to_show_for_asset_class(self, asset_class: AssetClass) -> str:
        if asset_class == AssetClass.CRYPTO:
            return "AGGTRADES"
        if asset_class == AssetClass.FOREX:
            return "MIDPOINT"
        return "TRADES"

    def _infer_trend(self, candles: List[Candle]) -> TrendState:
        return infer_trend_from_swings(candles)


class CCXTMarketDataProvider:
    """Historical and live market data via CCXT (authenticated).
    
    This is the modern replacement for CoinbaseMarketDataProvider, supporting 
    Advanced Trade V3 and Nano Futures.
    """

    def __init__(self, exchange: ccxt.Exchange, symbol_map: dict[str, str] | None = None):
        self._exchange = exchange
        self._symbol_map = symbol_map or {}

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        sym = self._symbol_map.get(symbol.upper(), symbol)
        # Normalize timeframe for CCXT (1m, 5m, 1h, etc.)
        tf = timeframe.lower().strip()
        # [ANTIGRAVITY FIX] Map verbose GUI timeframes to CCXT short codes
        map_tf = {
            "1 min": "1m", "1 mins": "1m",
            "5 min": "5m", "5 mins": "5m",
            "15 min": "15m", "15 mins": "15m",
            "30 min": "30m", "30 mins": "30m",
            "1 hour": "1h", "1 hours": "1h",
            "4 hour": "4h", "4 hours": "4h",
            "1 day": "1d", "1 days": "1d",
        }
        tf = map_tf.get(tf, tf)
        
        # CCXT documentation says fetch_ohlcv(symbol, timeframe, since, limit)
        # We don't use 'since' for 'latest' candles unless needed.
        try:
            ohlcv = self._exchange.fetch_ohlcv(sym, tf, limit=limit)
        except Exception as e:
            logger.warning(f"[CCXT-DATA] Snapshot fetch failed for {symbol} ({sym}): {e}")
            return []

        candles: List[Candle] = []
        for row in ohlcv:
            # row: [timestamp, open, high, low, close, volume]
            ts = datetime.fromtimestamp(row[0] / 1000.0, tz=timezone.utc)
            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles[-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        # Use HTF-emulation or just 200 candles for now
        trend_htf = self._infer_trend(candles[-100:])
        trend_ltf = self._infer_trend(candles[-20:])
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=candles[-100:],
            ltf_candles=candles[-20:],
            htf_timeframe=timeframe,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        sym = self._symbol_map.get(symbol.upper(), symbol)
        try:
            data = self._exchange.fetch_ticker(sym)
            return Ticker(
                symbol=symbol,
                bid=float(data["bid"]) if data.get("bid") is not None else None,
                ask=float(data["ask"]) if data.get("ask") is not None else None,
                last=float(data["last"]) if data.get("last") is not None else None,
                volume_24h_quote_usd=float(data["quoteVolume"]) if data.get("quoteVolume") is not None else None,
            )
        except Exception as e:
            logger.warning(f"[CCXT-DATA] Ticker fetch failed for {symbol}: {e}")
            try:
                ohlcv = self._exchange.fetch_ohlcv(sym, "1m", limit=1)
                if not ohlcv or len(ohlcv) == 0:
                    logger.debug(f"[CCXT-DATA] OHLCV fallback returned empty for {sym}")
                    return None
                
                candle = ohlcv[-1]
                if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                    logger.debug(f"[CCXT-DATA] OHLCV fallback returned malformed candle for {sym}: {candle}")
                    return None
                    
                last = float(candle[4])
                return Ticker(
                    symbol=symbol,
                    bid=None,
                    ask=None,
                    last=last,
                    volume_24h_quote_usd=None,
                )
            except Exception as ohlcv_exc:
                logger.warning(f"[CCXT-DATA] Ticker fallback failed for {symbol}: {ohlcv_exc}")
                return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        sym = self._symbol_map.get(symbol.upper(), symbol)
        try:
            data = self._exchange.fetch_order_book(sym, limit=depth)
            bids = [OrderBookLevel(price=float(r[0]), size=float(r[1])) for r in data.get("bids", [])]
            asks = [OrderBookLevel(price=float(r[0]), size=float(r[1])) for r in data.get("asks", [])]
            return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.now(timezone.utc))
        except Exception as e:
            logger.warning(f"[CCXT-DATA] Book fetch failed for {symbol}: {e}")
            return None

    def _infer_trend(self, candles: List[Candle]) -> TrendState:
        return infer_trend_from_swings(candles)

    def get_market_definition(self, symbol: str) -> dict | None:
        sym = self._symbol_map.get(symbol.upper(), symbol)
        try:
            if not self._exchange.markets:
                self._exchange.load_markets()
            if sym in self._exchange.markets:
                return self._exchange.markets[sym]
        except Exception as e:
            logger.warning(f"[CCXT-DATA] Failed to get market definition for {symbol}: {e}")
        return None
