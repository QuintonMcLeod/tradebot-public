"""The engine's entry-cost gate: every strategy judged on the same quoted toll.

Before 2026-10-10 the cost of an entry was tested three different ways in three
places: the strategy against a per-pair AVERAGE spread, the paper broker against an
estimate with a one-basis-point fallback for the pairs nobody had measured, and the
live broker against the one-way spread while its own comment called that a round trip.
These tests pin the replacement: one price, taken from the quote at the decision bar
with the measured table only as a fallback, stated in pips and as a share of the risk
unit, and enforced for every strategy by the engine rather than by one of them.
"""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import MagicMock

from helpers import make_test_profile
from tradebot_sci.config.models import SafetySettings
from tradebot_sci.market.models import Candle, MarketSnapshot, Ticker, TrendState
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.entry_cost import (
    LIVE_QUOTE,
    MEASURED_TABLE,
    check_entry_cost,
    cost_fraction,
    entry_toll,
    live_toll_pips,
    measured_toll_pips,
    pip_size,
    risk_pips,
)

# A symbol no measured table can cover, used to prove that an unpriceable entry is
# refused rather than treated as free.
UNMEASURED = "ZZZUSD"


# ── the price of an entry ────────────────────────────────────────────────────────

def test_the_quote_is_priced_before_the_pairs_average():
    """The live quote is what the trade pays, so it wins over the table."""
    toll, source = entry_toll("EURUSD", {"current_spread": 0.00021}, 1.1000)
    assert source == LIVE_QUOTE
    assert toll == pytest.approx(2.1, abs=1e-6)


def test_a_quote_of_zero_is_not_a_free_trade():
    """The replay reports bid equal to ask because its data has no spread field."""
    assert live_toll_pips({"current_spread": 0.0}, "EURUSD") is None
    assert live_toll_pips({"current_spread": None}, "EURUSD") is None
    assert live_toll_pips({}, "EURUSD") is None


def test_a_pair_nobody_measured_has_no_price():
    assert measured_toll_pips(UNMEASURED, 1.0000) is None
    toll, source = entry_toll(UNMEASURED, {"current_spread": 0.0}, 1.0000)
    assert toll is None and source is None


def test_pip_size_knows_the_yen_crosses():
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01


def test_the_risk_unit_comes_from_the_bracket():
    assert risk_pips(1.1000, 1.0980, "EURUSD") == pytest.approx(20.0)
    assert risk_pips(1.1000, 1.0990, "EURUSD") == pytest.approx(10.0)
    # A missing or degenerate stop leaves the risk unit unknown rather than zero.
    assert risk_pips(1.1000, None, "EURUSD") is None
    assert risk_pips(None, 1.0980, "EURUSD") is None
    assert risk_pips(1.1000, 1.1000, "EURUSD") is None


# ── the ceiling as a share of the risk unit ──────────────────────────────────────

def test_the_same_toll_is_cheap_behind_a_wide_stop_and_dear_behind_a_narrow_one():
    """1.5 pips is 7.5 percent of a 20-pip stop and 15 percent of a 10-pip stop."""
    wide = check_entry_cost("EURUSD", {"current_spread": 0.00015}, 1.1000, 1.0980, ceiling=0.10)
    narrow = check_entry_cost("EURUSD", {"current_spread": 0.00015}, 1.1000, 1.0990, ceiling=0.10)
    assert wide.allowed is True
    assert wide.fraction == pytest.approx(0.075)
    assert narrow.allowed is False
    assert narrow.fraction == pytest.approx(0.15)
    assert "above the 10% ceiling" in narrow.reason


def test_an_entry_over_the_ceiling_is_refused_with_the_working_stated():
    verdict = check_entry_cost("EURUSD", {"current_spread": 0.00060}, 1.1000, 1.0990, ceiling=0.30)
    assert verdict.allowed is False
    assert verdict.toll_pips == pytest.approx(6.0)
    assert verdict.fraction == pytest.approx(0.60)
    assert "6.00p" in verdict.readout() and "60.0% of R" in verdict.readout()


def test_an_entry_inside_the_ceiling_passes():
    verdict = check_entry_cost("EURUSD", {"current_spread": 0.00020}, 1.1000, 1.0980, ceiling=0.30)
    assert verdict.allowed is True
    assert verdict.fraction == pytest.approx(0.10)
    assert verdict.reason is None


# ── unknown cost is not cheap ────────────────────────────────────────────────────

def test_an_unpriceable_entry_is_refused_by_default():
    """An unmeasurable cost is not the same as a cheap one."""
    verdict = check_entry_cost(UNMEASURED, {"current_spread": 0.0}, 1.0000, 0.9980)
    assert verdict.allowed is False
    assert verdict.toll_pips is None
    assert "entry cost unknown" in verdict.reason
    assert "ceiling cannot be checked" in verdict.readout()


def test_an_unpriceable_entry_passes_when_the_flag_is_reversed():
    verdict = check_entry_cost(
        UNMEASURED, {"current_spread": 0.0}, 1.0000, 0.9980, refuse_unknown=False)
    assert verdict.allowed is True
    assert verdict.toll_pips is None
    assert "configured to allow it" in verdict.reason


def test_a_decision_with_no_stop_is_unjudged_and_said_to_be():
    """The ceiling is a share of R, so a decision carrying no R cannot be judged."""
    verdict = check_entry_cost("EURUSD", {"current_spread": 0.00060}, 1.1000, None)
    assert verdict.allowed is True
    assert verdict.risk_pips is None
    assert "cannot be judged as a share of R" in verdict.reason


def test_cost_fraction_is_none_rather_than_zero_when_something_is_missing():
    assert cost_fraction(None, 20.0) is None
    assert cost_fraction(2.0, None) is None
    assert cost_fraction(2.0, 0.0) is None
    assert cost_fraction(2.0, 20.0) == pytest.approx(0.10)


# ── the guard is ON by default, as ADR-002 requires ──────────────────────────────

def test_the_gate_is_on_by_default():
    safety = SafetySettings()
    assert safety.safety_entry_cost_gate_enabled is True
    assert safety.safety_entry_cost_refuse_unknown is True
    assert safety.spread_gate_max_pct == 0.30


# ── wired into the engine, for every strategy rather than for one ────────────────

class _FakeStrategy:
    """A strategy that always wants to go long, so the gate is the only thing tested."""

    name = "fake_entry_strategy"
    SESSION_PROFILE = None

    def check_entry_signal(self, *args, **kwargs):
        return AITradeDecision(
            symbol="EURUSD",
            timeframe="5m",
            bias="long",
            phase="trend",
            action="enter_long",
            entry_price=1.1000,
            stop_loss=1.0980,      # a 20-pip risk unit
            take_profit=1.1040,
            risk_per_trade_pct=0.01,
            structure_summary="fake breakout",
            invalidation_conditions="none",
            management_instructions="none",
        )

    def check_exit_signal(self, *args, **kwargs):
        return None

    def score_signal(self, *args, **kwargs):
        return 70.0, "A", "fake entry"

    def describe(self) -> str:
        return "fake entry strategy"


class _Ticket:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask


class _Provider:
    def __init__(self, bars, ticker):
        self._bars = bars
        self._ticker = ticker

    def get_latest_snapshot(self, symbol, timeframe):
        return self._bars

    def get_ticker(self, symbol):
        return self._ticker


def _bars(now):
    return MarketSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=[
            Candle(timestamp=now - timedelta(minutes=5), open=1.0990, high=1.1000,
                   low=1.0985, close=1.0995, volume=100.0),
            Candle(timestamp=now, open=1.0995, high=1.1010, low=1.0990,
                   close=1.1000, volume=100.0),
        ],
        trend_htf=TrendState(direction="long", strength=0.6),
        trend_ltf=TrendState(direction="long", strength=0.6),
    )


def _run_entry(spread_price, **safety_overrides):
    """Drive one real entry decision through the engine and return what came back."""
    now = datetime.now(timezone.utc)
    snapshot = _bars(now)
    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
        **safety_overrides,
    )
    engine = StrategyEngine(
        ai_client=MagicMock(),
        market_provider=_Provider(snapshot, _Ticket(1.0999, 1.0999 + spread_price)),
        profile=profile,
        symbol="EURUSD",
    )
    engine._strategy = _FakeStrategy()
    return engine.decide(timeframe="5m", snapshot=snapshot)


def test_the_engine_refuses_an_entry_whose_quote_is_too_big_a_slice_of_the_risk():
    """A 9-pip round trip against a 20-pip risk unit is 45 percent, over the 30 ceiling."""
    decision = _run_entry(0.00090)
    assert decision is not None
    assert decision.action == "stand_aside"
    assert "Entry Cost" in (decision.notes or "")
    assert "45.0% of the" in (decision.notes or "")


def test_the_engine_leaves_a_cheap_entry_alone():
    """A 1.5-pip round trip is 7.5 percent of the same 20-pip risk unit."""
    decision = _run_entry(0.00015)
    assert decision is not None
    assert decision.action == "enter_long"


def test_the_engine_refuses_when_the_cost_cannot_be_priced_at_all():
    """The replay reports no spread, and an unmeasured pair has no table entry."""
    now = datetime.now(timezone.utc)
    snapshot = _bars(now)
    profile = make_test_profile(
        candle_timeframe="5m", market_poll_interval_seconds=10, ai_decision_interval_seconds=30)
    provider = _Provider(snapshot, _Ticket(0.0, 0.0))
    engine = StrategyEngine(
        ai_client=MagicMock(), market_provider=provider, profile=profile, symbol=UNMEASURED)
    engine._strategy = _FakeStrategy()
    decision = engine.decide(timeframe="5m", snapshot=snapshot)
    assert decision is not None
    assert decision.action == "stand_aside"
    assert "entry cost unknown" in (decision.notes or "")


def test_the_engine_falls_back_to_the_measured_table_when_there_is_no_quote(monkeypatch):
    """A path with no live quote still prices the pair if the table covers it."""
    import tradebot_sci.broker.paper_broker as paper_broker

    monkeypatch.setattr(
        paper_broker, "_MEASURED_SPREAD_BPS", {"EURUSD": 1.44}, raising=False)
    decision = _run_entry(0.0)
    assert decision is not None
    assert decision.action == "enter_long"


def test_the_gate_can_be_switched_off_in_one_place():
    decision = _run_entry(0.00090, safety_entry_cost_gate_enabled=False)
    assert decision is not None
    assert decision.action == "enter_long"


def test_the_toll_is_stated_on_a_taken_entry_as_well_as_a_refused_one(caplog):
    """The readout is the point of the readout: it is logged either way."""
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.engine"):
        _run_entry(0.00015)
    taken = [r.getMessage() for r in caplog.records if "[ENTRY COST]" in r.getMessage()]
    assert taken, "a taken entry must still state what it pays"
    assert "1.50p" in taken[0] and "7.5% of R" in taken[0]

    caplog.clear()
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.engine"):
        _run_entry(0.00090)
    refused = [r.getMessage() for r in caplog.records if "[ENTRY COST]" in r.getMessage()]
    assert any("45.0% of R" in m for m in refused)
    assert any("entry refused" in m for m in refused)
