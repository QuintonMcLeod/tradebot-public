"""Sizing: the configured risk per trade has to be the risk the trade actually takes.

Steven's order, 2026-10-10: raise the trade size from 1 percent to 6 percent, and put
the daily stop at 12 percent, matching the live desk (tools/oanda_trade.py, where
MAX_RISK_PCT_PER_TRADE is 6.0 and MAX_DAILY_LOSS_PCT is 12.0).

A config value is not the same as a delivered size, and this project has already been
bitten by exactly that: the paper broker sizes from `profile.risk_per_trade_pct`, and
its affordability guard then caps the notional at `profile.target_leverage` times the
balance. On EURUSD a 20-pip stop is 0.172 percent of the price, so 6 percent of the
balance needs 34.8 times the balance in notional. At the old cap of 10 the order would
have been shrunk to about 1.7 percent of the balance while every log line still said
6 percent: the same silent-cap failure as incident 21 and the
spread-guard-tests-the-wrong-number family. So the cap was raised to 50, which is the
paper broker's own ceiling (PAPER_MAX_LEVERAGE), and these tests pin the invariant
that matters:

  the leverage cap must not strangle the configured risk on the pairs the strategy
  trades at its own 20-pip stop.

It holds for nine of the eleven pairs with a cached price. The two JPY crosses are the
exception and are pinned as such rather than quietly left: GBPJPY needs 63.5x and
EURJPY 55.0x to risk 6 percent at a 20-pip stop, both above the paper broker's 50x
ceiling, so those two deliver 4.73 and 5.46 percent. Raising the cap past 50 would not
buy anything real: it would only make a paper account's number match its own log line
while the leverage itself became fictional.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.config.loader import load_settings  # noqa: E402
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState  # noqa: E402
from tradebot_sci.strategy.variants.forex_scrape_fade import ForexScrapeFade  # noqa: E402

# One representative price per pair, taken from the cached research candles on
# 2026-10-10 (data/forex_backtest/*_5m.json, last close). Prices move; the invariant is
# about the relationship between the stop, the risk and the cap, not about a level.
PRICES = {
    "EURUSD": 1.1614,
    "GBPUSD": 1.3402,
    "USDJPY": 157.84,
    "USDCAD": 1.3567,
    "AUDJPY": 110.9320,
    "NZDUSD": 0.5899,
    "USDCHF": 0.7760,
    "AUDUSD": 0.7028,
    "GBPJPY": 211.5380,
    "EURJPY": 183.3100,
}


def break_snapshot(symbol="EURUSD", close=1.16000, bars=30, depth_pips=3.0, hour=20):
    """A flat prior range, then one bar closing below it: the strategy's long entry."""
    pip = 0.01 if symbol.upper().endswith("JPY") else 0.0001
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


def needed_leverage(symbol: str, price: float, strat: ForexScrapeFade,
                    risk_pct: float) -> float:
    """Notional, as a multiple of the balance, that a full-risk entry needs."""
    stop_fraction = strat.stop_pips * strat._pip_size(symbol) / price
    return risk_pct / stop_fraction


# ── the config the bot runs on ───────────────────────────────────────────────────

def test_the_profile_carries_the_configured_risk_and_daily_halt():
    s = load_settings()
    prof = s.get_active_profile()
    assert float(prof.risk_per_trade_pct) == pytest.approx(0.06), (
        "the profile must carry the configured risk per trade, not the 1 percent default"
    )
    assert float(s.risk.limit_loss_daily_pct) == pytest.approx(0.12), (
        "the daily loss halt is read by safety_guard from settings.risk.limit_loss_daily_pct"
    )


def test_the_engine_propagation_puts_the_profile_risk_on_the_decision():
    """The engine copies settings.risk.risk_per_trade_pct onto the strategy, and the
    strategy's decisions carry it. Without that copy the decision carries the base
    class's 1.5 percent fallback and the config change would do nothing."""
    s = load_settings()
    strat = ForexScrapeFade()
    strat.profile_risk_pct = float(s.risk.risk_per_trade_pct)     # what engine.py does
    d = strat.check_entry_signal(break_snapshot(), {"current_spread": 0.00015})
    assert d is not None and d.action == "enter_long"
    assert float(d.risk_per_trade_pct) == pytest.approx(0.06)


def test_the_fallback_still_exists_for_an_unconfigured_strategy():
    assert ForexScrapeFade().get_risk_pct() == pytest.approx(0.015)


# ── the cap must not strangle the risk it was raised for ─────────────────────────

def test_the_cap_covers_the_configured_risk_on_the_majors():
    s = load_settings()
    prof = s.get_active_profile()
    risk = float(prof.risk_per_trade_pct)
    cap = float(prof.target_leverage)
    strat = ForexScrapeFade()
    covered = [sym for sym in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDJPY",
                               "AUDUSD", "NZDUSD", "USDCHF")
               if needed_leverage(sym, PRICES[sym], strat, risk) <= cap + 1e-9]
    assert len(covered) == 8, (
        f"the {cap:.0f}x cap no longer covers the configured {risk:.0%} at a "
        f"{strat.stop_pips:.0f}-pip stop on the majors; covered: {covered}"
    )


def test_the_two_jpy_crosses_are_capped_and_say_by_how_much():
    """Pinned so the number cannot drift unnoticed: these two need more than the paper
    broker's 50x ceiling, so their delivered risk is the cap, not the config."""
    s = load_settings()
    prof = s.get_active_profile()
    risk = float(prof.risk_per_trade_pct)
    cap = float(prof.target_leverage)
    strat = ForexScrapeFade()
    for sym, expected_delivered in (("GBPJPY", 0.0473), ("EURJPY", 0.0546)):
        need = needed_leverage(sym, PRICES[sym], strat, risk)
        assert need > cap, f"{sym} is expected to need more than the {cap:.0f}x cap"
        delivered = cap * (strat.stop_pips * strat._pip_size(sym) / PRICES[sym])
        assert delivered == pytest.approx(expected_delivered, abs=0.0005)


def test_a_tighter_cap_would_shrink_the_trade_silently():
    """The failure mode this file exists for, stated as arithmetic: at the old 10x cap
    a 6 percent order on EURUSD is delivered as 1.7 percent of the balance."""
    strat = ForexScrapeFade()
    stop_fraction = strat.stop_pips * strat._pip_size("EURUSD") / PRICES["EURUSD"]
    assert 10.0 * stop_fraction == pytest.approx(0.0172, abs=0.0005)
