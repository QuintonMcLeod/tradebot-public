"""The entry-time cost readout in forex_scrape_fade, and the ceiling it reports against.

The engine fetches the live bid/ask every cycle and hands it over as
gates["current_spread"], and before this change nothing read it: the strategy enforced
`scrape_max_spread_pips` against a per-pair average from measured_spreads.json instead,
and a pair absent from that table passed unchecked because `_measured_spread_bps`
returns None and the guard only refuses on a value that is not None. Measured 2026-10-10:
25 to 27 percent of the entries the table admits are quoted above the ceiling at their
own entry bar and carry 41 to 44 percent of the admitted cost, and the uncovered pairs
are 40.5 percent of the twenty-six-pair pool at a mean 6.74 pips a round trip. Facts 178
and 179.

Three things must hold. The readout must report the live quote when there is one and the
table when there is not, and it must say so plainly when there is neither. The ceiling
must refuse rather than only report, since that is the answer this lane gave on
2026-10-10 when it was asked which of the two should happen (decision 28). And one flag
must still reverse that, so the decision can be undone in a line.

An entry with no measurable cost is refused too. "Not in the table" used to read as
"cheap", which is how 11 of the 26 pairs passed unchecked.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState  # noqa: E402
from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade  # noqa: E402

PIP = 0.0001
ENTRY_HOUR = 20


def snapshot(symbol="EURUSD", close=1.16000, bars=30, hour=ENTRY_HOUR, depth_pips=3.0):
    """A flat prior range, then one bar that closes `depth_pips` below it.

    The rule takes the prior 20 bars as the range and calls a close below the range low
    a long break, with a 2-pip minimum depth, so a flat range plus one deep bar is the
    shortest path to the guard this module is testing.
    """
    pip = 0.01 if symbol.upper().endswith("JPY") else 0.0001
    # Anchor the LAST bar inside the entry hour, so the window gate passes whatever the
    # bar count is. The strategy reads the hour off the final candle.
    last_ts = datetime(2026, 10, 9, hour, 55, tzinfo=timezone.utc)
    t0 = last_ts - timedelta(minutes=5 * (bars - 1))
    candles = [
        Candle(timestamp=t0 + timedelta(minutes=5 * i), open=close, high=close,
               low=close, close=close, volume=100.0)
        for i in range(bars - 1)
    ]
    broken = close - depth_pips * pip
    candles.append(Candle(timestamp=last_ts, open=close, high=close,
                          low=broken - pip, close=broken, volume=100.0))
    flat = TrendState(direction=0, strength=0.0)
    return MarketSnapshot(symbol=symbol, timeframe="5m", candles=candles, trend_htf=flat,
                          trend_ltf=flat)


def engine_gates(spread_price=None):
    """The gates dict the engine builds, with only the key this change reads."""
    return {"current_spread": spread_price}


# ── the toll lookup itself ───────────────────────────────────────────────────────

def test_live_quote_is_preferred_over_the_table():
    f = ForexScrapeFade()
    pips, source = f._entry_toll("EURUSD", engine_gates(0.00024), PIP, 1.16)
    assert pips == pytest.approx(2.4)
    assert source == "live bid/ask"


def test_table_is_the_fallback_when_there_is_no_live_quote():
    f = ForexScrapeFade()
    pips, source = f._entry_toll("EURUSD", engine_gates(None), PIP, 1.16)
    assert pips == pytest.approx(1.67, abs=0.02)  # 1.44 bps of 1.16
    assert source == "measured table"


def test_uncovered_pair_with_no_quote_is_reported_as_unmeasured_not_cheap():
    """The case that used to pass silently. Unknown must not read as zero."""
    f = ForexScrapeFade()
    pips, source = f._entry_toll("NOPEZZZ", engine_gates(None), PIP, 1.16)
    assert pips is None
    assert source is None


def test_a_zero_or_unusable_live_quote_falls_back_rather_than_reporting_zero():
    f = ForexScrapeFade()
    for bad in (0.0, None, "", "x"):
        pips, source = f._entry_toll("EURUSD", engine_gates(bad), PIP, 1.16)
        assert pips is not None and pips > 0
        assert source == "measured table"


def test_the_readout_is_logged_with_the_toll_in_pips_and_in_r(caplog):
    f = ForexScrapeFade()
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.variants.forex_scrape_fade"):
        f.check_entry_signal(snapshot(), engine_gates(0.00024))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "entry toll 2.40p" in text
    assert "12.0% of the 20p risk unit" in text  # 2.4 pips against a 20-pip risk unit
    assert "from live bid/ask" in text


def test_the_readout_marks_a_quote_above_the_ceiling(caplog):
    f = ForexScrapeFade()
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.variants.forex_scrape_fade"):
        f.check_entry_signal(snapshot(), engine_gates(0.00050))  # 5 pips
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "entry toll 5.00p" in text
    assert "ABOVE CEILING" in text


# ── the ceiling refuses, and one flag reverses that ──────────────────────────────

def test_the_ceiling_refuses_by_default():
    """Decided 2026-10-10 (decision 28): the ceiling refuses the entry, it does not only
    report it. The flag is still the single thing that reverses the behaviour."""
    assert ForexScrapeFade().live_spread_gate is True


def test_a_five_pip_quote_is_refused_by_default_on_a_cheap_pair():
    """EURUSD is in the table at 1.44 bps, so the table check passes. The live quote is
    5 pips, well above the 1.9-pip ceiling, so the entry does not stand."""
    f = ForexScrapeFade()
    decision = f.check_entry_signal(snapshot(), engine_gates(0.00050))
    assert decision is None


def test_with_the_gate_off_the_same_quote_still_enters():
    """The reversal path, kept tested so the decision can be undone in one line."""
    f = ForexScrapeFade()
    f.live_spread_gate = False
    decision = f.check_entry_signal(snapshot(), engine_gates(0.00050))
    assert decision is not None
    assert decision.action == "enter_long"


def test_the_refusal_is_not_silent_about_the_number(caplog):
    """The number is logged either way: a refusal must name the toll it refused on."""
    f = ForexScrapeFade()
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.variants.forex_scrape_fade"):
        assert f.check_entry_signal(snapshot(), engine_gates(0.00050)) is None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "entry toll 5.00p" in text
    assert "declined, live spread 5.00p above the 1.9p ceiling" in text


def test_a_quote_inside_the_ceiling_still_enters():
    f = ForexScrapeFade()
    decision = f.check_entry_signal(snapshot(), engine_gates(0.00015))  # 1.5 pips
    assert decision is not None
    assert decision.action == "enter_long"


def test_an_entry_with_no_measurable_cost_is_refused_not_admitted(caplog):
    """A pair absent from the table with no live quote is the case that used to pass
    silently. The ceiling cannot be checked against nothing, so the entry is refused and
    the journal says which of the two numbers was missing."""
    f = ForexScrapeFade()
    with caplog.at_level("INFO", logger="tradebot_sci.strategy.variants.forex_scrape_fade"):
        assert f.check_entry_signal(snapshot(symbol="NOPEZZZ"), engine_gates(None)) is None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "entry cost unknown" in text
    assert "no live quote is available" in text


def test_the_table_refusal_still_fires_unchanged():
    """CHFJPY is 2.11 bps in the table, which is 3.27 pips at 155.00 and so above the
    1.9-pip ceiling. The old check refuses it whether or not a live quote is present."""
    f = ForexScrapeFade()
    assert f.check_entry_signal(snapshot(symbol="CHFJPY", close=155.00),
                                engine_gates(0.0001)) is None
    assert f.check_entry_signal(snapshot(symbol="CHFJPY", close=155.00),
                                engine_gates(None)) is None
    # and with the gate off it is still refused, by the table check rather than the gate
    f2 = ForexScrapeFade()
    f2.live_spread_gate = False
    assert f2.check_entry_signal(snapshot(symbol="CHFJPY", close=155.00),
                                 engine_gates(0.0001)) is None
