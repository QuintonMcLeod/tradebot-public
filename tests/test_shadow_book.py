"""The shadow book: the setups the desk declined, scored with the rules frozen first.

These tests never touch the network and never touch the live files. The scoring rule
is a pure function of candles, so it is tested against candles written by hand, one
case per way a setup can end.

What is being defended:

  * the stop wins a bar that touches both levels, because the project's own barrier
    work uses the stop-wins assumption (facts 145, 146) and a scoreboard that is
    more generous than the test it informs is worthless;
  * the desk's measured spread is charged on every outcome, so a setup that only
    works before costs cannot be reported as a winner;
  * MFE and MAE from candles are labelled as reconstructed, because the live sampler
    is a different measurement and the two must not be mixed;
  * `score` never scores a setup twice, so the total cannot drift upward by rerunning it.

Run: python3 -m pytest tests/test_shadow_book.py -q
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "shadow_book.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("shadow_book_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def book():
    return load_tool()


def setup(**kw) -> dict:
    """Live trade 7, the trade the desk actually took: short EUR_USD at 1.12613."""
    s = {"id": "abc123", "decided_at": "2026-10-06T13:06:50+00:00", "window": "13:00",
         "instrument": "EUR_USD", "side": "short", "entry": 1.12613, "stop": 1.12900,
         "target": 1.11980, "horizon_hours": 24.0, "horizon_at": "2026-10-07T13:06:50+00:00",
         "spread_pips": 1.7, "reason": "retrace of the 76% level in a downtrend"}
    s.update(kw)
    return s


def bar(t, h, l, c=None) -> dict:
    return {"t": t, "o": c or (h + l) / 2, "h": h, "l": l, "c": c or (h + l) / 2}


# ── the scoring rule, one case per way a setup can end ────────────────────

def test_short_that_reaches_its_target_scores_the_reward_ratio(book):
    out = book.score_setup(setup(), [
        bar("2026-10-06T13:10:00Z", 1.12650, 1.12300),
        bar("2026-10-06T14:00:00Z", 1.12500, 1.11950),
    ])
    assert out["outcome"] == "target"
    assert out["gross_r"] == 2.206                    # 63.3 pips of reward / 28.7 pips of risk
    assert out["cost_r"] == 0.03                      # half of the 1.7 pip spread: a limit fills at its level
    assert out["net_r"] == pytest.approx(2.176, abs=0.002)
    assert out["exit_price"] == 1.1198
    assert out["bars"] == 2


def test_short_that_is_stopped_scores_minus_one_r(book):
    out = book.score_setup(setup(), [
        bar("2026-10-06T15:00:00Z", 1.12700, 1.12500),
        bar("2026-10-06T16:00:00Z", 1.12940, 1.12600),
    ])
    assert out["outcome"] == "stopped"
    assert out["gross_r"] == -1.0
    assert out["net_r"] == pytest.approx(-1.03, abs=0.002)   # half the spread, charged on a loser too


def test_a_bar_that_touches_both_levels_is_a_stop_and_is_flagged(book):
    out = book.score_setup(setup(), [bar("2026-10-06T17:00:00Z", 1.13000, 1.11900)])
    assert out["outcome"] == "stopped"
    assert out["ambiguous"] is True
    assert out["tie_rule"] == "stop"


def test_a_setup_that_reaches_neither_level_is_marked_out_at_the_horizon(book):
    out = book.score_setup(setup(), [
        bar("2026-10-06T18:00:00Z", 1.12650, 1.12400, 1.12500),
        bar("2026-10-07T12:00:00Z", 1.12600, 1.12450, 1.12500),
    ])
    assert out["outcome"] == "time"
    assert out["gross_r"] == 0.394                    # 11.3 pips in profit when the clock ran out
    assert out["net_r"] == pytest.approx(0.335, abs=0.002)
    assert out["exit_price"] == 1.125


def test_a_long_is_scored_the_other_way_round(book):
    s = setup(side="long", entry=1.10000, stop=1.09500, target=1.11000)
    assert book.score_setup(s, [bar("2026-10-06T18:00:00Z", 1.11100, 1.09900)])["outcome"] == "target"
    assert book.score_setup(s, [bar("2026-10-06T18:00:00Z", 1.10100, 1.09450)])["outcome"] == "stopped"


def test_mfe_and_mae_are_reconstructed_and_say_so(book):
    out = book.score_setup(setup(), [
        bar("2026-10-06T13:10:00Z", 1.12650, 1.12400),   # 3.7 pips against at worst
        bar("2026-10-06T14:00:00Z", 1.12500, 1.11950),   # 66.3 pips in favour at best
    ])
    assert out["mae_r"] == pytest.approx(-0.13, abs=0.002)
    assert out["mfe_r"] == 2.31
    assert "reconstructed from M5 candles" in out["excursion_source"]


def test_a_setup_with_no_candles_is_not_scored_as_a_win(book):
    assert book.score_setup(setup(), [])["outcome"] == "NO_DATA"


def test_a_setup_whose_entry_equals_its_stop_is_an_error_not_a_zero(book):
    out = book.score_setup(setup(stop=1.12613), [bar("2026-10-06T13:10:00Z", 1.12700, 1.12500)])
    assert out["outcome"] == "ERROR"


def test_the_spread_charged_is_the_one_the_setup_was_recorded_with(book):
    cheap = book.score_setup(setup(spread_pips=0.8), [bar("2026-10-06T17:00:00Z", 1.13000, 1.11900)])
    dear = book.score_setup(setup(spread_pips=3.0), [bar("2026-10-06T17:00:00Z", 1.13000, 1.11900)])
    assert dear["cost_r"] > cheap["cost_r"]
    assert dear["net_r"] < cheap["net_r"]


# ── the store: scoring once, and reporting what the passes cost ───────────

def score_args(path: pathlib.Path, results: pathlib.Path, force=False) -> argparse.Namespace:
    return argparse.Namespace(file=str(path), results_file=str(results), force=force)


def test_score_writes_one_result_per_setup_and_never_twice(book, tmp_path, monkeypatch):
    setups, results = tmp_path / "shadow_setups.jsonl", tmp_path / "shadow_results.jsonl"
    setups.write_text(json.dumps(setup(decided_at="2026-10-06T13:06:50+00:00",
                                       horizon_at="2026-10-07T13:06:50+00:00")) + "\n")
    monkeypatch.setattr(book, "candles_between",
                        lambda ins, a, b: [bar("2026-10-06T14:00:00Z", 1.12500, 1.11950)])

    book.cmd_score(score_args(setups, results))
    first = json.loads(results.read_text().splitlines()[0])
    assert first["outcome"] == "target"

    # a second sweep must not score the same setup again and inflate the total
    book.cmd_score(score_args(setups, results))
    assert len(results.read_text().splitlines()) == 1


def test_a_setup_before_its_horizon_is_left_waiting(book, tmp_path, monkeypatch):
    setups, results = tmp_path / "shadow_setups.jsonl", tmp_path / "shadow_results.jsonl"
    setups.write_text(json.dumps(setup(
        decided_at="2026-10-07T13:00:00+00:00", horizon_at="2099-01-01T00:00:00+00:00")) + "\n")
    monkeypatch.setattr(book, "candles_between",
                        lambda ins, a, b: pytest.fail("must not price a setup before its horizon"))
    book.cmd_score(score_args(setups, results))
    assert not results.exists() or results.read_text() == ""


def test_a_mid_price_graze_is_not_a_fill(book):
    """The flaw the live trades exposed: the mid touched the level and the broker did not fill.

    Live trade 5: the mid first touched its 1.32150 target at 08:40Z and the fill came at
    08:53Z, because the ask has to reach a short's buy limit, not the mid.
    """
    # the target is 1.11980 and the adjustment is 0.85 pips, so the mid has to reach
    # 1.119715 before a short's buy limit at 1.11980 is filled
    out = book.score_setup(setup(), [bar("2026-10-01T08:40:00Z", 1.12650, 1.11978)])
    assert out["outcome"] == "time"                   # 0.2 pips short of the target is not a fill
    assert out["levels_adjusted_pips"] == 0.85


def test_a_real_crossing_of_the_adjusted_level_is_a_fill(book):
    out = book.score_setup(setup(), [bar("2026-10-01T08:55:00Z", 1.12650, 1.11960)])
    assert out["outcome"] == "target"


def test_report_totals_the_declined_setups_and_says_what_a_positive_sum_means(
        book, tmp_path, monkeypatch, capsys):
    setups, results = tmp_path / "shadow_setups.jsonl", tmp_path / "shadow_results.jsonl"
    setups.write_text(json.dumps(setup(id="one")) + "\n" + json.dumps(setup(id="two")) + "\n")
    book.append_jsonl(results, {**setup(id="one"), "outcome": "target", "gross_r": 2.2,
                               "cost_r": 0.06, "net_r": 2.14, "mfe_r": 2.3, "mae_r": -0.1})
    book.append_jsonl(results, {**setup(id="two"), "outcome": "stopped", "gross_r": -1.0,
                               "cost_r": 0.06, "net_r": -1.06, "mfe_r": 0.4, "mae_r": -1.0})

    book.cmd_report(argparse.Namespace(file=str(setups), results_file=str(results), json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["summary"] == {"n": 2, "target": 1, "stopped": 1, "time": 0, "ambiguous": 0,
                              "sum_net_r": 1.08, "mean_net_r": 0.54}
    assert out["by_window"]["13:00"]["n"] == 2
    assert "too tight" in out["reading"]

    book.cmd_report(argparse.Namespace(file=str(setups), results_file=str(results), json=False))
    printed = capsys.readouterr().out
    assert "declined setups scored net +1.08R" in printed
    assert "window 13:00: n=2" in printed
