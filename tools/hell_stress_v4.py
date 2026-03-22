#!/usr/bin/env python3
"""
Hell Stress Test v4 — Clean data, 2 symbols, native 4h HTF
Uses forex_backtest data (Dec 7 - Mar 6)
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

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import (
    Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
    TradingProfileSettings, RuntimeSettings,
)

DATA_DIR = os.path.expanduser("~/.config/tradebot-sci/data/forex_backtest")
SYMBOLS = ["EURUSD", "GBPUSD"]
INITIAL_CAPITAL = 3000.0


def build_config():
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="5m",
        htf_timeframe="4h",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        min_hold_hours=0.08,
        max_hold_hours=0,
        risk_per_trade_pct=0.01,
        block_counter_trend_entries=True,
        trend_strength_floor=0.20,
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_supertrend_enabled=True,
        stop_and_reverse_enabled=True,
        reversal_risk_per_trade=0.045,
        reversal_tp_r=1.0,
        reversal_cost_aware_tp=True,
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


def build_paths():
    dp, hp = {}, {}
    for sym in SYMBOLS:
        p5m = os.path.join(DATA_DIR, f"{sym}_5m.json")
        p4h = os.path.join(DATA_DIR, f"{sym}_4h.json")
        if os.path.exists(p5m):
            dp[sym] = p5m
        if os.path.exists(p4h):
            hp[sym] = p4h
    return dp, hp


def run_bt(start, end, wind_down=0, warmup=3):
    settings = build_config()
    bt = Backtester(ib=None, settings=settings, ai_client=None)
    dp, hp = build_paths()
    return bt.run_backtest(
        initial_capital=INITIAL_CAPITAL,
        start_date=start, end_date=end,
        wind_down_days=wind_down,
        data_paths=dp,
        htf_data_paths=hp,
        warmup_days=warmup,
    )


def show_trades(trades, max_n=20):
    for i, t in enumerate(trades[:max_n], 1):
        hold_h = (t.exit_time - t.entry_time).total_seconds() / 3600
        mark = "✅" if t.pnl > 0 else "❌"
        g = t.entry_gates or {}
        htf_s = g.get("htf_strength", "?")
        regime = g.get("market_regime", "?")
        dt = t.entry_time.strftime("%m/%d %H:%M")
        print(f"  {i:>2} {mark} {t.symbol:>8} {t.direction:>5} ${t.pnl:>+8.2f} "
              f"{hold_h:>5.1f}h htf={htf_s} regime={regime} {dt} exit={t.exit_reason}")
    if len(trades) > max_n:
        print(f"  ... ({len(trades) - max_n} more)")


def strength_dist(trades):
    strengths = [t.entry_gates.get("htf_strength", -1) for t in trades if t.entry_gates]
    valid = [s for s in strengths if s >= 0]
    if valid:
        print(f"  HTF Strength Distribution:")
        for val in sorted(set(valid)):
            count = valid.count(val)
            print(f"    {val:.2f}: {count} trades {'█' * count}")


# ═══════════════════════════════════════════
def test_1():
    print("\n" + "═" * 70)
    print("  TEST 1: 6 Random Days (Jan-Feb window)")
    print("═" * 70)

    random.seed(42)
    all_days = []
    d = datetime(2025, 12, 15, tzinfo=timezone.utc)
    while d < datetime(2026, 2, 28, tzinfo=timezone.utc):
        if d.weekday() < 5:
            all_days.append(d)
        d += timedelta(days=1)

    selected = sorted(random.sample(all_days, 6))
    print(f"  Days: {[d.strftime('%b %d (%a)') for d in selected]}")

    total_pnl = 0
    all_trades = []
    for day in selected:
        t0 = time.time()
        day_start = day.replace(hour=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        try:
            r = run_bt(day_start, day_end, warmup=5)
            pnl = sum(t.pnl for t in r.trades)
            total_pnl += pnl
            all_trades.extend(r.trades)
            n = len(r.trades)
            wins = sum(1 for t in r.trades if t.pnl > 0)
            wr = wins/n*100 if n else 0
            mark = "✅" if pnl > 0 else ("⬜" if n == 0 else "❌")
            print(f"  {day.strftime('%b %d (%a)')}: {n:>2} trades, {wr:>5.0f}% WR, ${pnl:>+8.2f} {mark} ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  {day.strftime('%b %d (%a)')}: ERROR - {e}")

    n = len(all_trades)
    wins = sum(1 for t in all_trades if t.pnl > 0)
    wr = wins/n*100 if n else 0
    print(f"\n  TOTAL: ${total_pnl:>+.2f} | {n} trades | {wr:.0f}% WR")
    strength_dist(all_trades)
    show_trades(all_trades)
    passed = total_pnl > 0
    print(f"  RESULT: {'✅ PASSED' if passed else '❌ FAILED'}")
    return total_pnl, all_trades


# ═══════════════════════════════════════════
def test_2(trades, n_sims=1000):
    print("\n\n" + "═" * 70)
    print(f"  TEST 2: Monte Carlo ({n_sims} shuffles)")
    print("═" * 70)

    if len(trades) < 2:
        print("  Not enough trades!")
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
    p = lambda d, pc: d[min(int(len(d)*pc/100), len(d)-1)]

    print(f"  Input: {len(pnls)} trades, Total: ${sum(pnls):+.2f}")
    print(f"  Worst:  ${results[0]:+.2f} | 5th: ${p(results,5):+.2f} | Median: ${p(results,50):+.2f}")
    print(f"  95th:   ${p(results,95):+.2f} | Best: ${results[-1]:+.2f}")
    print(f"  Positive: {positive}/{n_sims} ({pct:.0f}%)")
    passed = pct >= 55
    print(f"  RESULT: {'✅ PASSED' if passed else '❌ FAILED'} (need ≥55%)")
    return passed


# ═══════════════════════════════════════════
def test_3():
    print("\n\n" + "═" * 70)
    print("  TEST 3: 30-Day Grind (Jan 15 – Feb 15)")
    print("═" * 70)

    t0 = time.time()
    start = datetime(2025, 12, 15, tzinfo=timezone.utc)
    end = datetime(2026, 1, 15, tzinfo=timezone.utc)
    result = run_bt(start, end, wind_down=1, warmup=7)
    elapsed = time.time() - t0

    trades = result.trades
    n = len(trades)
    if n == 0:
        print("  NO TRADES")
        return False, []

    wins = sum(1 for t in trades if t.pnl > 0)
    wr = wins/n*100
    total_pnl = sum(t.pnl for t in trades)
    gw = sum(t.pnl for t in trades if t.pnl > 0)
    gl = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    pf = gw/gl if gl > 0 else 999

    print(f"  {n} trades | {wr:.1f}% WR | PF={pf:.2f} | ${total_pnl:+.2f} ({elapsed:.0f}s)")
    strength_dist(trades)
    show_trades(trades)
    passed = total_pnl > 0 and pf >= 1.0
    print(f"\n  RESULT: {'✅ PASSED' if passed else '❌ FAILED'}")
    return passed, trades


# ═══════════════════════════════════════════
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  HELL STRESS TEST v4 — Clean Data + Native 4h HTF                 ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  Symbols: {SYMBOLS} | Base: 15m | HTF: 4h (native)")

    t1_pnl, t1_trades = test_1()
    t3_passed, t3_trades = test_3()
    mc_input = t3_trades if len(t3_trades) > len(t1_trades) else t1_trades
    t2_passed = test_2(mc_input)

    print("\n\n" + "═" * 70)
    print("  FINAL SCORECARD")
    print("═" * 70)
    t1_p = t1_pnl > 0
    print(f"  Test 1 (6 Random Days):  {'✅ PASSED' if t1_p else '❌ FAILED'} (${t1_pnl:+.2f})")
    print(f"  Test 2 (Monte Carlo):    {'✅ PASSED' if t2_passed else '❌ FAILED'}")
    print(f"  Test 3 (30-Day Grind):   {'✅ PASSED' if t3_passed else '❌ FAILED'}")
    all_pass = t1_p and t2_passed and t3_passed
    print(f"\n  {'🎉 ALL TESTS PASSED' if all_pass else '⚠️  SOME TESTS FAILED'}")
    print("═" * 70)
