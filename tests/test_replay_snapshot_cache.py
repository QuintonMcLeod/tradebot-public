"""The snapshot cache must follow the replay cursor, not the wall clock.

What went wrong, measured 2026-10-10: the cross-cycle snapshot cache expired on
a thirty second wall-clock timer while a replay day of 288 candles runs in about
ten seconds. Every symbol was therefore shown the same bar for roughly three
replay days, and the strategy never once found itself inside its 20:00-21:00 UTC
entry hour: zero in-window evaluations out of 6,864 symbol evaluations a day,
across every replay day measured. The cursor and the decision pass were paced to
each other the whole time (288 revealed candles, 264 completed cycles a day); it
was the data handed to the decision that was stale.
"""
from __future__ import annotations

from typing import Any

from tradebot_sci.runtime import cycle as cycle_module


class _ReplayLike:
    """A provider that reveals a new bar, the way the replay does."""

    def __init__(self) -> None:
        self.cursor = 0

    def advance(self) -> None:
        self.cursor += 1

    @property
    def data_revision(self) -> int:
        return self.cursor


class _LiveLike:
    """A provider whose data changes on the exchange's clock, not ours."""

    pass


def _fill_cache() -> None:
    cycle_module._snapshot_cache[("EURUSD", "5m", "1h", "4h", 200)] = object()  # type: ignore[assignment]
    cycle_module._snapshot_cache_ts[("EURUSD", "5m", "1h", "4h", 200)] = 0.0


def test_a_cursor_move_drops_the_snapshots_taken_before_it() -> None:
    provider: Any = _ReplayLike()
    _fill_cache()
    cycle_module._snapshot_data_revision = provider.data_revision

    provider.advance()
    cycle_module._drop_cache_if_provider_moved(provider)

    assert cycle_module._snapshot_cache == {}, (
        "the cache still holds a snapshot taken before the cursor moved, so the "
        "strategy would be shown the previous bar"
    )
    assert cycle_module._snapshot_cache_ts == {}


def test_the_cache_is_kept_while_the_cursor_stands_still() -> None:
    provider: Any = _ReplayLike()
    _fill_cache()
    cycle_module._snapshot_data_revision = provider.data_revision

    cycle_module._drop_cache_if_provider_moved(provider)

    assert len(cycle_module._snapshot_cache) == 1, (
        "snapshots are being refetched on every cycle of the same candle"
    )


def test_a_provider_without_a_revision_keeps_the_wall_clock_cache() -> None:
    """Live providers must be unaffected: this change is about replay only."""
    provider: Any = _LiveLike()
    _fill_cache()

    cycle_module._drop_cache_if_provider_moved(provider)

    assert len(cycle_module._snapshot_cache) == 1
