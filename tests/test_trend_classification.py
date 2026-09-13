from datetime import datetime, timedelta, timezone

from tradebot_sci.market.models import Candle
from tradebot_sci.market.trend import infer_trend_from_swings


def _c(i: int, o: float, h: float, l: float, c: float) -> Candle:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Candle(timestamp=now + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=1000)


def test_trend_classification_uses_swing_structure_not_slope():
    candles = [
        _c(0, 10.0, 12.0, 9.0, 10.0),
        _c(1, 10.0, 13.0, 10.0, 12.0),
        _c(2, 12.0, 11.2, 8.0, 9.0),
        _c(3, 9.0, 12.5, 9.0, 11.0),
        _c(4, 11.0, 10.8, 7.5, 8.0),
        _c(5, 8.0, 10.0, 8.0, 10.0),
    ]
    trend = infer_trend_from_swings(candles, swing_lookback=1, min_swings=2, strength_floor=0.0)
    assert trend.direction == "short"
    assert trend.strength > 0.0


def test_trend_classification_bullish_hh_hl():
    candles = [
        _c(0, 10.0, 10.5, 9.0, 9.8),
        _c(1, 9.8, 12.0, 10.0, 11.5),
        _c(2, 11.5, 11.0, 9.5, 10.5),
        _c(3, 10.5, 13.0, 11.0, 12.2),
        _c(4, 12.2, 12.0, 10.5, 11.8),
        _c(5, 11.8, 14.0, 11.5, 13.5),
    ]
    trend = infer_trend_from_swings(candles, swing_lookback=1, min_swings=2, strength_floor=0.0)
    assert trend.direction == "long"
    assert trend.strength > 0.0


def test_trend_neutral_when_insufficient_swings():
    candles = [
        _c(0, 10.0, 10.5, 9.8, 10.1),
        _c(1, 10.1, 10.6, 9.9, 10.2),
        _c(2, 10.2, 10.7, 10.0, 10.3),
        _c(3, 10.3, 10.8, 10.1, 10.4),
    ]
    trend = infer_trend_from_swings(candles, swing_lookback=1, min_swings=3)
    assert trend.direction == "neutral"


def test_trend_neutral_in_chop_structure():
    candles = [
        _c(0, 10.0, 10.8, 9.9, 10.2),
        _c(1, 10.2, 10.6, 9.7, 10.0),
        _c(2, 10.0, 10.9, 9.8, 10.3),
        _c(3, 10.3, 10.7, 9.6, 9.8),
        _c(4, 9.8, 11.0, 9.7, 10.4),
        _c(5, 10.4, 10.8, 9.5, 10.1),
    ]
    trend = infer_trend_from_swings(candles, swing_lookback=1, min_swings=2, strength_floor=0.6)
    assert trend.direction == "neutral"
