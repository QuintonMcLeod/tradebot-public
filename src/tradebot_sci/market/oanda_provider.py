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
from tradebot_sci.market.models import Candle, MarketSnapshot
from tradebot_sci.market.trend import infer_trend_from_swings

logger = logging.getLogger(__name__)

class OandaMarketDataProvider:
    """Market data provider for OANDA v20 API."""

    def __init__(self, account_id: str, api_key: str, environment: str = "practice"):
        if not HAS_OANDA:
            raise ImportError(f"OANDA dependencies missing ({_OANDA_IMPORT_ERROR}). Please install oandapyV20.")
        self.client = oandapyV20.API(access_token=api_key, environment=environment)
        self.account_id = account_id

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
        oanda_sym = self._normalize_symbol(symbol)
        oanda_tf = self._map_timeframe(timeframe)
        
        params = {
            "count": limit,
            "granularity": oanda_tf,
            "price": "M"  # Midpoint
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=oanda_sym, params=params)
            self.client.request(r)
            
            candles = []
            for c in r.response.get("candles", []):
                if not c.get("complete"):
                    continue
                mid = c.get("mid")
                if not mid:
                    continue
                    
                # OANDA timestamp is "2024-01-22T10:00:00.000000000Z"
                ts_str = c["time"].split(".")[0].replace("Z", "")
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                
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
            logger.error(f"[OANDA-DATA] Failed to fetch candles for {symbol}: {e}")
            return []

    def get_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        candles = self.get_latest_candles(symbol, timeframe, limit=200)
        trend_htf = infer_trend_from_swings(candles[-100:]) if len(candles) >= 100 else infer_trend_from_swings(candles)
        trend_ltf = infer_trend_from_swings(candles[-20:]) if len(candles) >= 20 else infer_trend_from_swings(candles)
        
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trend_htf=trend_htf,
            trend_ltf=trend_ltf,
            htf_candles=candles[-100:] if len(candles) >= 100 else candles,
            ltf_candles=candles[-20:] if len(candles) >= 20 else candles,
            htf_timeframe=timeframe,
            ltf_timeframe=timeframe,
        )

    def close(self) -> None:
        pass
