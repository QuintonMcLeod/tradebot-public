from __future__ import annotations

import logging
import requests
import time
from typing import List

from tradebot_sci.market.models import Candle, MarketSnapshot, OrderBook, Ticker, Ask, Bid
from tradebot_sci.market.providers import MarketDataProvider

logger = logging.getLogger(__name__)

class PaxosMarketDataProvider(MarketDataProvider):
    """Market Data Provider using Paxos Public Data API."""

    BASE_URL_PROD = "https://api.paxos.com/v2"
    BASE_URL_SANDBOX = "https://api.sandbox.paxos.com/v2"

    def __init__(self, environment: str = "sandbox"):
        self.base_url = self.BASE_URL_PROD if environment.lower() == "production" else self.BASE_URL_SANDBOX

    def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[PAXOS-DATA] Failed {endpoint}: {e}")
            raise

    def get_ticker(self, symbol: str) -> Ticker | None:
        """Fetches ticker for a symbol (e.g. BTCUSD)."""
        # GET /markets/{market}/ticker
        # Response: { "best_bid": "...", "best_ask": "...", "last_execution": "..." }
        try:
            mkt = symbol.upper()
            data = self._get(f"/markets/{mkt}/ticker")
            
            # Map fields
            bid = float(data.get("best_bid", 0))
            ask = float(data.get("best_ask", 0))
            last = float(data.get("last_execution", {}).get("price", 0))
            if last == 0: last = (bid + ask) / 2
            
            return Ticker(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=last,
                time=time.time()
            )
        except Exception:
            return None

    def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook | None:
        try:
            mkt = symbol.upper()
            data = self._get(f"/markets/{mkt}/orderbook")
            
            bids = [Bid(price=float(p), size=float(s)) for p, s in data.get("bids", [])[:depth]]
            asks = [Ask(price=float(p), size=float(s)) for p, s in data.get("asks", [])[:depth]]
            
            return OrderBook(symbol=symbol, bids=bids, asks=asks, time=time.time())
        except Exception:
            return None

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        # Paxos API V2 doesn't have a public OHLCV endpoint in standard docs?
        # Usually they provide Ticker/Trades.
        # Fallback: We might not support historical candles natively without paid feed or recording.
        # For now return empty or implement basic trade aggregation if needed.
        # Logger warning.
        logger.warning(f"[PAXOS-DATA] Historical candles not supported by public API for {symbol}")
        return []

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        tick = self.get_ticker(symbol)
        if not tick:
            return None
            
        # Resolve HTF/XTF timeframe from config
        try:
            from tradebot_sci.config.loader import load_config_json
            config = load_config_json()
        except ImportError:
            from tradebot_sci import paths as _paths
            import json
            try:
                with open(_paths.CONFIG_FILE, "r") as f:
                    config = json.load(f)
            except Exception:
                config = {}
        
        active_prof = config.get("active_profile", "primary")
        prof_data = config.get("profiles", {}).get(active_prof, {})
        htf_setting = prof_data.get("htf_timeframe") or config.get("global", {}).get("htf_timeframe") or "4h"
        xtf_setting = prof_data.get("xtf_timeframe") or config.get("global", {}).get("xtf_timeframe") or "1m"

        _neutral = TrendState(direction="neutral", strength=0.0)
        
        # Create a synthetic candle from ticker? OR just snapshot
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=[],
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=[],
            ltf_candles=[],
            micro_candles=[],
            htf_timeframe=htf_setting,
            ltf_timeframe=timeframe,
            micro_timeframe=xtf_setting,
        )

    def close(self) -> None:
        pass
