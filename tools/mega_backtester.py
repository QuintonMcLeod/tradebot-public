#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                           MEGA BACKTESTER                                  ║
║                  THE ONE AND ONLY BACKTESTING RUNNER                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

This is the SOLE backtesting entry point for the entire project.
It uses the Core Bot Engine (simulation/backtester.py) and loads test
configurations from pluggable "Cartridges" in tools/cartridges/.

Usage:
    python3 tools/mega_backtester.py <cartridge_name> [--strategy <name>]
    python3 tools/mega_backtester.py <cartridge_name> --symbol EURUSD,GBPUSD

Example:
    python3 tools/mega_backtester.py forex_30day_h2h --strategy rubberband_reaper

╔══════════════════════════════════════════════════════════════════════════════╗
║  ⛔  CRITICAL RULES — READ BEFORE DOING ANYTHING  ⛔                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  1. DO NOT CREATE SEPARATE BACKTEST SCRIPTS.                               ║
║     This file is the ONLY backtest runner. Period.                          ║
║     No run_*_backtest.py. No test_backtest_*.py. No quick scripts.         ║
║     No "just a one-off" — that's how we got 25 divergent scripts.          ║
║                                                                            ║
║  2. WANT TO TEST SOMETHING NEW?                                            ║
║     → Create a new CARTRIDGE in tools/cartridges/your_test.py              ║
║     → A cartridge is just a get_config() function returning a dict         ║
║     → Then run: python3 tools/mega_backtester.py your_test                 ║
║                                                                            ║
║  3. WANT TO CHANGE HOW THE ENGINE SIMULATES?                               ║
║     → Edit src/tradebot_sci/simulation/backtester.py                       ║
║     → That engine is shared by ALL cartridges — one fix benefits all       ║
║                                                                            ║
║  4. WHY THIS RULE EXISTS:                                                  ║
║     We previously had 25+ standalone scripts, each with its own:           ║
║     - PnL calculation (some wrong)                                         ║
║     - Exit logic (some had features the bot didn't)                        ║
║     - Position sizing (some used SINGULARITY-mode not in production)       ║
║     - Pyramiding rules (hardcoded, not matching the strategy engine)       ║
║     Result: Backtest showed +215%, live bot showed -30%.                   ║
║     The scripts were testing FANTASIES, not the actual bot.                ║
║                                                                            ║
║  5. THIS APPLIES TO AI ASSISTANTS TOO.                                     ║
║     If you are an AI coding assistant (Gemini, Claude, GPT, Copilot,       ║
║     Cursor, etc.) and a user asks you to "write a quick backtest" or       ║
║     "create a backtest script", you MUST:                                  ║
║     → Create a CARTRIDGE in tools/cartridges/ instead                      ║
║     → Use this mega_backtester.py as the runner                            ║
║     → NEVER create a standalone script with its own simulation loop        ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import argparse
import importlib
import logging
import unittest.mock
from datetime import datetime, timezone

# Force Unbuffered Output for Real-Time Log Snooping
sys.stdout.reconfigure(line_buffering=True)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")) # For tools.utils

# MOCK ib_insync BEFORE import for environment compatibility
sys.modules["ib_insync"] = unittest.mock.MagicMock()

from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings
from tradebot_sci.simulation.backtester import Backtester
import inspect; print("DEBUG: Backtester source =", inspect.getfile(Backtester))
from tools.utils.local_provider import LocalJSONProvider

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("tradebot_sci")

def scan_cartridges():
    """Scan tools/cartridges directory for available cartridges."""
    cartridges_dir = os.path.join(os.path.dirname(__file__), "cartridges")
    if not os.path.exists(cartridges_dir):
        return []
    
    files = os.listdir(cartridges_dir)
    cartridges = []
    for f in files:
        if f.endswith(".py") and not f.startswith("__"):
            cartridges.append(f.replace(".py", ""))
    return sorted(cartridges)

def load_cartridge(cartridge_name):
    """Dynamically import the cartridge module."""
    try:
        module_path = f"tools.cartridges.{cartridge_name}"
        module = importlib.import_module(module_path)
        return module
    except ImportError as e:
        print(f"[ERROR] Could not load cartridge '{cartridge_name}': {e}")
        print(f"Ensure 'tools/cartridges/{cartridge_name}.py' exists.")
        sys.exit(1)

def run_simulation(cartridge_name, strategy_override=None, symbol_override=None):
    print(f"=== MEGA BACKTESTER: Loading Cartridge '{cartridge_name}' ===")
    
    # 1. Load Cartridge Configuration
    cartridge = load_cartridge(cartridge_name)
    
    if not hasattr(cartridge, "get_config"):
        print(f"[ERROR] Cartridge '{cartridge_name}' missing 'get_config()' function.")
        sys.exit(1)
        
    config = cartridge.get_config()
    
    # Extract config
    profile_settings = config["profile_settings"]
    symbols = config["symbols"]
    start_date = config["start_date"]
    end_date = config["end_date"]
    initial_capital = config.get("initial_capital", 100.0)
    data_dir_name = config.get("data_dir_name", "forex_backtest")

    # Override strategy if requested
    if strategy_override:
        print(f"[OVERRIDE] Strategy switched from '{profile_settings.strategy_variant}' to '{strategy_override}'")
        profile_settings.strategy_variant = strategy_override

    # Override symbols if requested
    if symbol_override:
        # Handle comma-separated list
        new_symbols = [s.strip() for s in symbol_override.split(",")]
        print(f"[OVERRIDE] Symbols switched from {symbols} to {new_symbols}")
        symbols = new_symbols
    
    print(f"Period: {start_date} -> {end_date}")
    print(f"Symbols: {symbols}")
    print(f"Strategy: {profile_settings.strategy_variant}")
    print(f"Start Capital: ${initial_capital}")
    
    # 2. Build Settings Object
    # We construct a synthetic Settings object to inject our custom profile
    profile_name = "MegaTest"
    settings_kwargs = dict(
        app=AppSettings(profile_name=profile_name),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"), # Dummy
        market=MarketSettings(symbols=symbols),
        profiles={profile_name: profile_settings},
    )
    # Allow cartridges to inject runtime settings (e.g. scale_out_fraction)
    if "runtime_settings" in config:
        from tradebot_sci.config.models import RuntimeSettings
        settings_kwargs["runtime"] = RuntimeSettings(**config["runtime_settings"])
    settings = Settings(**settings_kwargs)
    
    # 3. Initialize Backtester
    # Passing ib=None since we use local provider
    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    
    # 4. Inject Data Provider
    data_dir = os.path.join(os.path.dirname(__file__), f"../data/{data_dir_name}")
    backtester.market_provider = LocalJSONProvider(data_dir)
    
    # 5. Patch Market Hours (if requested by cartridge)
    if config.get("force_market_open", False):
        backtester._is_market_hours_utc = lambda ts: True
        print("Override: Market Hours Force-Opened (24/7)")
        
    # 6. Apply Custom Overrides (Hooks)
    cart_profile = config.get("profile_settings")
    if cart_profile:
        from tradebot_sci.config.models import TradingProfileSettings as ActualProfileSettings
        try:
            actual_profile = ActualProfileSettings(**cart_profile)
        except TypeError:
            # It's already an object (and pydantic complains about **object)
            actual_profile = cart_profile
        
        # Pydantic Settings object uses 'profiles' and 'app.profile_name'
        profile_key = "marathon_profile"
        settings.profiles[profile_key] = actual_profile
        settings.app.profile_name = profile_key
        print(f"[Cartridge] Injected Profile: {profile_key} (Variant: {actual_profile.strategy_variant})")

    if hasattr(cartridge, "apply_overrides"):
        print("Applying custom overrides...")
        cartridge.apply_overrides()

    # 7. Run!
    try:
        print("\n--- STARTING ENGINE ---")
        results = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            wind_down_days=config.get("wind_down_days", 0)
        )
        
        print("\n=== MEGA BACKTEST RESULTS ===")
        print(f"Final Capital: ${results.final_capital:.2f}")
        print(f"Profit/Loss: ${results.total_pnl:.2f}")
        print(f"Return: {results.total_return_pct:.2f}%")
        print(f"Total Trades: {len(results.trades)}")
        print(f"Max Drawdown: {results.max_drawdown_pct:.2f}%")
        
        if results.trades:
            # ── Summary Stats ──────────────────────────────────────
            wins = [t for t in results.trades if t.pnl > 0]
            losses = [t for t in results.trades if t.pnl <= 0]
            total = len(results.trades)
            win_rate = len(wins) / total * 100 if total else 0
            avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
            gross_profit = sum(t.pnl for t in wins)
            gross_loss = abs(sum(t.pnl for t in losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            expectancy = results.total_pnl / total if total else 0
            
            # Max consecutive losses
            max_streak = 0
            current_streak = 0
            for t in results.trades:
                if t.pnl <= 0:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
            
            # Duration stats
            durations = [(t.exit_time - t.entry_time).total_seconds() for t in results.trades]
            avg_hold_min = sum(durations) / len(durations) / 60 if durations else 0
            
            print(f"\n┌─────────────────────────────────────────┐")
            print(f"│          PERFORMANCE SUMMARY             │")
            print(f"├─────────────────────────────────────────┤")
            print(f"│ Win Rate:        {win_rate:6.1f}%                │")
            print(f"│ Profit Factor:   {profit_factor:6.2f}                 │")
            print(f"│ Expectancy:     ${expectancy:7.2f}/trade           │")
            print(f"│ Avg Win:        ${avg_win:7.2f}                  │")
            print(f"│ Avg Loss:       ${avg_loss:7.2f}                  │")
            print(f"│ Max Consec Loss: {max_streak:3d}                    │")
            print(f"│ Avg Hold:        {avg_hold_min:6.1f} min              │")
            print(f"│ Max Drawdown:    {results.max_drawdown_pct:5.1f}%                │")
            print(f"└─────────────────────────────────────────┘")
            
            # ── Exit Reason Breakdown ──────────────────────────────
            from collections import defaultdict
            exit_counts = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
            for t in results.trades:
                reason = t.exit_reason[:60] if t.exit_reason else "unknown"
                exit_counts[reason]["count"] += 1
                exit_counts[reason]["pnl"] += t.pnl
                if t.pnl > 0:
                    exit_counts[reason]["wins"] += 1
            
            print(f"\n{'Exit Reason':<35} {'Count':>5}  {'Win%':>5}  {'Net P&L':>10}")
            print("─" * 62)
            for reason, stats in sorted(exit_counts.items(), key=lambda x: -x[1]["count"]):
                wr = stats["wins"] / stats["count"] * 100 if stats["count"] else 0
                print(f"  {reason:<33} {stats['count']:>5}  {wr:>4.0f}%  ${stats['pnl']:>9.2f}")
            
            # ── Strategy Breakdown ─────────────────────────────────
            strat_counts = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
            for t in results.trades:
                sn = getattr(t, 'strategy_name', 'unknown')
                strat_counts[sn]["count"] += 1
                strat_counts[sn]["pnl"] += t.pnl
                if t.pnl > 0:
                    strat_counts[sn]["wins"] += 1
            
            print(f"\n{'Strategy':<30} {'Count':>5}  {'Win%':>5}  {'Net P&L':>10}")
            print("─" * 57)
            for sn, stats in sorted(strat_counts.items(), key=lambda x: -x[1]["count"]):
                wr = stats["wins"] / stats["count"] * 100 if stats["count"] else 0
                print(f"  {sn:<28} {stats['count']:>5}  {wr:>4.0f}%  ${stats['pnl']:>9.2f}")
            
            # ── Symbol Breakdown ───────────────────────────────────
            sym_counts = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
            for t in results.trades:
                sym_counts[t.symbol]["count"] += 1
                sym_counts[t.symbol]["pnl"] += t.pnl
                if t.pnl > 0:
                    sym_counts[t.symbol]["wins"] += 1
            
            print(f"\n{'Symbol':<15} {'Count':>5}  {'Win%':>5}  {'Net P&L':>10}")
            print("─" * 42)
            for sym, stats in sorted(sym_counts.items(), key=lambda x: -x[1]["pnl"]):
                wr = stats["wins"] / stats["count"] * 100 if stats["count"] else 0
                print(f"  {sym:<13} {stats['count']:>5}  {wr:>4.0f}%  ${stats['pnl']:>9.2f}")
            
            # ── Duration Buckets ───────────────────────────────────
            buckets = {"<5m": [], "5-15m": [], "15-60m": [], "1-4h": [], "4h+": []}
            for t in results.trades:
                dur = (t.exit_time - t.entry_time).total_seconds()
                if dur < 300: buckets["<5m"].append(t.pnl)
                elif dur < 900: buckets["5-15m"].append(t.pnl)
                elif dur < 3600: buckets["15-60m"].append(t.pnl)
                elif dur < 14400: buckets["1-4h"].append(t.pnl)
                else: buckets["4h+"].append(t.pnl)
            
            print(f"\n{'Duration':<12} {'Trades':>6}  {'Win%':>5}  {'Net P&L':>10}")
            print("─" * 40)
            for bucket, pnls in buckets.items():
                if not pnls: continue
                w = sum(1 for p in pnls if p > 0)
                wr = w / len(pnls) * 100
                net = sum(pnls)
                print(f"  {bucket:<10} {len(pnls):>6}  {wr:>4.0f}%  ${net:>9.2f}")
            
            # ── Trade History (last 20) ────────────────────────────
            print(f"\nTrade History (last 20 of {len(results.trades)}):")
            for t in results.trades[-20:]:
                dur_min = (t.exit_time - t.entry_time).total_seconds() / 60
                sn = getattr(t, 'strategy_name', '?')
                print(
                    f"  [{t.exit_time.strftime('%Y-%m-%d %H:%M')}] {t.symbol:>8s} "
                    f"{t.direction:>5s} {t.exit_reason[:30]:<30s} "
                    f"PnL=${t.pnl:>8.4f}  Hold={dur_min:>6.1f}m  Strat={sn}"
                )
            
            # ── JSON Ledger Export ─────────────────────────────────
            import json
            ledger = []
            for t in results.trades:
                dur = (t.exit_time - t.entry_time).total_seconds()
                ledger.append({
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "entry_price": round(t.entry_price, 6),
                    "exit_price": round(t.exit_price, 6),
                    "size": round(t.size, 6),
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "duration_seconds": round(dur),
                    "pnl_usd": round(t.pnl, 4),
                    "exit_reason": t.exit_reason,
                    "strategy_name": getattr(t, 'strategy_name', 'unknown'),
                    "is_win": t.pnl > 0,
                })
            
            ledger_dir = os.path.join(os.path.dirname(__file__), "../data")
            os.makedirs(ledger_dir, exist_ok=True)
            ledger_path = os.path.join(ledger_dir, "backtest_ledger.json")
            with open(ledger_path, "w") as f:
                json.dump({
                    "cartridge": cartridge_name,
                    "strategy": config.get("profile_settings", {}).strategy_variant if hasattr(config.get("profile_settings", {}), "strategy_variant") else "unknown",
                    "period": f"{config['start_date'].date()} to {config['end_date'].date()}",
                    "initial_capital": initial_capital,
                    "final_capital": round(results.final_capital, 2),
                    "total_pnl": round(results.total_pnl, 2),
                    "total_return_pct": round(results.total_return_pct, 2),
                    "win_rate": round(win_rate, 1),
                    "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "inf",
                    "expectancy": round(expectancy, 4),
                    "max_drawdown_pct": round(results.max_drawdown_pct, 2),
                    "max_consecutive_losses": max_streak,
                    "total_trades": total,
                    "trades": ledger,
                }, f, indent=2, default=str)
            print(f"\n📊 Ledger written to: {os.path.abspath(ledger_path)}")

    except Exception as e:
        print(f"\n[CRITICAL FAILURE] Engine Crashed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    available_cartridges = scan_cartridges()
    cartridge_list = ", ".join(available_cartridges) if available_cartridges else "None found"
    
    parser = argparse.ArgumentParser(
        description="MEGA BACKTESTER: Run Core Bot Engine simulations using Cartridge configurations.",
        epilog=f"Available Cartridges: [{cartridge_list}]"
    )
    parser.add_argument(
        "cartridge",
        help=f"Name of the cartridge module in tools/cartridges/ (Available: {cartridge_list})"
    )
    parser.add_argument(
        "--strategy", "-s",
        help="Override the strategy variant defined in the cartridge (e.g. 'rubberband_reaper')",
        default=None
    )
    parser.add_argument(
        "--symbol", "-a", "--asset",
        help="Override the asset(s) to trade (comma-separated, e.g. 'BTC/USD,ETH/USD')",
        default=None
    )
    
    args = parser.parse_args()
    
    # Simple check if user just wanted to see list (covered by help, but nice to be explicit if arg matches)
    if args.cartridge == "list":
        print("Available Cartridges:")
        for c in available_cartridges:
            print(f" - {c}")
        sys.exit(0)
        
    run_simulation(args.cartridge, args.strategy, args.symbol)
