from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tradebot_sci.runtime.loop import _is_market_open


def test_us_equity_closed_on_weekends_even_during_regular_hours() -> None:
    now = datetime(2025, 12, 13, 10, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    assert _is_market_open("SPY", now) is False


def test_us_equity_open_on_weekday_regular_hours() -> None:
    now = datetime(2025, 12, 15, 10, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    assert _is_market_open("SPY", now) is True


def test_crypto_always_open() -> None:
    # Crypto hours: 12PM–6AM EST. Use 1PM EST which is within active hours.
    now = datetime(2025, 12, 13, 13, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    assert _is_market_open("BTCUSD", now) is True

