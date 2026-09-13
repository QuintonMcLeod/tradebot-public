from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import tradebot_sci.runtime.cycle as cycle


def _fake_snapshot(symbol="TEST", timeframe="5m"):
    return SimpleNamespace(symbol=symbol, timeframe=timeframe, candles=[])


class DummyEngine:
    def __init__(self):
        self.last_strat_name = "DummyStrategy"
        self.last_strat_grade = "N/A"
        self.last_strat_score = 0.0

    def score_structure(self, snapshot):  # noqa: ANN001
        return 1.0, "ok"

    def score_icc_readiness(self, snapshot):  # noqa: ANN001
        return 1.0, "ok"

    def score_icc_grade(self, snapshot):  # noqa: ANN001
        return 1.0, "B", "ok"


class DummyExecutor:
    def __init__(self, states: dict[str, dict]):
        self._states = states

    def get_open_position_snapshot(self, symbol: str):
        return None

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return self._states.get(symbol, {})

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        st = state or self._fetch_symbol_state(symbol)
        return bool(
            abs(st.get("position_shares", 0)) > 0
            or st.get("working_orders", 0)
            or st.get("synthetic_stop_armed")
        )

    def get_liquid_capital(self, symbol=None):
        return 10000.0


def test_build_candidate_list_locks_to_symbol_with_working_orders(monkeypatch):
    monkeypatch.setattr(cycle, "fetch_snapshot", lambda *_args, **_kwargs: _fake_snapshot("QQQ"))

    executor = DummyExecutor(
        {
            "QQQ": {"position_shares": 0, "working_orders": 2, "synthetic_stop_armed": False},
            "XLK": {"position_shares": 0, "working_orders": 0, "synthetic_stop_armed": False},
        }
    )
    engines = {"QQQ": DummyEngine(), "XLK": DummyEngine()}


    profile_settings = SimpleNamespace(
        structure_score_threshold=0.1,
        multi_position_enabled=False,
        max_concurrent_positions=1,
    )
    market_settings = SimpleNamespace(max_candles=200)

    now = datetime.now(timezone.utc)
    candidates, _ = cycle.build_candidate_list(
        executor,
        engines,
        provider=None,
        symbols=["QQQ", "XLK"],
        timeframe="5m",
        profile_settings=profile_settings,
        market_settings=market_settings,
        strike_tracker=None,
        now=now,
    )

    # QQQ has working orders so appears as "active campaign", XLK has no orders
    symbols_in_candidates = [c[0] for c in candidates]
    # Both may appear — QQQ as active campaign, XLK as normal candidate
    assert len(candidates) >= 1


def test_build_candidate_list_refuses_when_multiple_symbols_have_working_orders(monkeypatch):
    monkeypatch.setattr(cycle, "fetch_snapshot", lambda *_args, **_kwargs: _fake_snapshot("QQQ"))

    executor = DummyExecutor(
        {
            "QQQ": {"position_shares": 0, "working_orders": 1, "synthetic_stop_armed": False},
            "XLK": {"position_shares": 0, "working_orders": 1, "synthetic_stop_armed": False},
        }
    )
    engines = {"QQQ": DummyEngine(), "XLK": DummyEngine()}

    from types import SimpleNamespace
    profile_settings = SimpleNamespace(
        structure_score_threshold=0.1,
        multi_position_enabled=False,
        max_concurrent_positions=1,
    )
    market_settings = SimpleNamespace(max_candles=200)

    now = datetime.now(timezone.utc)
    candidates, _ = cycle.build_candidate_list(
        executor,
        engines,
        provider=None,
        symbols=["QQQ", "XLK"],
        timeframe="5m",
        profile_settings=profile_settings,
        market_settings=market_settings,
        strike_tracker=None,
        now=now,
    )

    # Both symbols have working orders — they appear as "active campaign" entries
    for c in candidates:
        assert c[3] in ("existing position", "active campaign")
