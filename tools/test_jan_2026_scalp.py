import os
import sys
from datetime import datetime, timezone
import logging

# Add src to path
sys.path.append(os.path.abspath("src"))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import load_settings

def run_jan_2026_scalp():
    logging.basicConfig(level=logging.INFO)
    
    # Load settings with scalp_aggressive profile
    settings = load_settings()
    settings.app.profile_name = "scalp_aggressive"
    
    # Ensure no caps block trades
    if settings.broker:
        settings.broker.max_dollar_risk_per_symbol = 1000000.0
        settings.broker.max_shares_per_symbol = 1000000
    
    backtester = Backtester(None, settings, None)
    
    symbols = ["SOL/USD", "BTC/USD", "ETH/USD"]  # Multi-symbol for better coverage
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 14, tzinfo=timezone.utc)  # First 2 weeks
    
    print("="*60)
    print("JANUARY 2026 BASELINE BACKTEST")
    print("Profile: scalp_aggressive (ORIGINAL SETTINGS)")
    print("="*60)
    
    result = backtester.run_backtest(1000.0, start_date, end_date, symbols=symbols)
    
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    print(f"Final Capital: ${result.final_capital:,.2f}")
    print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Win Rate: {result.win_rate:.1%}")
    print(f"Total Trades: {len(result.trades)}")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    
    # Calculate average win/loss
    wins = [t.pnl for t in result.trades if t.pnl > 0]
    losses = [t.pnl for t in result.trades if t.pnl < 0]
    if wins:
        print(f"Average Win: ${sum(wins)/len(wins):,.2f}")
    if losses:
        print(f"Average Loss: ${sum(losses)/len(losses):,.2f}")
    
    # Show trade details
    print("\n" + "="*60)
    print("TRADE DETAILS")
    print("="*60)
    for i, t in enumerate(result.trades, 1):
        print(f"{i}. {t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.symbol} {t.direction} | P&L: {'+' if t.pnl >= 0 else ''}${t.pnl:,.2f} | Reason: {t.exit_reason}")

if __name__ == "__main__":
    run_jan_2026_scalp()
