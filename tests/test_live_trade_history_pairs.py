"""Regression tests for the live trade pairing in tools/live_trade_history.py.

The bracket for each live trade comes from a written table keyed by the entry
timestamp, while the fills come from the ledger. That join used to be positional,
so when the ledger window silently dropped the first live entry every later trade
wore the previous trade's stop. These tests lock the two properties that prevent a
repeat: a close pairs with the open of its OWN instrument, and a bracket is looked
up by the entry's own timestamp rather than its index.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import live_trade_history as lth  # noqa: E402


def fill(time, instrument, units, price, pl, reason):
    return dict(time=time, instrument=instrument, units=units,
                price=price, pl=pl, reason=reason)


def test_close_pairs_with_its_own_instrument_not_first_in_first_out():
    # Two positions held at once. A single FIFO queue would hand EUR_USD's exit to
    # the GBP_USD entry, which is the cross-instrument fault this guards against.
    txns = [
        fill("2026-09-17T08:00:00Z", "EUR_USD", -100, 1.10, "0.0000", "MARKET_ORDER"),
        fill("2026-09-17T09:00:00Z", "GBP_USD", -100, 1.30, "0.0000", "MARKET_ORDER"),
        fill("2026-09-17T10:00:00Z", "GBP_USD", 100, 1.31, "1.0", "TAKE_PROFIT_ORDER"),
        fill("2026-09-17T11:00:00Z", "EUR_USD", 100, 1.09, "1.0", "TAKE_PROFIT_ORDER"),
    ]
    rows = lth.pair_trades(txns)
    assert [(r["entry"]["instrument"], r["exit"]["instrument"]) for r in rows] == [
        ("EUR_USD", "EUR_USD"), ("GBP_USD", "GBP_USD")]
    # Rows are reported in entry-time order, not exit-time order.
    assert [r["entry"]["time"] for r in rows] == [
        "2026-09-17T08:00:00Z", "2026-09-17T09:00:00Z"]


def test_bracket_is_keyed_by_entry_time_not_by_position():
    # The written table must be addressed by the entry's timestamp. If it were an
    # index, dropping the first entry would give trade 2 the stop written for trade 1.
    by_open = {m["opened"]: m for m in lth.TRADE_META}
    assert len(by_open) == len(lth.TRADE_META), "two trades share a written timestamp"
    assert by_open["2026-09-17T20:02:05"]["n"] == 2
    assert by_open["2026-09-17T20:02:05"]["stop"] == 1.15015
    # The first trade's bracket must never be reachable from the second's key.
    assert by_open["2026-09-17T20:02:05"]["stop"] != by_open["2026-09-17T08:36:13"]["stop"]


def test_every_written_bracket_carries_a_stop_and_a_target():
    for m in lth.TRADE_META:
        assert m["stop"] is not None, m
        assert m["target"] is not None, m


def test_risk_is_priced_in_the_account_currency_not_the_quote_currency():
    # USD_CAD's quote currency is CAD, so units times stop distance is an amount of CAD.
    # Reading it as dollars overstated this trade's risk fraction by 41 percent and made a
    # compliant 6 percent entry look like an 8 percent breach.
    usd_cad = dict(time="2026-10-08T18:13:01Z", instrument="USD_CAD", units=6290,
                   price=1.42304, pl="0.0000", reason="MARKET_ORDER",
                   homeConversionFactors={"lossQuoteHome": {"factor": "0.70978804969387"}})
    assert round(lth.risk_in_account_currency(6290, 0.00324, usd_cad), 2) == 14.47
    # A pair already quoted in the account currency is unchanged by its factor of 1.
    eur_usd = dict(time="2026-10-06T13:06:50Z", instrument="EUR_USD", units=-2987,
                   price=1.12613, pl="0.0000", reason="MARKET_ORDER",
                   homeConversionFactors={"lossQuoteHome": {"factor": "1"}})
    assert round(lth.risk_in_account_currency(-2987, 0.00287, eur_usd), 2) == 8.57


def test_a_non_account_quote_without_a_factor_is_a_hard_error():
    # No factor and not quoted in USD: the tool must refuse rather than guess a rate.
    bare = dict(time="2026-10-08T18:13:01Z", instrument="USD_CAD", units=6290,
                price=1.42304, pl="0.0000", reason="MARKET_ORDER")
    try:
        lth.risk_in_account_currency(6290, 0.00324, bare)
    except SystemExit as exc:
        assert "lossQuoteHome" in str(exc)
    else:
        raise AssertionError("a missing conversion factor must not be guessed")
