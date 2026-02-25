#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║             CONDUCTOR STRESS TEST — Multi-Window Analysis                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

Tests the Forex Conductor across multiple time windows and reports:
- Per-strategy breakdown (which sub-strategies bleed money?)
- Loss streak analysis (max consecutive losses, recovery patterns)
- Session analysis (which hours are profitable/unprofitable?)
- Consistency score (does it work across all windows or only some?)
"""
import sys, os, logging, time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest.mock
sys.modules["ib_insync"] = unittest.mock.MagicMock()
os.environ["TRADING_CONFIRMATION"] = "YES"

logging.basicConfig(level=logging.WARNING)

from tools.utils.local_provider import LocalJSONProvider
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import (
    Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
    TradingProfileSettings,
)


def build_config():
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="15m",
        htf_timeframe="1h",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        min_hold_hours=0.08,   # 5 minutes — cut losers fast
        max_hold_hours=0,
        risk_per_trade_pct=0.01,
        block_counter_trend_entries=True,
        trend_strength_floor=0.20,
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
    )
    settings = Settings(
        app=AppSettings(profile_name="A"),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=["EURUSD", "GBPUSD"]),
        profiles={"A": profile},
    )
    return settings


def run_backtest(days, end_offset_days=0):
    """Run a backtest for `days` ending `end_offset_days` ago."""
    settings = build_config()
    bt = Backtester(ib=None, settings=settings, ai_client=None)
    bt.market_provider = LocalJSONProvider("data/audit")
    bt._is_market_hours_utc = lambda ts: True

    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now - timedelta(days=end_offset_days)
    start = end - timedelta(days=days)
    return bt.run_backtest(initial_capital=7500, start_date=start, end_date=end, wind_down_days=0), start, end


def analyze(result, start, end, label):
    """Print detailed analysis of a backtest result."""
    trades = result.trades
    n = len(trades)
    if n == 0:
        print(f"\n{'='*70}")
        print(f"  {label}: NO TRADES")
        print(f"{'='*70}")
        return {}

    wins = sum(1 for t in trades if t.pnl > 0)
    wr = wins / n * 100
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    avg_w = sum(t.pnl for t in winners) / len(winners) if winners else 0
    avg_l = sum(t.pnl for t in losers) / len(losers) if losers else 0
    rr = abs(avg_w / avg_l) if avg_l != 0 else 999

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  Window: {start.strftime('%b %d')} – {end.strftime('%b %d')}")
    print(f"{'='*70}")
    print(f"  {n} trades | {wr:.0f}% WR | R:R {rr:.1f}:1 | PnL ${result.total_pnl:+.2f} | Max DD {result.max_drawdown_pct:.1f}%")
    print(f"  Avg Win: ${avg_w:.2f} | Avg Loss: ${avg_l:.2f}")

    # Per-strategy breakdown
    by_strat = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0, "trades": []})
    for t in trades:
        gates = getattr(t, "entry_gates", None) or {}
        meta = gates.get("meta_source", "?")
        d = by_strat[meta]
        if t.pnl > 0:
            d["w"] += 1
        else:
            d["l"] += 1
        d["pnl"] += t.pnl
        d["trades"].append(t)

    print(f"\n  {'Strategy':<22} {'Trades':>6} {'WR':>6} {'PnL':>10} {'Avg W':>8} {'Avg L':>8}")
    print(f"  {'─'*22} {'─'*6} {'─'*6} {'─'*10} {'─'*8} {'─'*8}")
    for name, d in sorted(by_strat.items(), key=lambda x: x[1]["pnl"]):
        total = d["w"] + d["l"]
        wr2 = d["w"] / total * 100 if total else 0
        strat_winners = [t for t in d["trades"] if t.pnl > 0]
        strat_losers = [t for t in d["trades"] if t.pnl <= 0]
        s_avg_w = sum(t.pnl for t in strat_winners) / len(strat_winners) if strat_winners else 0
        s_avg_l = sum(t.pnl for t in strat_losers) / len(strat_losers) if strat_losers else 0
        print(f"  {name:<22} {total:>6} {wr2:>5.0f}% ${d['pnl']:>9.2f} ${s_avg_w:>7.2f} ${s_avg_l:>7.2f}")

    # Per-trade breakdown
    print(f"\n  {'#':>3} {'Date':<12} {'Symbol':<8} {'Dir':<6} {'PnL':>10} {'Entry':>10} {'Exit':>10} {'Reason':<10}")
    print(f"  {'─'*3} {'─'*12} {'─'*8} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    sorted_trades = sorted(trades, key=lambda t: t.entry_time)
    running = 0
    for i, t in enumerate(sorted_trades, 1):
        running += t.pnl
        icon = "🟢" if t.pnl > 0 else "🔴"
        date_str = t.entry_time.strftime("%b %d %H:%M") if t.entry_time else "?"
        print(
            f"  {i:>3} {date_str:<12} {t.symbol:<8} {t.direction:<6} "
            f"${t.pnl:>+9.2f} ${t.entry_price:>9.5f} ${t.exit_price:>9.5f} "
            f"{t.exit_reason:<10} {icon} (cum: ${running:>+.2f})"
        )

    # Loss streak analysis
    max_streak = 0
    current_streak = 0
    streaks = []
    for t in trades:
        if t.pnl <= 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            if current_streak > 0:
                streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        streaks.append(current_streak)

    streak_damage = []
    cs = 0
    cs_pnl = 0
    for t in trades:
        if t.pnl <= 0:
            cs += 1
            cs_pnl += t.pnl
        else:
            if cs > 0:
                streak_damage.append((cs, cs_pnl))
            cs = 0
            cs_pnl = 0
    if cs > 0:
        streak_damage.append((cs, cs_pnl))

    print(f"\n  Loss Streaks: max={max_streak}, all={streaks}")
    if streak_damage:
        worst = min(streak_damage, key=lambda x: x[1])
        print(f"  Worst streak: {worst[0]} consecutive losses = ${worst[1]:.2f}")

    return {
        "label": label,
        "pnl": result.total_pnl,
        "trades": n,
        "wr": wr,
        "rr": rr,
        "max_dd": result.max_drawdown_pct,
        "max_streak": max_streak,
        "by_strat": {k: {"pnl": v["pnl"], "trades": v["w"] + v["l"], "wr": v["w"] / (v["w"] + v["l"]) * 100 if (v["w"] + v["l"]) else 0} for k, v in by_strat.items()},
    }


def main():
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║             CONDUCTOR STRESS TEST — Multi-Window                    ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    windows = [
        (7, 0, "Week 1 (most recent 7d)"),
        (7, 7, "Week 2 (7-14 days ago)"),
        (7, 14, "Week 3 (14-21 days ago)"),
        (7, 21, "Week 4 (21-28 days ago)"),
        (14, 0, "Full 14 days (most recent)"),
    ]

    all_results = []
    for days, offset, label in windows:
        try:
            t0 = time.time()
            result, start, end = run_backtest(days, offset)
            elapsed = time.time() - t0
            analysis = analyze(result, start, end, f"{label} ({elapsed:.1f}s)")
            all_results.append(analysis)
        except Exception as e:
            print(f"\n  [ERROR] {label}: {e}")
            import traceback
            traceback.print_exc()

    # Summary table
    print(f"\n{'='*70}")
    print(f"  CONSISTENCY SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Window':<35} {'PnL':>8} {'Trades':>6} {'WR':>5} {'R:R':>6} {'MaxDD':>6} {'Streak':>6}")
    print(f"  {'─'*35} {'─'*8} {'─'*6} {'─'*5} {'─'*6} {'─'*6} {'─'*6}")
    profitable = 0
    for r in all_results:
        if not r:
            continue
        mark = "✅" if r["pnl"] > 0 else "❌"
        if r["pnl"] > 0:
            profitable += 1
        print(f"  {r['label']:<35} ${r['pnl']:>7.0f} {r['trades']:>6} {r['wr']:>4.0f}% {r['rr']:>5.1f}:1 {r['max_dd']:>5.1f}% {r['max_streak']:>5} {mark}")

    total = len([r for r in all_results if r])
    print(f"\n  Consistency: {profitable}/{total} windows profitable")
    if profitable == total:
        print("  ✅ FULLY CONSISTENT — strategy works across all tested windows")
    elif profitable >= total * 0.6:
        print("  ⚠️  PARTIALLY CONSISTENT — works in most but not all windows")
    else:
        print("  ❌ INCONSISTENT — fails in most windows, needs fundamental fixes")


if __name__ == "__main__":
    main()
