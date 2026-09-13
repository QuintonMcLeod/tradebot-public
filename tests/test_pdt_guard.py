from datetime import date, datetime
from zoneinfo import ZoneInfo

from helpers import make_test_profile
from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.market.symbols import SYMBOL_METADATA


class _DummyIB:
    def sleep(self, seconds: float) -> None:
        return None


def test_pdt_guard_blocks_roundtrips_but_does_not_force_long_only():
    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        pdt_guard_enabled=True,
        max_equity_roundtrips_per_day=1,
    )
    executor = IbkrExecutor(
        ib_client=_DummyIB(),
        runtime_settings=profile._settings.runtime,
        profile_settings=profile,
    )
    # Use date.today() to match check_pdt_guard's internal date comparison
    executor._pdt_current_date = date.today()
    executor._pdt_roundtrips_today = 2
    executor._pdt_guard_enabled = True
    metadata = SYMBOL_METADATA["SPY"]
    assert executor._check_pdt_guard("SPY", metadata) is False
    caps = executor.get_execution_capabilities("SPY")
    assert caps["supports_short"] is True
    assert caps["long_only"] is False


def test_pdt_roundtrip_counts_on_exit_and_blocks_new_entry():
    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        pdt_guard_enabled=True,
        max_equity_roundtrips_per_day=1,
    )
    executor = IbkrExecutor(
        ib_client=_DummyIB(),
        runtime_settings=profile._settings.runtime,
        profile_settings=profile,
    )
    executor._pdt_guard_enabled = True
    executor._pdt_roundtrips_today = 0
    # Use date.today() to match check_pdt_guard's internal date comparison
    executor._pdt_current_date = date.today()
    executor._record_equity_entry("SPY")
    executor._record_equity_exit("SPY")
    assert executor._pdt_roundtrips_today == 1
    metadata = SYMBOL_METADATA["SPY"]
    assert executor._check_pdt_guard("SPY", metadata) is False

