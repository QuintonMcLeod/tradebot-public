from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from tradebot_sci.market.models import Candle

logger = logging.getLogger(__name__)


def resample_candles(candles: List[Candle], target_seconds: int) -> List[Candle]:
    if not candles or target_seconds <= 0:
        return []

    resampled: List[Candle] = []
    current_bucket = None
    current_candle: Optional[Candle] = None

    for candle in candles:
        ts = candle.timestamp
        tzinfo = ts.tzinfo
        bucket_start = int(ts.timestamp() // target_seconds) * target_seconds

        if current_bucket != bucket_start:
            if current_candle is not None:
                resampled.append(current_candle)
            bucket_dt = datetime.fromtimestamp(bucket_start, tz=tzinfo) if tzinfo else datetime.fromtimestamp(bucket_start)
            current_candle = Candle(
                timestamp=bucket_dt,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            )
            current_bucket = bucket_start
        else:
            current_candle.high = max(current_candle.high, candle.high)
            current_candle.low = min(current_candle.low, candle.low)
            current_candle.close = candle.close
            current_candle.volume += candle.volume

    if current_candle is not None:
        resampled.append(current_candle)

    return resampled


def timeframe_to_seconds(timeframe: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(timeframe, 0)
