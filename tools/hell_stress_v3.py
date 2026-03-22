#!/usr/bin/env python3
"""
Hell Stress Test v3 — Regime Classifier Fix Verification
Matches original scale_hell_test.py config: 15m, EURUSD+GBPUSD, audit data.
Uses dates within the audit data range (Feb 10-24).
"""
import sys, os, logging, random, time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") or ".")

import unittest.mock
sys.modules["ib_insync"] = unittest.mock.MagicMock()
os.environ["TRADING_CONFIRMATION"] = "YES"

logging.basicConfig(level=logging.WARNING)

from tools.utils.local_provider import LocalJSONProvider
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import (
    Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
    TradingProfileSettings, RuntimeSettings,
)

SYMBOLS = ["EURUSD", "GBPUSD"]
DATA_DIR = "data/audit"
INITIAL_CAPITAL = 3000.0

# Audit data range
DATA_START = datetime(2026, 2, 10, 21, 0, tzinfo=timezone.utc)
DATA_END   = datetime(2026, 2, 24, 20, 45, tzinfo=timezone.utc)


def build_config():
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="15m",
        htf_timeframe="1h",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        min_hold_hours=0.08,
        max_hold_hours=0,
        risk_per_trade_pct=0.01,
        block_counter_trend_entries=True,
        trend_strength_floor=0.20,
        # Indicators — 4 enabled (matches config.json global)
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_supertrend_enabled=True,
        # SAR
        stop_and_reverse_enabled=True,
        reversal_risk_per_trade=0.045,
        reversal_tp_r=1.0,
        reversal_cost_aware_tp=True,
        # Pyramiding
        enable_pyramiding=True,
        max_pyramid_count=50,
    )
    settings = Settings(
        app=AppSettings(profile_name="A"),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=SYMBOLS),
        runtime=RuntimeSettings(scale_out_fraction=0.95),
        profiles={"A": profile},
    )
    return settings


def run_bt(start, end, wind_down=0):
    settings = build_config()
    bt = Backtester(ib=None, settings=settings, ai_client=None)
    bt.market_provider = LocalJSONProvider(DATA_DIR)
    bt._is_market_hours_utc = lambda ts: True
    return bt.run_backtest(
        initial_capital=INITIAL_CAPITAL,
        start_date=start, end_date=end,
        wind_down_days=wind_down,
    )


def print_trades(trades, max_show=25):
    for i, t in enumerate(trades[:max_show], 1):
        hold_h = (t.exit_time - t.entry_time).total_seconds() / 3600
        mark = "✅" if t.pnl > 0 else "❌"
        gates = t.entry_gates or {}
        htf_str = gates.get("htf_strength", "?")
        regime = gates.get("market_regime", "?")
        date_str = t.entry_time.strftime("%m/%d %H:%M")
        print(f"  {i:>2} {mark} {t.symbol:>8} {t.direction:>5} ${t.pnl:>+8.2f} "
              f"{hold_h:>5.1f}h htf={htf_str} regime={regime} {date_str}")
    if len(trades) > max_show:
        print(f"  ... ({len(trades) - max_show} more trades)")


# ═══════════════════════════════════════════
#  TEST 1: 6 Random Days
# ═══════════════════════════════════════════
def test_1():
    print("\n" + "═" * 70)
    print("  TEST 1: 6 Random Days")
    print("═" * 70)

    random.seed(42)
    all_days = []
    d = DATA_START + timedelta(days=1)  # Skip first day for warmup
    while d < DATA_END - timedelta(days=1):
        if d.weekday() < 5:
            all_days.append(d.replace(hour=0, minute=0, second=0))
        d += timedelta(days=1)

    n_days = min(6, len(all_days))
    selected = sorted(random.sample(all_days, n_days))
    print(f"  Available: {len(all_days)} trading days | Selected: {n_days}")
    print(f"  Days: {[d.strftime('%b %d (%a)') for d in selected]}")

    total_pnl = 0
    all_trades = []
    for day in selected:
        t0 = time.time()
        day_end = day.replace(hour=23, minute=59, second=59)
        try:
            result = run_bt(day, day_end)
            pnl = sum(t.pnl for t in result.trades)
            total_pnl += pnl
            all_trades.extend(result.trades)
            n = len(result.trades)
            wins = sum(1 for t in result.trades if t.pnl > 0)
            wr = wins / n * 100 if n else 0
            mark = "✅" if pnl > 0 else ("⬜" if n == 0 else "❌")
            print(f"  {day.strftime('%b %d (%a)')}: {n:>2} trades, {wr:>5.0f}% WR, ${pnl:>+8.2f} {mark} ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  {day.strftime('%b %d (%a)')}: ERROR - {e}")

    wins = sum(1 for t in all_trades if t.pnl > 0)
    n = len(all_trades)
    wr = wins / n * 100 if n else 0
    print(f"\n  TOTAL: ${total_pnl:>+.2f} | {n} trades | {wr:.0f}% WR")

    # HTF strength distribution
    strengths = [t.entry_gates.get("htf_strength", -1) for t in all_trades if t.entry_gates]
    if strengths:
        print(f"  HTF Strength Distribution:")
        for val in sorted(set(s for s in strengths if s >= 0)):
            count = sum(1 for s in strengths if s == val)
            print(f"    {val:.2f}: {count} trades {'█' * count}")

    passed = total_pnl > 0
    print(f"\n  RESULT: {'✅ PASSED' if passed else '❌ FAILED'}")
    print_trades(all_trades)
    return total_pnl, all_trades


# ═══════════════════════════════════════════
#  TEST 2: Monte Carlo
# ═══════════════════════════════════════════
def test_2(trades, n_sims=1000):
    print("\n\n" + "═" * 70)
    print(f"  TEST 2: Monte Carlo ({n_sims} shuffles)")
    print("═" * 70)

    if not trades:
        print("  No trades!")
        return False

    pnls = [t.pnl for t in trades]
    random.seed(42)
    results = []
    for _ in range(n_sims):
        shuffled = pnls.copy()
        random.shuffle(shuffled)
        results.append(sum(shuffled))

    results.sort()
    positive = sum(1 for r in results if r > 0)
    pct = positive / n_sims * 100

    def p(data, pctl):
        return data[min(int(len(data) * pctl / 100), len(data)-1)]

    print(f"  Input: {len(pnls)} trades, Total: ${sum(pnls):+.2f}")
    print(f"  Worst:  ${results[0]:+.2f} | 5th: ${p(results,5):+.2f} | Median: ${p(results,50):+.2f}")
    print(f"  95th:   ${p(results,95):+.2f} | Best: ${results[-1]:+.2f}")
    print(f"  Positive: {positive}/{n_sims} ({pct:.0f}%)")
    passed = pct >= 55
    print(f"  RESULT: {'✅ PASSED' if passed else '❌ FAILED'} (need ≥55%)")
    return passed


# ═══════════════════════════════════════════
#  TEST 3: 30-Day Grind (full data range)
# ═══════════════════════════════════════════
def test_3():
    print("\n\n" + "═" * 70)
    print("  TEST 3: Full Data Grind (Feb 11–24)")
    print("═" * 70)

    t0 = time.time()
    start = datetime(2026, 2, 11, tzinfo=timezone.utc)
    end = datetime(2026, 2, 24, tzinfo=timezone.utc)
    result = run_bt(start, end, wind_down=1)
    elapsed = time.time() - t0

    trades = result.trades
    n = len(trades)
    if n == 0:
        print("  NO TRADES")
        return False, []

    wins = sum(1 for t in trades if t.pnl > 0)
    wr = wins / n * 100
    total_pnl = sum(t.pnl for t in trades)
    gross_win = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 999

    print(f"  {n} trades | {wr:.1f}% WR | PF={pf:.2f} | ${total_pnl:+.2f} ({elapsed:.0f}s)")

    # HTF strength distribution
    strengths = [t.entry_gates.get("htf_strength", -1) for t in trades if t.entry_gates]
    if strengths:
        print(f"\n  HTF Strength Distribution:")
        for val in sorted(set(s for s in strengths if s >= 0)):
            count = sum(1 for s in strengths if s == val)
            print(f"    {val:.2f}: {count} trades {'█' * count}")

    print_trades(trades)

    passed = total_pnl > 0 and pf >= 1.0
    print(f"\n  RESULT: {'✅ PASSED' if passed else '❌ FAILED'}")
    return passed, trades


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  HELL STRESS TEST v3 — Regime Classifier Fix Verification          ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  Symbols: {SYMBOLS} | TF: 15m | HTF: 1h")
    print(f"  Data: {DATA_DIR} (Feb 10–24)")

    t1_pnl, t1_trades = test_1()
    t3_passed, t3_trades = test_3()

    # Monte Carlo on the full grind trades (bigger sample)
    mc_trades = t3_trades if len(t3_trades) > len(t1_trades) else t1_trades
    t2_passed = test_2(mc_trades)

    print("\n\n" + "═" * 70)
    print("  FINAL SCORECARD")
    print("═" * 70)
    t1_passed = t1_pnl > 0
    print(f"  Test 1 (6 Random Days):  {'✅ PASSED' if t1_passed else '❌ FAILED'} (${t1_pnl:+.2f})")
    print(f"  Test 2 (Monte Carlo):    {'✅ PASSED' if t2_passed else '❌ FAILED'}")
    print(f"  Test 3 (Full Grind):     {'✅ PASSED' if t3_passed else '❌ FAILED'}")
    all_pass = t1_passed and t2_passed and t3_passed
    print(f"\n  {'🎉 ALL TESTS PASSED' if all_pass else '⚠️  SOME TESTS FAILED'}")
    print("═" * 70)
