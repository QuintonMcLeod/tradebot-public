import os
import sys
from datetime import datetime, timedelta, timezone
import logging

# Add src to path
sys.path.append(os.path.abspath("src"))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import load_settings
from tradebot_sci.market.symbols import AssetClass

def run_aggro_backtest():
    import tradebot_sci
    print(f"LOADING TRADEBOT FROM: {tradebot_sci.__file__}")
    logging.basicConfig(level=logging.DEBUG) # [ANTIGRAVITY DEBUG] Enable verbose logs
    
    # Load settings and force the aggro profile
    settings = load_settings()
    profile_name = "scalp_aggressive" # [ANTIGRAVITY] New profile
    settings.app.profile_name = "scalp_aggressive"
    
    # ENSURE NO CAPS BLOCK OUR YOLO
    if settings.broker:
        settings.broker.max_dollar_risk_per_symbol = 1000000.0 # Uncapped for test (YOLO)
        settings.broker.max_shares_per_symbol = 1000000
    
    # [ANTIGRAVITY] Force entry (was 70) to test Exit by mutating loaded profile
    if "scalp_aggressive" in settings.profiles:
        settings.profiles["scalp_aggressive"].icc_entry_score_threshold = 0.0
        
    backtester = Backtester(None, settings, None)
    
    symbols = ["SOL/USD"] # Focus on SOL only
    start_date = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 11, 5, tzinfo=timezone.utc) # Extend to catch the exit
    
    print("="*60)
    print("NOVEMBER 2024 YOLO AGGRESSIVE (30/50/80) BACKTEST")
    print("="*60)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Initial capital: $1,000.00")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print("\nRunning backtest...")
    
    result = backtester.run_backtest(1000.0, start_date, end_date, symbols=symbols)
    
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"Final Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Win Rate: {result.win_rate:.1%}")
    print(f"Total Trades: {len(result.trades)}")
    
    print("\n" + "="*60)
    print("TRADE DETAILS")
    print("="*60)
    for i, t in enumerate(result.trades, 1):
        print(f"{i}. {t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.symbol} {t.direction} | P&L: {'+' if t.pnl >= 0 else ''}${t.pnl:,.2f} | Reason: {t.exit_reason}")

if __name__ == "__main__":
    run_aggro_backtest()
