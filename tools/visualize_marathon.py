#!/usr/bin/env python3
import sys
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone, timedelta
import unittest.mock

# Add project roots
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
sys.path.insert(0, os.getcwd())

# Mock ib_insync
sys.modules["ib_insync"] = unittest.mock.MagicMock()

from tools.mega_backtester import load_cartridge
from tradebot_sci.config.models import Settings, AppSettings, LoggingSettings, AISettings, MarketSettings
from tradebot_sci.simulation.backtester import Backtester
from tools.utils.local_provider import LocalJSONProvider

def run_and_get_trades(cartridge_name):
    print(f"Running {cartridge_name} for visualization...")
    cartridge = load_cartridge(cartridge_name)
    config = cartridge.get_config()
    
    profile_settings = config["profile_settings"]
    symbols = config["symbols"]
    start_date = config["start_date"]
    end_date = config["end_date"]
    initial_capital = config.get("initial_capital", 100.0)
    data_dir_name = config.get("data_dir_name", "marathon")

    profile_name = "VizTest"
    settings = Settings(
        app=AppSettings(profile_name=profile_name),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=symbols),
        profiles={profile_name: profile_settings},
    )
    
    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    data_dir = os.path.join(os.getcwd(), "data", data_dir_name)
    backtester.market_provider = LocalJSONProvider(data_dir)
    
    if config.get("force_market_open", False):
        backtester._is_market_hours_utc = lambda ts: True

    results = backtester.run_backtest(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        symbols=symbols
    )
    return results, initial_capital

def plot_marathon():
    # 1. Run Forex
    forex_results, forex_init = run_and_get_trades("marathon_forex")
    # 2. Run Crypto
    crypto_results, crypto_init = run_and_get_trades("marathon_crypto")
    
    # Process Trades for Plotting
    def get_equity_curve(results, initial_cap):
        trades = sorted(results.trades, key=lambda t: t.exit_time)
        times = [results.start_date]
        equity = [initial_cap]
        current_equity = initial_cap
        for t in trades:
            current_equity += t.pnl
            times.append(t.exit_time)
            equity.append(current_equity)
        # Add final point
        times.append(results.end_date)
        equity.append(current_equity)
        return times, equity

    f_times, f_equity = get_equity_curve(forex_results, forex_init)
    c_times, c_equity = get_equity_curve(crypto_results, crypto_init)
    
    # Plotting
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    ax1.set_facecolor('#1e1e1e')
    ax2.set_facecolor('#1e1e1e')
    fig.patch.set_facecolor('#1e1e1e')
    
    # Forex Plot
    ax1.step(f_times, f_equity, where='post', color='#00d4ff', linewidth=2, label='Forex Equity ($2000 Base)')
    ax1.fill_between(f_times, f_equity, forex_init, step='post', alpha=0.2, color='#00d4ff')
    ax1.axhline(y=forex_init, color='white', linestyle='--', alpha=0.5)
    ax1.set_title("14-Day Forex Marathon Equity Curve", color='white', size=14)
    ax1.set_ylabel("Capital (USD)", color='white')
    ax1.legend(loc='upper right')
    ax1.grid(True, color='#333333', alpha=0.5)
    
    # Crypto Plot
    ax2.step(c_times, c_equity, where='post', color='#ffae00', linewidth=2, label='Crypto Equity ($500 Base)')
    ax2.fill_between(c_times, c_equity, crypto_init, step='post', alpha=0.2, color='#ffae00')
    ax2.axhline(y=crypto_init, color='white', linestyle='--', alpha=0.5)
    ax2.set_title("14-Day Crypto Marathon Equity Curve", color='white', size=14)
    ax2.set_ylabel("Capital (USD)", color='white')
    ax2.legend(loc='upper right')
    ax2.grid(True, color='#333333', alpha=0.5)
    
    # Formatting
    plt.xticks(rotation=45, color='white')
    plt.yticks(color='white')
    ax1.tick_params(colors='white')
    ax2.tick_params(colors='white')
    
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    plt.tight_layout()
    output_path = os.path.join(os.getcwd(), 'marathon_performance_chart.png')
    plt.savefig(output_path, dpi=120, facecolor=fig.get_facecolor())
    print(f"Chart saved to {output_path}")

if __name__ == "__main__":
    plot_marathon()
