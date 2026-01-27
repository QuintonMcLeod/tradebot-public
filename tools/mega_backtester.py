#!/usr/bin/env python3
"""
MEGA BACKTESTER
Consolidated backtesting runner that uses the Core Bot Engine (Backtester).
Loads configuration from "Cartridges" (custom modules) to define simulation parameters.

Usage:
    python3 tools/mega_backtester.py <cartridge_name> [--strategy <strategy_name>]

Example:
    python3 tools/mega_backtester.py friday_fade --strategy rubberband_reaper
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
    settings = Settings(
        app=AppSettings(profile_name=profile_name),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"), # Dummy
        market=MarketSettings(symbols=symbols),
        profiles={profile_name: profile_settings},
    )
    
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
        # Pydantic Settings object uses 'profiles' and 'app.profile_name'
        profile_key = "marathon_profile"
        settings.profiles[profile_key] = cart_profile
        settings.app.profile_name = profile_key
        print(f"[Cartridge] Injected Profile: {profile_key} (Variant: {cart_profile.strategy_variant})")

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
        
        if results.trades:
            print("\nTrade History:")
            for t in results.trades:
                print(f"[{t.exit_time.strftime('%Y-%m-%d %H:%M')}] {t.symbol} {t.direction} {t.exit_reason}")
                print(f"  PnL: ${t.pnl:.4f} | Size: {t.size:.4f}")

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
