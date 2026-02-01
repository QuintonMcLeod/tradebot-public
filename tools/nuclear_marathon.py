#!/usr/bin/env python3
"""Run a Nuclear Backtest: SND + Gamma Squeeze with Extreme Risk."""

import sys
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.backtester import Backtester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    print("=" * 60)
    print("☢️ NUCLEAR MARATHON: SND + GAMMA SQUEEZE ☢️")
    print("=" * 60)

    # Load settings (respecting .env overrides)
    settings = load_settings()
    
    # 1. Force the active profile to one that supports SND
    # The user has APP_PROFILE=forex_crypto_hybrid in .env
    profile_name = settings.app.profile_name
    profile = settings.profiles.get(profile_name)
    if not profile:
        print(f"Error: Profile {profile_name} not found.")
        return 1

    profile.nuclear_overrides_enabled = os.getenv("NUCLEAR_OVERRIDES_ENABLED", "false").lower() == "true"
    profile.max_risk_cap_override = float(os.getenv("MAX_RISK_CAP_OVERRIDE", "0.05"))
    profile.compounding_cap_override = float(os.getenv("COMPOUNDING_CAP_OVERRIDE", "10000.0"))
    profile.pyramid_cap_override = float(os.getenv("PYRAMID_CAP_OVERRIDE", "750.0"))
    
    # 2. Force Strategy and Wealth Mode
    profile.strategy_variant = "supply_demand"
    os.environ["PERFORMANCE_MODE"] = "gamma"
    
    # 3. Verify Nuclear Overrides are active
    print(f"Nuclear Mode: {'ENABLED' if profile.nuclear_overrides_enabled else 'DISABLED'}")
    print(f"Risk Cap Override: {profile.max_risk_cap_override * 100:.1f}%")
    print(f"Compounding Cap: ${profile.compounding_cap_override:,.2f}")
    print(f"Pyramid Cap: ${profile.pyramid_cap_override:,.2f}")
    
    # "Famous January Week"
    start_date = datetime(2026, 1, 24, tzinfo=ZoneInfo("UTC"))
    end_date = datetime(2026, 1, 31, tzinfo=ZoneInfo("UTC"))
    initial_capital = float(os.getenv("INITIAL_CAPITAL", "10000.0"))
    
    # Focus symbols from Jan week
    symbols = ["BTC/USD", "ETH/USD", "EURUSD", "GBPUSD", "SOL/USD"]

    # Mapping to local JSON data from previous marathons
    data_dir = Path(__file__).parent.parent / "data" / "marathon"
    data_paths = {
        "BTC/USD": str(data_dir / "BTCUSD_5m.json"),
        "ETH/USD": str(data_dir / "ETHUSD_5m.json"),
        "SOL/USD": str(data_dir / "SOLUSD_5m.json"),
        "EURUSD": str(data_dir / "EURUSD_5m.json"),
        "GBPUSD": str(data_dir / "GBPUSD_5m.json"),
    }

    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print("-" * 60)

    # Initialize components
    ai_client = TradeSciAIClient(settings.ai)
    backtester = Backtester(None, settings, ai_client) 

    # Run
    try:
        result = backtester.run_backtest(
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            data_paths=data_paths
        )
    except Exception as e:
        logging.exception("Nuclear Marathon failed")
        return 1

    # Generate Report
    print("\n" + "=" * 60)
    print("☢️ NUCLEAR RESULTS ☢️")
    print("=" * 60)
    
    print(f"\nFinal Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:+.2f}%)")
    print(f"Total Trades: {len(result.trades)}")
    print(f"Win Rate: {result.win_rate:.1f}%")
    
    if result.trades:
        print("\nTop Win:")
        max_trade = max(result.trades, key=lambda t: t.pnl)
        print(f"  {max_trade.symbol} {max_trade.direction.upper()}: ${max_trade.pnl:,.2f} ({max_trade.exit_reason})")
        
        print("\nMax Drawdown (Trade):")
        min_trade = min(result.trades, key=lambda t: t.pnl)
        print(f"  {min_trade.symbol} {min_trade.direction.upper()}: ${min_trade.pnl:,.2f} ({min_trade.exit_reason})")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
