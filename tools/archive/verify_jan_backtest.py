#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

# Fix logging to be less noisy
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backtest_verify")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import get_settings

def run_verification_backtest():
    settings = get_settings()
    
    # Configure for January 23 - 31, 2026 (The Success Window)
    start_date = datetime(2026, 1, 23, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 31, tzinfo=timezone.utc)
    
    # Map symbols to their local data files
    data_paths = {
        "EURUSD": "data/forex_backtest/EURUSD_5m.json",
        "BTCUSD": "data/crypto_marathon/BTCUSD_5m.json",
        "GBPUSD": "data/forex_backtest/GBPUSD_5m.json"
    }
    
    # Initialize Backtester with None for IB (local file mode enabled by recent fix)
    tester = Backtester(ib=None, settings=settings, ai_client=None)
    
    print(f"=== VERIFICATION BACKTEST: JAN 23-31, 2026 ===")
    
    # 1. Forex Test (EURUSD)
    print("\n--- Testing Forex (EURUSD) with 'forex_intraday' profile ---")
    settings.app.profile_name = "forex_intraday"
    results_forex = None
    try:
        results_forex = tester.run_backtest(
            initial_capital=100.0,
            start_date=start_date,
            end_date=end_date,
            symbols=["EURUSD"],
            data_paths=data_paths
        )
        if results_forex:
            print(f"Forex Trades: {len(results_forex.trades)}")
            print(f"Forex Final Capital: ${results_forex.final_capital:.2f}")
            for t in results_forex.trades:
                print(f"  [{t.exit_time}] {t.direction} {t.symbol} exit: {t.exit_reason} PnL: ${t.pnl:.2f}")
    except Exception as e:
        print(f"Forex Test Failed: {e}")

    # 2. Crypto Test (BTCUSD)
    print("\n--- Testing Crypto (BTCUSD) with 'crypto_247' profile ---")
    settings.app.profile_name = "crypto_247"
    results_crypto = None
    try:
        results_crypto = tester.run_backtest(
            initial_capital=100.0,
            start_date=start_date,
            end_date=end_date,
            symbols=["BTCUSD"],
            data_paths=data_paths
        )
        if results_crypto:
            print(f"Crypto Trades: {len(results_crypto.trades)}")
            print(f"Crypto Final Capital: ${results_crypto.final_capital:.2f}")
            for t in results_crypto.trades:
                print(f"  [{t.exit_time}] {t.direction} {t.symbol} exit: {t.exit_reason} PnL: ${t.pnl:.2f}")
    except Exception as e:
        print(f"Crypto Test Failed: {e}")

    # Final Summary
    print("\n=== VERIFICATION COMPLETE ===")
    has_trades = (results_forex and len(results_forex.trades) > 0) or (results_crypto and len(results_crypto.trades) > 0)
    if has_trades:
        print("SUCCESS: Bot is trading successfully in the Jan 23-31 window.")
    else:
        print("ALERT: No trades detected. Review thresholds or market volatility.")

if __name__ == "__main__":
    run_verification_backtest()
