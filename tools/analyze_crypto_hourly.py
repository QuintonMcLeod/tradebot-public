#!/usr/bin/env python3
"""
CRYPTO HOURLY PERFORMANCE ANALYZER
Runs a backtest on crypto data and breaks down P&L by hour-of-day (UTC and EST).
Answers the question: "What time of day does crypto actually show positive results?"
"""

import sys
import os
import unittest.mock
from datetime import datetime, timezone
from collections import defaultdict

# Force Unbuffered Output
sys.stdout.reconfigure(line_buffering=True)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# MOCK ib_insync BEFORE import
sys.modules["ib_insync"] = unittest.mock.MagicMock()

from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings, TradingProfileSettings
from tradebot_sci.simulation.backtester import Backtester

import logging
logging.basicConfig(level=logging.WARNING, format='%(message)s')

def run_analysis():
    print("=" * 70)
    print("CRYPTO HOURLY PERFORMANCE ANALYZER")
    print("=" * 70)

    # --- Configuration (matches crypto_30day_h2h cartridge) ---
    start_date = datetime(2025, 12, 27, 8, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 28, 8, 0, 0, tzinfo=timezone.utc)
    symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"]
    initial_capital = 500.0
    data_dir_name = "crypto_marathon"
    
    strategies_to_test = ["meta_sci", "supply_demand", "bearish_engulfing"]

    for strategy in strategies_to_test:
        print(f"\n{'='*70}")
        print(f"STRATEGY: {strategy.upper()}")
        print(f"{'='*70}")
        
        profile = TradingProfileSettings(
            strategy_variant=strategy,
            candle_timeframe="5m",
            htf_timeframe="1h",
            ltf_timeframe="5m",
            trend_window=18,
            ltf_trend_window=12,
            trend_swing_lookback=3,
            trend_min_swings=2,
            trend_strength_floor=0.25,
            risk_per_trade_pct=0.05,
            max_concurrent_positions=6,
            multi_position_enabled=True,
            max_pyramid_entries=4,
            market_poll_interval_seconds=15,
            ai_decision_interval_seconds=60,
            icc_entry_score_threshold=60.0,
            symbols=symbols,
        )
        
        profile_name = "CryptoHourly"
        settings = Settings(
            app=AppSettings(profile_name=profile_name),
            logging=LoggingSettings(),
            ai=AISettings(provider="openai"),
            market=MarketSettings(symbols=symbols),
            profiles={profile_name: profile},
        )
        
        backtester = Backtester(ib=None, settings=settings, ai_client=None)
        
        # Inject local data provider
        from tools.utils.local_provider import LocalJSONProvider
        data_dir = os.path.join(os.path.dirname(__file__), f"../data/{data_dir_name}")
        backtester.market_provider = LocalJSONProvider(data_dir)
        backtester._is_market_hours_utc = lambda ts: True  # Force all hours open
        
        try:
            result = backtester.run_backtest(
                initial_capital=initial_capital,
                start_date=start_date,
                end_date=end_date,
                symbols=symbols,
            )
        except Exception as e:
            print(f"  [ERROR] Backtest failed: {e}")
            continue
        
        if not result.trades:
            print("  No trades generated.")
            continue
        
        print(f"\n  Total Trades: {len(result.trades)}")
        print(f"  Total P&L: ${result.total_pnl:+,.2f}")
        print(f"  Win Rate: {result.win_rate:.1f}%")
        
        # --- HOURLY ANALYSIS ---
        # Group by ENTRY hour (UTC)
        hourly_pnl_utc = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        # Group by ENTRY hour (EST)
        hourly_pnl_est = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        # Also by symbol
        symbol_pnl = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        # Day of week
        dow_pnl = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        # 4-hour blocks
        block_pnl = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        
        for t in result.trades:
            entry_utc = t.entry_time
            hour_utc = entry_utc.hour
            
            # Convert to EST (UTC-5)
            hour_est = (hour_utc - 5) % 24
            
            # 4-hour block (UTC)
            block = f"{(hour_utc // 4) * 4:02d}:00-{((hour_utc // 4) * 4 + 3) % 24:02d}:59"
            
            is_win = t.pnl > 0
            
            hourly_pnl_utc[hour_utc]["pnl"] += t.pnl
            hourly_pnl_utc[hour_utc]["trades"] += 1
            hourly_pnl_utc[hour_utc]["wins"] += 1 if is_win else 0
            
            hourly_pnl_est[hour_est]["pnl"] += t.pnl
            hourly_pnl_est[hour_est]["trades"] += 1
            hourly_pnl_est[hour_est]["wins"] += 1 if is_win else 0
            
            symbol_pnl[t.symbol]["pnl"] += t.pnl
            symbol_pnl[t.symbol]["trades"] += 1
            symbol_pnl[t.symbol]["wins"] += 1 if is_win else 0
            
            dow_name = entry_utc.strftime("%A")
            dow_pnl[dow_name]["pnl"] += t.pnl
            dow_pnl[dow_name]["trades"] += 1
            dow_pnl[dow_name]["wins"] += 1 if is_win else 0
            
            block_pnl[block]["pnl"] += t.pnl
            block_pnl[block]["trades"] += 1
            block_pnl[block]["wins"] += 1 if is_win else 0
        
        # --- Print UTC Hourly Breakdown ---
        print(f"\n  {'─'*60}")
        print(f"  HOURLY P&L BREAKDOWN (UTC) — Entry Hour")
        print(f"  {'─'*60}")
        print(f"  {'Hour':>6} │ {'P&L':>10} │ {'Trades':>6} │ {'Wins':>5} │ {'WR%':>5} │ Bar")
        print(f"  {'─'*60}")
        
        max_abs_pnl = max(abs(h["pnl"]) for h in hourly_pnl_utc.values()) if hourly_pnl_utc else 1
        
        for hour in range(24):
            if hour not in hourly_pnl_utc:
                continue
            data = hourly_pnl_utc[hour]
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            bar_len = int(abs(data["pnl"]) / max_abs_pnl * 30) if max_abs_pnl > 0 else 0
            bar = ("█" * bar_len) if data["pnl"] >= 0 else ("░" * bar_len)
            sign = "+" if data["pnl"] >= 0 else ""
            color = "🟢" if data["pnl"] > 0 else "🔴" if data["pnl"] < 0 else "⚪"
            print(f"  {hour:02d}:00 │ {sign}${data['pnl']:>8.2f} │ {data['trades']:>6} │ {data['wins']:>5} │ {wr:>4.0f}% │ {color} {bar}")
        
        # --- Print EST Hourly Breakdown ---
        print(f"\n  {'─'*60}")
        print(f"  HOURLY P&L BREAKDOWN (EST) — Entry Hour")
        print(f"  {'─'*60}")
        print(f"  {'Hour':>6} │ {'P&L':>10} │ {'Trades':>6} │ {'Wins':>5} │ {'WR%':>5} │ Bar")
        print(f"  {'─'*60}")
        
        for hour in range(24):
            if hour not in hourly_pnl_est:
                continue
            data = hourly_pnl_est[hour]
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            bar_len = int(abs(data["pnl"]) / max_abs_pnl * 30) if max_abs_pnl > 0 else 0
            bar = ("█" * bar_len) if data["pnl"] >= 0 else ("░" * bar_len)
            sign = "+" if data["pnl"] >= 0 else ""
            color = "🟢" if data["pnl"] > 0 else "🔴" if data["pnl"] < 0 else "⚪"
            # Label with AM/PM
            am_pm = "AM" if hour < 12 else "PM"
            display_hour = hour if hour <= 12 else hour - 12
            if display_hour == 0: display_hour = 12
            print(f"  {hour:02d}:00 │ {sign}${data['pnl']:>8.2f} │ {data['trades']:>6} │ {data['wins']:>5} │ {wr:>4.0f}% │ {color} {bar}  ({display_hour}{am_pm})")
        
        # --- 4-Hour Block Summary ---
        print(f"\n  {'─'*60}")
        print(f"  4-HOUR BLOCK SUMMARY (UTC)")
        print(f"  {'─'*60}")
        for block_name in sorted(block_pnl.keys()):
            data = block_pnl[block_name]
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            sign = "+" if data["pnl"] >= 0 else ""
            color = "🟢" if data["pnl"] > 0 else "🔴"
            print(f"  {block_name:>12} │ {sign}${data['pnl']:>8.2f} │ {data['trades']:>4} trades │ {wr:.0f}% WR │ {color}")
        
        # --- Day of Week ---
        print(f"\n  {'─'*60}")
        print(f"  DAY OF WEEK P&L")
        print(f"  {'─'*60}")
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in day_order:
            if day not in dow_pnl:
                continue
            data = dow_pnl[day]
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            sign = "+" if data["pnl"] >= 0 else ""
            color = "🟢" if data["pnl"] > 0 else "🔴"
            print(f"  {day:>12} │ {sign}${data['pnl']:>8.2f} │ {data['trades']:>4} trades │ {wr:.0f}% WR │ {color}")
        
        # --- By Symbol ---
        print(f"\n  {'─'*60}")
        print(f"  PER-SYMBOL P&L")
        print(f"  {'─'*60}")
        for sym in sorted(symbol_pnl.keys(), key=lambda s: symbol_pnl[s]["pnl"], reverse=True):
            data = symbol_pnl[sym]
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            sign = "+" if data["pnl"] >= 0 else ""
            color = "🟢" if data["pnl"] > 0 else "🔴"
            print(f"  {sym:>10} │ {sign}${data['pnl']:>8.2f} │ {data['trades']:>4} trades │ {wr:.0f}% WR │ {color}")
        
        # --- BEST HOURS SUMMARY ---
        print(f"\n  {'─'*60}")
        print(f"  🏆 TOP 5 PROFITABLE HOURS (EST)")
        print(f"  {'─'*60}")
        sorted_est_hours = sorted(hourly_pnl_est.items(), key=lambda x: x[1]["pnl"], reverse=True)
        for hour, data in sorted_est_hours[:5]:
            if data["pnl"] <= 0:
                break
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            am_pm = "AM" if hour < 12 else "PM"
            display_hour = hour if hour <= 12 else hour - 12
            if display_hour == 0: display_hour = 12
            print(f"  {display_hour:>2}{am_pm} ({hour:02d}:00) │ +${data['pnl']:>8.2f} │ {data['trades']:>4} trades │ {wr:.0f}% WR │ 🟢")
        
        print(f"\n  {'─'*60}")
        print(f"  💀 TOP 5 LOSING HOURS (EST)")
        print(f"  {'─'*60}")
        sorted_est_hours_worst = sorted(hourly_pnl_est.items(), key=lambda x: x[1]["pnl"])
        for hour, data in sorted_est_hours_worst[:5]:
            if data["pnl"] >= 0:
                break
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            am_pm = "AM" if hour < 12 else "PM"
            display_hour = hour if hour <= 12 else hour - 12
            if display_hour == 0: display_hour = 12
            print(f"  {display_hour:>2}{am_pm} ({hour:02d}:00) │ -${abs(data['pnl']):>8.2f} │ {data['trades']:>4} trades │ {wr:.0f}% WR │ 🔴")

    print(f"\n{'='*70}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*70}")

if __name__ == "__main__":
    run_analysis()
