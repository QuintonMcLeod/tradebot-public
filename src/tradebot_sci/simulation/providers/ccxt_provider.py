from __future__ import annotations

import logging
import math
import time
import json
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import ccxt  # type: ignore

from tradebot_sci.market.models import Candle, MarketSnapshot, Ticker, TrendState
from tradebot_sci.config.models import Settings
# Legacy infer_trend_from_swings removed — direction set by trend_consensus.py
from tradebot_sci.simulation.utils import resample_candles, timeframe_to_seconds

logger = logging.getLogger(__name__)


class CCXTHistoricalDataProvider:
    """Provides market data from historical candles via CCXT (Coinbase) for backtesting."""

    def __init__(self, settings: Settings, exchange_id: str = "coinbase"):
        self.settings = settings
        self.exchange_id = exchange_id
        # Initialize exchange without API keys just for public data if possible,
        # but we use keys from env if provided for higher limits/private data if needed.
        # For backtesting, public data is usually sufficient.
        self.exchange = getattr(ccxt, exchange_id)({
            'enableRateLimit': True,
        })
        self.exchange.load_markets()
        self._cache: Dict[str, List[Candle]] = {}
        
        # Approximate spreads for simulation (e.g. 0.05% to 0.1%)
        # Coinbase fees are roughly 0.6% taker, 0.4% maker for low tier
        self.simulated_spread_bps = 10  # 0.1% spread cost embedded in ticker

    def fetch_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        file_path: str | None = None,
    ) -> List[Candle]:
        """Fetch historical candles from CCXT for the specified date range."""
        cache_key = f"{symbol}:{timeframe}:{start_date.isoformat()}:{end_date.isoformat()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Local File Loading Support
        if file_path and os.path.exists(file_path):
            logger.info(f"[BACKTEST] Loading candles for {symbol} from local file: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    candles = []
                    for c in raw_data:
                        # Handle multiple timestamp formats
                        ts_str = c["timestamp"]
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except ValueError:
                            ts = datetime.fromisoformat(ts_str)
                            
                        if start_date <= ts <= end_date:
                            candles.append(Candle(
                                timestamp=ts,
                                open=float(c["open"]),
                                high=float(c["high"]),
                                low=float(c["low"]),
                                close=float(c["close"]),
                                volume=float(c.get("volume", 0.0)),
                            ))
                    
                    self._cache[cache_key] = candles
                    logger.info(f"[BACKTEST] Loaded {len(candles)} candles from file.")
                    return candles
            except Exception as e:
                logger.error(f"[BACKTEST] Failed to load candles from file {file_path}: {e}")
                return []

        # Map symbol to CCXT format if needed (e.g. BTCUSD -> BTC/USD)
        ccxt_symbol = symbol

        try:
            timeframe_seconds = timeframe_to_seconds(timeframe)
            if timeframe_seconds == 0:
                logger.warning(f"Invalid timeframe: {timeframe}")
                return []
                
            # Disk Cache to prevent API Rate Limits
            cache_dir = os.path.join("data", "cache", "backtest")
            os.makedirs(cache_dir, exist_ok=True)
            
            # Create a unique filename for this query
            query_hash = hashlib.md5(f"{symbol}_{timeframe}_{start_date}_{end_date}".encode()).hexdigest()
            cache_file = os.path.join(cache_dir, f"{query_hash}.json")
            
            if os.path.exists(cache_file):
                logger.info(f"[BACKTEST] Loading cached data for {symbol} ({cache_file})")
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                        return [
                            Candle(
                                timestamp=datetime.fromisoformat(c["ts"]),
                                open=c["o"],
                                high=c["h"],
                                low=c["l"],
                                close=c["c"],
                                volume=c["v"]
                            ) for c in raw_data
                        ]
                except Exception as e:
                    logger.warning(f"[BACKTEST] Failed to read cache: {e}")

            # Calculate timeframe in milliseconds
            timeframe_ms = timeframe_seconds * 1000
            start_ts = int(start_date.timestamp() * 1000)
            end_ts = int(end_date.timestamp() * 1000)
            
            all_ohlcv = []
            since = start_ts
            
            logger.info(f"[BACKTEST] Fetching {ccxt_symbol} {timeframe} candles from {start_date} to {end_date}...")
            
            while since < end_ts:
                # Fetch candles in chunks
                limit = 1000  # Coinbase specific limit per request
                ohlcv = self.exchange.fetch_ohlcv(
                    ccxt_symbol, timeframe, since=since, limit=limit
                )
                
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                
                # Update since to last candle timestamp + 1 timeframe
                last_ts = ohlcv[-1][0]
                since = last_ts + (timeframe_seconds * 1000)
                
                # Safety check if we passed end_date
                if last_ts >= end_ts:
                    break
                    
                # Small sleep to respect rate limits if not handled by library
                # ccxt enableRateLimit handles this generally, but failures occur on heavily loaded backtests
                time.sleep(1.0)

            # Filter duplicates and range
            candles = []
            seen_ts = set()
            
            for c in all_ohlcv:
                ts_ms = c[0]
                if ts_ms < int(start_date.timestamp() * 1000) or ts_ms > end_ts:
                    continue
                if ts_ms in seen_ts:
                    continue
                seen_ts.add(ts_ms)
                
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                candles.append(Candle(
                    timestamp=dt,
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]),
                ))
            
            # Write to Disk Cache
            if candles:
                try:
                    cache_data = [
                        {
                            "ts": c.timestamp.isoformat(),
                            "o": c.open,
                            "h": c.high,
                            "l": c.low,
                            "c": c.close,
                            "v": c.volume
                        } for c in candles
                    ]
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f)
                    logger.info(f"[BACKTEST] Cached {len(candles)} candles to {cache_file}")
                except Exception as e:
                    logger.warning(f"[BACKTEST] Failed to write cache: {e}")

            self._cache[cache_key] = candles
            logger.info(f"[BACKTEST] Fetched {len(candles)} candles for {symbol}")
            return candles

        except Exception as e:
            logger.error(f"[BACKTEST] Error fetching historical data for {symbol}: {e}")
            return []

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        """Get the most recent N candles from the cache (used by strategy engine)."""
        cache_key = f"{symbol}:{timeframe}_current"
        if cache_key not in self._cache:
            return []
        return self._cache[cache_key][-limit:]

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        """Get market snapshot from cached candles."""
        profile = self.settings.get_active_profile()
        base_seconds = timeframe_to_seconds(timeframe)
        htf_seconds = timeframe_to_seconds(profile.htf_timeframe)
        ltf_seconds = timeframe_to_seconds(profile.ltf_timeframe or timeframe)

        htf_window = profile.trend_window
        ltf_window = profile.ltf_trend_window or htf_window
        required_seconds = max(htf_window * htf_seconds, ltf_window * ltf_seconds)
        base_limit = max(200, math.ceil(required_seconds / base_seconds) + 10)

        candles = self.get_latest_candles(symbol, timeframe, limit=base_limit)

        # Resampel candles for trend detection
        htf_candles = (
            resample_candles(candles, htf_seconds) if htf_seconds != base_seconds else candles
        )
        ltf_candles = (
            resample_candles(candles, ltf_seconds) if ltf_seconds != base_seconds else candles
        )
        
        # Micro candles cannot be resampled down from base timeframe, fetch directly from cache
        try:
            micro_candles = self.get_latest_candles(symbol, profile.xtf_timeframe, limit=10)
        except Exception:
            micro_candles = []

        # Neutral defaults — engine.py's Trend Detection sets direction
        _neutral = TrendState(direction="neutral", strength=0.0)

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles[-htf_window:] if len(htf_candles) >= htf_window else htf_candles,
            ltf_candles=ltf_candles[-ltf_window:] if len(ltf_candles) >= ltf_window else ltf_candles,
            micro_candles=micro_candles,
            htf_timeframe=profile.htf_timeframe,
            ltf_timeframe=profile.ltf_timeframe or timeframe,
            micro_timeframe=profile.xtf_timeframe,
        )
    
    # Optional capabilities used by PairSelector
    def get_ticker(self, symbol: str) -> Optional[Ticker]:
        """Provide a simulated ticker based on the last candle close."""
        # This is needed because some parts of the system check for ticker
        candles = self.get_latest_candles(symbol, self.settings.get_active_profile().candle_timeframe, 1)
        if not candles:
            return None
        
        last_close = candles[-1].close
        # Simulate spread
        spread = last_close * (self.simulated_spread_bps / 10000.0)
        
        return Ticker(
            symbol=symbol,
            bid=last_close - (spread / 2),
            ask=last_close + (spread / 2),
            last=last_close,
            volume_24h_quote_usd=candles[-1].volume * last_close # Approximation
        )

    def get_order_book(self, symbol: str, depth: int = 10) -> Optional[object]:
        return None
