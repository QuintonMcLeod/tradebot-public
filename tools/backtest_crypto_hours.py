#!/usr/bin/env python3
"""
CRYPTO MARKET HOURS A/B BACKTEST
Compares Meta-SCI performance: 24/7 trading vs 12PM-6AM EST (kill zone enforced).
"""

import sys
import os
import unittest.mock
from datetime import datetime, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.modules["ib_insync"] = unittest.mock.MagicMock()

from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings
from tradebot_sci.simulation.backtester import Backtester
from tools.utils.local_provider import LocalJSONProvider

import logging
logging.basicConfig(level=logging.WARNING, format='%(message)s')

EST = ZoneInfo("America/New_York")

def is_crypto_hours(ts: datetime) -> bool:
    """Returns True if timestamp is within crypto market hours (12PM-6AM EST)."""
    local = ts.astimezone(EST)
    hour = local.hour
    # Open: 12:00 PM (12) to 5:59 AM (close at 6:00)
    # Overnight window: hour >= 12 OR hour < 6
    return hour >= 12 or hour < 6

def run_backtest(label: str, market_hours_filter=None):
    start_date = datetime(2025, 12, 27, 8, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 28, 8, 0, 0, tzinfo=timezone.utc)
    symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"]
    initial_capital = 500.0

    profile = TradingProfileSettings(
        strategy_variant="meta_sci",
        candle_timeframe="5m", htf_timeframe="1h", ltf_timeframe="5m",
        trend_window=18, ltf_trend_window=12, trend_swing_lookback=3,
        trend_min_swings=2, trend_strength_floor=0.25, risk_per_trade_pct=0.05,
        max_concurrent_positions=6, multi_position_enabled=True, max_pyramid_entries=4,
        market_poll_interval_seconds=15, ai_decision_interval_seconds=60,
        icc_entry_score_threshold=70.0, symbols=symbols,
    )
    
    settings = Settings(
        app=AppSettings(profile_name="X"), logging=LoggingSettings(),
        ai=AISettings(provider="openai"), market=MarketSettings(symbols=symbols),
        profiles={"X": profile},
    )
    
    bt = Backtester(ib=None, settings=settings, ai_client=None)
    bt.market_provider = LocalJSONProvider(
        os.path.join(os.path.dirname(__file__), "../data/crypto_marathon")
    )
    
    if market_hours_filter:
        bt._is_market_hours_utc = market_hours_filter
    else:
        bt._is_market_hours_utc = lambda ts: True  # 24/7
    
    result = bt.run_backtest(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        symbols=symbols,
    )
    return result, initial_capital

def print_results(label, result, initial_capital):
    trades = result.trades
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    
    total_pnl = sum(t.pnl for t in trades)
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0
    profit_factor = (sum(t.pnl for t in wins) / abs(sum(t.pnl for t in losses))) if losses and sum(t.pnl for t in losses) != 0 else float('inf')
    
    # Max drawdown
    equity = initial_capital
    peak = equity
    max_dd = 0
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)
    
    # Per-symbol breakdown
    sym_pnl = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for t in trades:
        sym_pnl[t.symbol]["pnl"] += t.pnl
        sym_pnl[t.symbol]["trades"] += 1
        sym_pnl[t.symbol]["wins"] += 1 if t.pnl > 0 else 0
    
    # Hourly (EST)
    hourly = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for t in trades:
        h = t.entry_time.astimezone(EST).hour
        hourly[h]["pnl"] += t.pnl
        hourly[h]["trades"] += 1
        hourly[h]["wins"] += 1 if t.pnl > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total Trades:     {len(trades)}")
    print(f"  Wins / Losses:    {len(wins)} / {len(losses)}")
    print(f"  Win Rate:         {win_rate:.1f}%")
    print(f"  Total P&L:        ${total_pnl:+,.2f}")
    print(f"  Return:           {(total_pnl/initial_capital)*100:+.2f}%")
    print(f"  Avg Win:          ${avg_win:+.4f}")
    print(f"  Avg Loss:         ${avg_loss:+.4f}")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"  Max Drawdown:     {max_dd:.2f}%")
    print(f"  Final Capital:    ${initial_capital + total_pnl:,.2f}")
    
    print(f"\n  {'─'*50}")
    print(f"  PER-SYMBOL BREAKDOWN")
    print(f"  {'─'*50}")
    for sym in sorted(sym_pnl.keys(), key=lambda s: sym_pnl[s]["pnl"], reverse=True):
        d = sym_pnl[sym]
        wr = (d["wins"]/d["trades"]*100) if d["trades"] else 0
        sign = "+" if d["pnl"] >= 0 else ""
        icon = "🟢" if d["pnl"] > 0 else "🔴"
        print(f"  {sym:>10} │ {sign}${d['pnl']:>8.2f} │ {d['trades']:>4} trades │ {wr:.0f}% WR │ {icon}")

    print(f"\n  {'─'*50}")
    print(f"  HOURLY P&L (EST)")
    print(f"  {'─'*50}")
    for h in range(24):
        if h not in hourly: continue
        d = hourly[h]
        wr = (d["wins"]/d["trades"]*100) if d["trades"] else 0
        sign = "+" if d["pnl"] >= 0 else ""
        icon = "🟢" if d["pnl"] > 0 else "🔴"
        am_pm = "AM" if h < 12 else "PM"
        dh = h if h <= 12 else h - 12
        if dh == 0: dh = 12
        print(f"  {h:02d}:00 │ {sign}${d['pnl']:>8.2f} │ {d['trades']:>4} trades │ {wr:.0f}% WR │ {icon}  ({dh}{am_pm})")
    
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "pnl": total_pnl, "win_rate": win_rate, "profit_factor": profit_factor,
        "max_dd": max_dd, "final_capital": initial_capital + total_pnl,
    }

def main():
    print("=" * 60)
    print("  CRYPTO MARKET HOURS A/B BACKTEST")
    print("  Strategy: META-SCI │ Period: 30 days │ 6 symbols")
    print("=" * 60)
    
    print("\n⏳ Running 24/7 baseline...")
    r_24_7, cap = run_backtest("24/7 (No Restrictions)")
    stats_24_7 = print_results("📊 BASELINE: 24/7 Trading", r_24_7, cap)
    
    print("\n⏳ Running with Crypto Market Hours (12PM-6AM EST)...")
    r_hours, _ = run_backtest("12PM-6AM EST", market_hours_filter=is_crypto_hours)
    stats_hours = print_results("📊 WITH CRYPTO HOURS: 12PM-6AM EST", r_hours, cap)
    
    # --- COMPARISON ---
    print(f"\n{'='*60}")
    print(f"  ⚔️  HEAD-TO-HEAD COMPARISON")
    print(f"{'='*60}")
    
    metrics = [
        ("Total Trades",   f"{stats_24_7['trades']}", f"{stats_hours['trades']}"),
        ("Win Rate",       f"{stats_24_7['win_rate']:.1f}%", f"{stats_hours['win_rate']:.1f}%"),
        ("Total P&L",      f"${stats_24_7['pnl']:+,.2f}", f"${stats_hours['pnl']:+,.2f}"),
        ("Profit Factor",  f"{stats_24_7['profit_factor']:.2f}", f"{stats_hours['profit_factor']:.2f}"),
        ("Max Drawdown",   f"{stats_24_7['max_dd']:.2f}%", f"{stats_hours['max_dd']:.2f}%"),
        ("Final Capital",  f"${stats_24_7['final_capital']:,.2f}", f"${stats_hours['final_capital']:,.2f}"),
    ]
    
    print(f"  {'Metric':>20} │ {'24/7':>15} │ {'Market Hours':>15} │ Better")
    print(f"  {'─'*70}")
    for name, v1, v2 in metrics:
        # Simple heuristic for "better"
        if name == "Max Drawdown":
            better = "⏰" if stats_hours['max_dd'] < stats_24_7['max_dd'] else "🌐"
        elif name == "Total Trades":
            better = "—"
        else:
            better = "⏰" if stats_hours.get(name.lower().replace(' ','_'), 0) >= stats_24_7.get(name.lower().replace(' ','_'), 0) else "🌐"
        
        # Better pick for P&L
        if name == "Total P&L":
            better = "⏰" if stats_hours['pnl'] > stats_24_7['pnl'] else "🌐"
        elif name == "Win Rate":
            better = "⏰" if stats_hours['win_rate'] > stats_24_7['win_rate'] else "🌐"
        elif name == "Profit Factor":
            better = "⏰" if stats_hours['profit_factor'] > stats_24_7['profit_factor'] else "🌐"
        elif name == "Final Capital":
            better = "⏰" if stats_hours['final_capital'] > stats_24_7['final_capital'] else "🌐"
            
        print(f"  {name:>20} │ {v1:>15} │ {v2:>15} │ {better}")
    
    pnl_diff = stats_hours['pnl'] - stats_24_7['pnl']
    trades_saved = stats_24_7['trades'] - stats_hours['trades']
    print(f"\n  💰 P&L Improvement:    ${pnl_diff:+,.2f}")
    print(f"  🛡️  Trades Avoided:    {trades_saved}")
    print(f"  📈 WR Delta:           {stats_hours['win_rate'] - stats_24_7['win_rate']:+.1f}%")
    
    if pnl_diff > 0:
        print(f"\n  ✅ VERDICT: Crypto Market Hours SAVED ${pnl_diff:.2f} over 30 days!")
    else:
        print(f"\n  ⚠️  VERDICT: Market Hours slightly reduced P&L by ${abs(pnl_diff):.2f}")
        print(f"     (But may still reduce drawdown risk)")
    
    print(f"\n{'='*60}")

if __name__ == "__main__":
    main()
