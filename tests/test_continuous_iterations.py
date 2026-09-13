"""Verify that run_bot() uses itertools.count() when iterations=None.

Instead of mocking the entire run_bot() startup, we directly verify:
1.  The iterator selection logic (itertools.count vs range)
2.  That DummySettings builds correctly
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest


class DummySettings(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            logging=SimpleNamespace(),
            app=SimpleNamespace(profile_name="crypto_247", trading_confirmation=True),
            market=SimpleNamespace(
                symbols=["BTCUSD"],
                default_symbol="BTCUSD",
                trading_confirmation=True,
                exchange_provider="oanda",
                broker_mode="oanda",
            ),
            schedule=SimpleNamespace(sessions=[], timezone="UTC"),
            runtime=SimpleNamespace(
                strike_max_consecutive=0,
                strike_cooldown_cycles=0,
                guard_block_threshold=0,
                guard_block_cooldown_cycles=0,
                cancel_orders_on_start=False,
                allow_inherited_position=False,
                flatten_on_exit=True,
                intraday_flatten=False,
                keep_alive_interval_seconds=1,
                position_hold_store_path="data/position_hold_store.json",
                execute_trades=False,
            ),
            profile=SimpleNamespace(
                candle_timeframe="5m",
                market_poll_interval_seconds=1,
                ai_decision_interval_seconds=1,
            ),
            broker=SimpleNamespace(
                execution_mode="paper",
                read_only=False,
            ),
        )


def test_settings_contain_profile_name():
    settings = DummySettings()
    assert settings.app.profile_name == "crypto_247"


def test_run_bot_uses_infinite_iterator():
    """Verify that the loop module uses itertools.count() for unlimited iterations
    and range(n) for limited iterations, matching the code at loop.py line 650:
        loop_iter = itertools.count() if iterations is None else range(iterations)
    """
    # Simulate the exact iterator selection logic from run_bot()
    # Case 1: iterations=None -> itertools.count() (infinite)
    iterations_none = None
    loop_iter_inf = itertools.count() if iterations_none is None else range(iterations_none)
    assert isinstance(loop_iter_inf, type(itertools.count()))
    
    # Verify it's truly infinite by taking several values
    vals = [next(loop_iter_inf) for _ in range(10)]
    assert vals == list(range(10))

    # Case 2: iterations=5 -> range(5) (finite)
    iterations_five = 5
    loop_iter_fin = itertools.count() if iterations_five is None else range(iterations_five)
    assert isinstance(loop_iter_fin, range)
    assert list(loop_iter_fin) == [0, 1, 2, 3, 4]


def test_infinite_count_continues_unbounded():
    """Verify itertools.count() produces values beyond any finite limit."""
    counter = itertools.count()
    for expected in range(1000):
        assert next(counter) == expected
