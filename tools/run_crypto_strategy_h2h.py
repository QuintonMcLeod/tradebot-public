#!/usr/bin/env python3
"""
Crypto Strategy Head-to-Head Backtest
======================================
Step 1: Download fresh 10-day crypto data via CCXT
Step 2: Run each strategy variant against the same data
Step 3: Produce a leaderboard
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / ".."))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.config.models import PerAssetStrategies
from tradebot_sci.simulation.backtester import Backtester

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger("ib_insync").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("tradebot_sci.market.oanda_provider").setLevel(logging.WARNING)

# ─── CONFIG ─────────────────────────────────────────────────
SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BCHUSD", "ZECUSD"]
INITIAL_CAPITAL = 10000.0
DAYS = 7

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "crypto_h2h"

VARIANTS = [
    "robocop",
    "mean_reversion",
    "rubberband_reaper",
    "crypto_rsi_macd",
    "crypto_vwap_reversion",
    "crypto_double_macd",
    "crypto_grid",
    "meta_sci",
]


def download_data(symbols, start_date, end_date):
    """Download crypto candle data using the utils downloader."""
    from tools.utils.downloader import ensure_data_exists

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  📥 Downloading data to {DATA_DIR}")
    print(f"     Period: {start_date.date()} → {end_date.date()}")

    for sym in symbols:
        print(f"     {sym}...", end=" ", flush=True)
        success = ensure_data_exists(sym, "5m", start_date, end_date, str(DATA_DIR))
        print("✅" if success else "❌")

    # Also download 15m for HTF
    for sym in symbols:
        print(f"     {sym} (15m)...", end=" ", flush=True)
        success = ensure_data_exists(sym, "15m", start_date, end_date, str(DATA_DIR))
        print("✅" if success else "❌")


def run_variant(variant, settings, start_date, end_date):
    """Run a single backtest variant."""
    profile = settings.profiles.get("auto_schedule")
    if profile:
        profile.strategy_variant = variant
        if not profile.strategies:
            profile.strategies = PerAssetStrategies()
        profile.strategies.crypto = variant

    # Build data_paths from downloaded files
    data_paths = {}
    for sym in SYMBOLS:
        fpath = DATA_DIR / f"{sym}_5m.json"
        if fpath.exists():
            data_paths[sym] = str(fpath)
            # Also try slash format
            slash_sym = sym.replace("USD", "/USD")
            data_paths[slash_sym] = str(fpath)

    backtester = Backtester(None, settings, None)  # ai_client=None disables expensive API calls
    backtester._is_market_hours_utc = lambda ts: True

    try:
        result = backtester.run_backtest(
            initial_capital=INITIAL_CAPITAL,
            start_date=start_date,
            end_date=end_date,
            symbols=[s.replace("USD", "/USD") for s in SYMBOLS],
            data_paths=data_paths,
        )
        return result
    except Exception as e:
        logging.error(f"[{variant.upper()}] Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 72)
    print("  CRYPTO STRATEGY HEAD-TO-HEAD BACKTEST")
    print("  Old Guard vs New Crypto Suite vs Meta-SCI")
    print("=" * 72)

    settings = load_settings()
    settings.app.profile_name = "auto_schedule"

    end_date = datetime.now(ZoneInfo("UTC"))
    start_date = end_date - timedelta(days=DAYS)
    # Download needs extra lookback for indicator warmup
    download_start = start_date - timedelta(days=3)

    print(f"\n  Period:  {start_date.date()} → {end_date.date()} ({DAYS} days)")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Variants: {len(VARIANTS)}")

    # Step 1: Download fresh data
    download_data(SYMBOLS, download_start, end_date)

    print("\n" + "-" * 72)

    results = {}
    for i, variant in enumerate(VARIANTS, 1):
        tag = variant.upper()
        print(f"\n  [{i}/{len(VARIANTS)}] Running {tag}...")
        result = run_variant(variant, settings, start_date, end_date)
        if result:
            results[variant] = result
            print(f"  ✅ {tag}: {len(result.trades)} trades | "
                  f"P&L: ${result.total_pnl:+,.2f} ({result.total_return_pct:+.1f}%) | "
                  f"WR: {result.win_rate:.0f}%")
        else:
            print(f"  ❌ {tag}: FAILED")

    # ── Leaderboard ─────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  LEADERBOARD")
    print("=" * 72)

    sorted_results = sorted(results.items(), key=lambda x: x[1].total_pnl, reverse=True)

    print(f"\n  {'Rank':<5} {'Strategy':<25} {'Trades':<8} {'P&L':>12} {'Return':>10} {'Win%':>8}")
    print("  " + "-" * 68)

    for rank, (name, res) in enumerate(sorted_results, 1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "  "))
        print(f"  {medal}{rank:<3} {name:<25} {len(res.trades):<8} ${res.total_pnl:>+10,.2f} "
              f"{res.total_return_pct:>+9.1f}% {res.win_rate:>7.0f}%")

    # ── Per-Strategy Breakdown ──────────────────────────────
    print("\n" + "=" * 72)
    print("  DETAILED BREAKDOWN (Top 3)")
    print("=" * 72)

    for rank, (name, res) in enumerate(sorted_results[:3], 1):
        print(f"\n  #{rank} — {name.upper()}")
        print(f"    Final Capital: ${res.final_capital:,.2f}")
        print(f"    Total P&L:     ${res.total_pnl:+,.2f} ({res.total_return_pct:+.2f}%)")
        print(f"    Trades:        {len(res.trades)}")
        print(f"    Win Rate:      {res.win_rate:.1f}%")

        if res.trades:
            wins = [t for t in res.trades if t.pnl > 0]
            losses = [t for t in res.trades if t.pnl <= 0]
            avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

            print(f"    Avg Win:       ${avg_win:+,.2f}")
            print(f"    Avg Loss:      ${avg_loss:+,.2f}")

            sym_pnl = {}
            for t in res.trades:
                sym_pnl[t.symbol] = sym_pnl.get(t.symbol, 0) + t.pnl
            print(f"    Per-Symbol P&L:")
            for sym, pnl in sorted(sym_pnl.items(), key=lambda x: x[1], reverse=True):
                print(f"      {sym}: ${pnl:+,.2f}")

    # ── Meta-SCI vs Best Individual ─────────────────────────
    if "meta_sci" in results and len(sorted_results) > 1:
        meta_result = results["meta_sci"]
        best_name, best_result = sorted_results[0]
        print("\n" + "=" * 72)
        print("  META-SCI vs BEST INDIVIDUAL")
        print("=" * 72)
        if best_name == "meta_sci":
            print(f"\n  🎯 Meta-SCI IS the best performer!")
            if len(sorted_results) > 1:
                runner_up = sorted_results[1]
                print(f"  Runner-up: {runner_up[0].upper()} (${runner_up[1].total_pnl:+,.2f})")
        else:
            delta_pnl = meta_result.total_pnl - best_result.total_pnl
            print(f"\n  Best individual: {best_name.upper()} (${best_result.total_pnl:+,.2f})")
            print(f"  Meta-SCI:        ${meta_result.total_pnl:+,.2f}")
            print(f"  Delta:           ${delta_pnl:+,.2f}")

    print("\n" + "=" * 72)
    print("  BACKTEST COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
