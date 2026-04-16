from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

_OANDA_IMPORT_ERROR = None
try:
    import oandapyV20
    import oandapyV20.endpoints.instruments as instruments
    HAS_OANDA = True
except ImportError as e:
    HAS_OANDA = False
    _OANDA_IMPORT_ERROR = str(e)
from tradebot_sci.market.models import Candle, MarketSnapshot, Ticker, TrendState

logger = logging.getLogger("Market_Data")

# Silence noisy OANDA internal HTTP request logs
logging.getLogger("oandapyV20").setLevel(logging.WARNING)
logging.getLogger("oandapyV20.oandapyV20").setLevel(logging.WARNING)

class OandaMarketDataProvider:
    """Market data provider for OANDA v20 API."""

    def __init__(self, account_id: str, api_key: str, environment: str = "practice"):
        if not HAS_OANDA:
            raise ImportError(f"OANDA dependencies missing ({_OANDA_IMPORT_ERROR}). Please install oandapyV20.")
        self.client = oandapyV20.API(access_token=api_key, environment=environment)
        self.account_id = account_id
        _masked_key = ('***' + api_key[-6:]) if len(api_key) > 6 else '***'
        logger.info(
            f"[OANDA] MarketData init: account={account_id}, "
            f"env={environment}, key={_masked_key}"
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Converts EURUSD to EUR_USD, handles Crypto mappings."""
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        # Standard OANDA pairs: XXX_YYY
        if len(sym) == 6:
            return f"{sym[:3]}_{sym[3:]}"
        
        # Crypto handling (BTCUSD -> BTC_USD, etc)
        # OANDA usually uses BTC_USD or XBT_USD. We'll stick to _ format.
        if sym.endswith("USD") and len(sym) > 3:
            return f"{sym[:-3]}_{sym[-3:]}"
        if sym.endswith("USDT") and len(sym) > 4:
            return f"{sym[:-4]}_{sym[-4:]}"
            
        return sym

    def _map_timeframe(self, tf: str) -> str:
        """Maps standard timeframes to OANDA granularities."""
        # Standard: 1m, 5m, 15m, 1h, 4h, 1d
        # OANDA: S5, S10, S15, S30, M1, M2, M4, M5, M10, M15, M30, H1, H2, H3, H4, H6, H8, H12, D, W, M
        tf = tf.lower().strip()
        mapping = {
            "1m": "M1", "1 min": "M1", "1 mins": "M1",
            "5m": "M5", "5 min": "M5", "5 mins": "M5",
            "15m": "M15", "15 min": "M15", "15 mins": "M15",
            "30m": "M30", "30 min": "M30", "30 mins": "M30",
            "1h": "H1", "1 hour": "H1", "1 hours": "H1",
            "4h": "H4", "4 hour": "H4", "4 hours": "H4",
            "1d": "D", "1 day": "D", "1 days": "D",
        }
        return mapping.get(tf, "M5")

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        logger.info(f"[MARKET-DATA] Fetching {limit} candles for {symbol} ({timeframe})")
        oanda_sym = self._normalize_symbol(symbol)
        oanda_tf = self._map_timeframe(timeframe)
        
        params = {
            "count": limit,
            "granularity": oanda_tf,
            "price": "M",  # Midpoint
            "alignmentTimezone": "UTC" # Explicitly enforce UTC
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
            self.client.request(r)
            
            raw_candles = r.response.get("candles", [])
            logger.info(f"[MARKET-DATA] Received {len(raw_candles)} candles from API")
            
            candles = []
            for c in raw_candles:
                mid = c.get("mid")
                if not mid:
                    continue
                    
                # OANDA timestamp is often "2024-01-22T10:00:00.000000000Z"
                # Newer Python fromisoformat handles 'Z', but may struggle with 9-digit nanos.
                # We normalize to 6-digit micros for robust parsing.
                raw_time = c["time"]
                if "." in raw_time:
                    base, rest = raw_time.split(".", 1)
                    # rest is "NNNNNNNNNZ" or "NNNNNNNNN+00:00"
                    suffix = ""
                    if "Z" in rest:
                        suffix = "Z"
                        rest = rest.replace("Z", "")
                    elif "+" in rest:
                        rest, offset = rest.split("+", 1)
                        suffix = "+" + offset
                    elif "-" in rest:
                        rest, offset = rest.split("-", 1)
                        suffix = "-" + offset
                    
                    # Truncate nanos to micros (6 digits)
                    raw_time = f"{base}.{rest[:6]}{suffix}"
                
                # Use a robust parsing method
                if raw_time.endswith("Z"):
                    ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromisoformat(raw_time)
                
                # Ensure it's UTC aware even if parsed as naive (though Z/+00:00 makes it aware)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
                
                # [DEBUG] Log the first candle time to verify 12h issue
                if not candles:
                    logger.info(f"[MARKET-DATA] Raw: {c['time']} | Normalized: {raw_time} | Parsed: {ts.isoformat()} | Epoch: {int(ts.timestamp())}")

                candles.append(Candle(
                    timestamp=ts,
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=float(c["volume"])
                ))
            return candles
        except Exception as e:
            logger.error(f"[MARKET-DATA] Failed to fetch candles for {symbol}: {e}")
            return []

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        # Resolve HTF timeframe from config
        from tradebot_sci.config.loader import load_config_json
        config = load_config_json()
        active_prof = config.get("active_profile", "primary")
        prof_data = config.get("profiles", {}).get(active_prof, {})
        htf_setting = prof_data.get("htf_timeframe") or config.get("global", {}).get("htf_timeframe") or "4h"

        ltf_candles = self.get_latest_candles(symbol, timeframe, limit=1000)
        htf_candles = self.get_latest_candles(symbol, htf_setting, limit=1000)
        
        # Neutral defaults — engine.py's Trend Detection sets direction
        _neutral = TrendState(direction="neutral", strength=0.0)

        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=ltf_candles,
            trend_htf=_neutral,
            trend_ltf=_neutral,
            htf_candles=htf_candles,
            ltf_candles=ltf_candles,
            htf_timeframe=htf_setting,
            ltf_timeframe=timeframe,
        )

    def get_ticker(self, symbol: str) -> Ticker | None:
        """Fetch live bid/ask/mid from OANDA pricing endpoint."""
        oanda_sym = self._normalize_symbol(symbol)
        try:
            import oandapyV20.endpoints.pricing as pricing
            r = pricing.PricingInfo(
                self.account_id,
                params={"instruments": oanda_sym}
            )
            self.client.request(r)
            prices = r.response.get("prices", [])
            if prices:
                p = prices[0]
                bid = float(p.get("bids", [{}])[0].get("price", 0)) if p.get("bids") else None
                ask = float(p.get("asks", [{}])[0].get("price", 0)) if p.get("asks") else None
                mid = (bid + ask) / 2 if bid and ask else (bid or ask)
                return Ticker(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    last=mid,
                    volume_24h_quote_usd=None
                )
        except Exception as e:
            logger.warning(f"[MARKET-DATA] get_ticker failed for {symbol}: {e}")
        return None

    def get_order_book(self, symbol: str, depth: int = 10):
        """OANDA doesn't expose a traditional order book."""
        return None

    def close(self) -> None:
        pass
