from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tradebot_sci.runtime.auto_schedule import select_auto_schedule_symbols


def test_auto_schedule_selects_equities_during_us_market_hours() -> None:
    now = datetime(2025, 12, 15, 10, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    selection = select_auto_schedule_symbols(["SPY", "BTCUSD", "ETHUSD"], now)
    assert selection.mode == "equity"
    assert selection.symbols == ["SPY"]


def test_auto_schedule_selects_crypto_off_hours() -> None:
    now = datetime(2025, 12, 15, 20, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    selection = select_auto_schedule_symbols(["SPY", "BTCUSD", "ETHUSD"], now)
    assert selection.mode == "extended"
    assert selection.symbols == ["BTCUSD", "ETHUSD"]

