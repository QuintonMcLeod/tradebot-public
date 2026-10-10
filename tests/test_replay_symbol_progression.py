"""Guards on what the weekend replay reveals, symbol by symbol.

Two defects were found in the forward paper record on 2026-10-10 and are pinned
here so they cannot come back quietly:

1. The replay sliced every symbol with one warmup count taken from a single
   reference symbol.  The candle stores are not the same length, so the shorter
   ones were sliced past their own end, handed the whole replay day at cursor 0
   and frozen on the 23:55 candle.  Twenty four of the twenty six symbols could
   never reach the entry hour, and the ones that did traded a price that never
   moved: entry and exit fills were identical, so the result was a loss equal to
   the costs, 54 trades and -488.87 USD.
2. A closed paper trade recorded the hold the strategy saw and never the hold
   that actually happened, so a position force-closed 77 milliseconds after it
   opened carried duration_seconds = 900 and the pattern was invisible.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradebot_sci.broker.trade_result_store import (
    LEGACY_RECORD_EPOCH,
    RECORD_EPOCH,
    TradeResult,
    TradeResultStore,
)
from tradebot_sci.market.replay_provider import ReplayMarketProvider

REPLAY_DAY = datetime(2026, 3, 3, tzinfo=timezone.utc)
# 288 five-minute candles make one full replay day
BARS_PER_DAY = 288


def _write_candles(path: Path, first_day: datetime, days: int) -> None:
    """Write whole 5m days of flat candles starting at ``first_day``."""
    candles = []
    for day in range(days):
        for bar in range(BARS_PER_DAY):
            ts = first_day + timedelta(days=day, minutes=5 * bar)
            price = 1.1 + day * 0.001 + bar * 0.00001
            candles.append({
                "timestamp": ts.isoformat(),
                "open": price,
                "high": price + 0.0002,
                "low": price - 0.0002,
                "close": price,
                "volume": 1.0,
            })
    path.write_text(json.dumps(candles))


def _provider(tmp_path: Path) -> ReplayMarketProvider:
    """A replay whose two symbols hold different amounts of history.

    LONGUSD carries three days of history and SHORTUSD one, which is the shape
    of the real data directory: EURUSD runs from 2026-01-30 and the other
    twenty four from 2026-02-16.  One shared warmup count cannot serve both.
    """
    data_dir = tmp_path / "replay_data"
    data_dir.mkdir()
    _write_candles(data_dir / "LONGUSD_5m.json", REPLAY_DAY - timedelta(days=3), 4)
    _write_candles(data_dir / "SHORTUSD_5m.json", REPLAY_DAY - timedelta(days=1), 2)
    return ReplayMarketProvider(
        data_dir=data_dir,
        symbols=["LONGUSD", "SHORTUSD"],
        replay_date=REPLAY_DAY,
    )


def test_every_symbol_reveals_the_same_candle_as_the_cursor(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider._warmup_by_sym["LONGUSD"] != provider._warmup_by_sym["SHORTUSD"], (
        "the two symbols must not share a warmup boundary for this test to mean anything"
    )

    for _ in range(provider._total_day_candles):
        if provider.in_warmup:
            provider.advance()
            continue
        provider.advance()
        cursor_time = provider.sim_time
        for symbol in ("LONGUSD", "SHORTUSD"):
            candles = provider.get_latest_candles(symbol, "5m", limit=1)
            assert candles, f"{symbol} has no visible candles at cursor {provider._cursor}"
            assert candles[-1].timestamp == cursor_time, (
                f"{symbol} is at {candles[-1].timestamp} while the cursor is at {cursor_time}; "
                "a symbol ahead of the cursor trades a price that has not happened yet"
            )


def test_no_symbol_is_frozen_on_the_last_candle_of_the_day(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    short_store_len = len(provider._candles["SHORTUSD"]["5m"])

    for _ in range(30):
        provider.advance()

    visible = provider.get_latest_candles("SHORTUSD", "5m", limit=short_store_len)
    assert len(visible) < short_store_len, (
        "the whole store is visible at cursor 30, which means this symbol was handed "
        "the entire replay day at once and is frozen"
    )


def test_all_symbols_reach_the_entry_hour(tmp_path: Path) -> None:
    """The 20:00-21:00 UTC window is where the scrape strategy is allowed to enter."""
    provider = _provider(tmp_path)
    reached = set()
    for _ in range(provider._total_day_candles):
        provider.advance()
        if provider.sim_time is None or provider.sim_time.hour != 20:
            continue
        for symbol in ("LONGUSD", "SHORTUSD"):
            candles = provider.get_latest_candles(symbol, "5m", limit=1)
            if candles and candles[-1].timestamp.hour == 20:
                reached.add(symbol)
        if len(reached) == 2:
            break
    assert reached == {"LONGUSD", "SHORTUSD"}


def test_throughput_counts_the_candles_the_cursor_actually_revealed(tmp_path: Path) -> None:
    """A day's throughput must count revealed candles, not calls that did nothing."""
    provider = _provider(tmp_path)
    day = provider._total_day_candles
    for _ in range(day + 10):
        provider.advance()

    counted = provider.throughput()
    assert counted["candles"] == day
    assert counted["cursor_moves"] == day, (
        "advance() past the end of the replayed day was counted as a revealed candle"
    )


def test_throughput_records_the_evaluations_the_strategy_saw(tmp_path: Path) -> None:
    """The number the forward test is worth: symbol looks, and looks in the hour."""
    provider = _provider(tmp_path)
    provider.note_cycle(evaluations=26, in_window=0)
    provider.note_cycle(evaluations=26, in_window=26)
    provider.note_cycle(evaluations=24, in_window=0)

    counted = provider.throughput()
    assert counted["cycles"] == 3
    assert counted["symbol_evaluations"] == 76
    assert counted["in_window_evaluations"] == 26


def test_closed_trade_records_the_real_hold_not_only_the_simulated_one() -> None:
    opened = datetime(2026, 10, 10, 1, 0, 0, tzinfo=timezone.utc)
    closed = opened + timedelta(seconds=0.077)
    result = TradeResult(
        symbol="NZDCAD",
        closed_at=closed.isoformat(),
        pnl_pct=-0.05,
        pnl_usd=-4.75,
        is_win=False,
        tier="100%",
        capital_at_close=10000.0,
        opened_at=opened.isoformat(),
        duration_seconds=900.0,
        strategy="forex_structure_breakout_best",
        exit_reason="Time Decay Reached (48 bars)",
    )
    assert result.duration_seconds == 900.0
    assert result.wall_duration_seconds == 0.077
    assert result.record_epoch == RECORD_EPOCH


def test_an_explicit_wall_hold_is_kept() -> None:
    """Where closed_at is interpolated from the simulated hold, the caller wins."""
    result = TradeResult(
        symbol="EURUSD",
        closed_at="2026-10-10T12:00:00+00:00",
        pnl_pct=0.0,
        pnl_usd=0.0,
        is_win=False,
        tier="100%",
        capital_at_close=10000.0,
        opened_at="2026-10-10T08:00:00+00:00",
        duration_seconds=14400.0,
        wall_duration_seconds=0.031,
    )
    assert result.wall_duration_seconds == 0.031


def test_a_row_written_before_the_stamp_is_read_as_legacy() -> None:
    legacy = {
        "symbol": "NZDCAD",
        "closed_at": "2026-10-10T01:00:00.077000+00:00",
        "opened_at": "2026-10-10T01:00:00+00:00",
        "pnl_pct": -0.05,
        "pnl_usd": -4.75,
        "is_win": False,
        "tier": "100%",
        "capital_at_close": 10000.0,
        "duration_seconds": 900.0,
    }
    result = TradeResult.from_dict(legacy)
    assert result.record_epoch == LEGACY_RECORD_EPOCH
    assert result.wall_duration_seconds == 0.077

    store = TradeResultStore("", skip_save=True)
    store.results = [result]
    payload = [r.to_dict() for r in store.results]
    assert payload[0]["record_epoch"] == LEGACY_RECORD_EPOCH
    assert payload[0]["wall_duration_seconds"] == 0.077

def test_the_strategy_reports_which_side_of_its_entry_hour_it_is_on() -> None:
    """The value the throughput count above reads, rather than its log string.

    A replay can only be judged on how often the strategy was handed a candle
    inside its own entry hour, so the strategy has to say which side of that hour
    it is on as a value. Reading it back out of the HOLD summary string would make
    the count break silently the day someone reworded the string.
    """
    from datetime import datetime as _dt, timezone as _tz

    from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
    from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade

    def snapshot_at(hour: int) -> MarketSnapshot:
        at = _dt(2026, 10, 12, hour, 30, tzinfo=_tz.utc)
        candles = [
            Candle(
                timestamp=at - timedelta(minutes=5 * (24 - i)),
                open=1.1, high=1.1002, low=1.0998, close=1.1, volume=100.0,
            )
            for i in range(25)
        ]
        return MarketSnapshot(
            symbol="EURUSD", timeframe="5m", candles=candles,
            trend_htf=TrendState(direction="long", strength=0.5),
            trend_ltf=TrendState(direction="long", strength=0.5),
            ltf_candles=candles,
        )

    strategy = ForexScrapeFade()
    strategy.score_signal(snapshot_at(20), {})
    assert strategy.last_in_entry_window is True

    strategy.score_signal(snapshot_at(9), {})
    assert strategy.last_in_entry_window is False
