
import logging
import sys
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone, timedelta

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.simulation.providers.ccxt_provider import CCXTHistoricalDataProvider
from tradebot_sci.market.models import Candle
from tradebot_sci.strategy.icc_signals import (
    detect_liquidity_sweep, 
    detect_indication, 
    detect_correction, 
    detect_continuation
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("viz_sol")

def plot_candles(candles, ax, width=0.0005):
    """
    Draw candlestick patterns on the given axes from a list of Candle objects.
    """
    up_color = '#26a69a'  # Teal
    down_color = '#ef5350' # Red
    
    width2 = width / 2.0
    
    for c in candles:
        t = mdates.date2num(c.timestamp)
        open_p = c.open
        close_p = c.close
        high_p = c.high
        low_p = c.low
        
        if close_p >= open_p:
            color = up_color
            lower = open_p
            height = close_p - open_p
        else:
            color = down_color
            lower = close_p
            height = open_p - close_p
            
        ax.vlines(t, low_p, high_p, color=color, linewidth=1)
        if height == 0: height = 0.00001
        rect = plt.Rectangle((t - width2, lower), width, height, color=color)
        ax.add_patch(rect)

def run_simulation_for_signals(candles):
    """
    Replay history to find the signals leading to the entry at 17:50.
    """
    signals = {
        'sweeps': [],
        'indications': [],
        'corrections': [],
        'continuations': []
    }
    
    latest_sweep = None
    latest_indication = None
    latest_correction = None
    
    # We only care about signals leading up to our known entry at 17:50
    # Entry time: Nov 1 17:50 UTC
    target_entry_time = datetime(2024, 11, 1, 17, 50, tzinfo=timezone.utc)
    
    print("Simulating signals...")
    
    # Optimization: Only run detection on the window relevant to the setup
    # Setup usually takes 1-4 hours. Let's scan from 12:00 to 18:00
    scan_start = datetime(2024, 11, 1, 12, 0, tzinfo=timezone.utc)
    
    for i in range(50, len(candles)):
        current_candle = candles[i]
        if current_candle.timestamp < scan_start:
            continue
        if current_candle.timestamp > target_entry_time:
            break
            
        current_slice = candles[:i+1]
        
        # 1. Detect Sweep
        sw = detect_liquidity_sweep(current_slice, "long", window=60)
        if sw: 
            latest_sweep = sw
            # Only store if new
            if not signals['sweeps'] or signals['sweeps'][-1].index != sw.index:
                signals['sweeps'].append(sw)

        # 2. Detect Indication
        ind = detect_indication(current_slice, window=80)
        if ind and ind.direction == "long":
            latest_indication = ind
            if not signals['indications'] or signals['indications'][-1].index != ind.index:
                signals['indications'].append(ind)
                
        # 3. Detect Correction
        if latest_indication:
            cor = detect_correction(current_slice, latest_indication, window=80)
            if cor and cor.direction == "long":
                latest_correction = cor
                if not signals['corrections'] or signals['corrections'][-1].index != cor.index:
                    signals['corrections'].append(cor)

        # 4. Detect Continuation (Entry)
        cont = detect_continuation(
            current_slice, "long", 
            latest_sweep, latest_indication, latest_correction,
            require_sweep=True, require_indication=True
        )
        if cont:
             if not signals['continuations'] or signals['continuations'][-1].index != cont.index:
                signals['continuations'].append(cont)
                
    return signals

def main():
    settings = load_settings()
    settings.app.profile_name = "coinbase_futures" 
    
    # Initialize Provider
    provider = CCXTHistoricalDataProvider(settings)
    
    symbol = "SOL/USD"
    timeframe = "1m"
    
    # Fetch Data
    start_date = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 11, 14, tzinfo=timezone.utc)
    
    print(f"Fetching data...")
    all_candles = provider.fetch_historical_candles(symbol, timeframe, start_date, end_date)
    
    if not all_candles:
        print("No candles found.")
        return

    # Filter for Plotting Window (Expanded to show setup)
    # Start at 12:00 to show the whole afternoon setup
    plot_start = datetime(2024, 11, 1, 12, 0, tzinfo=timezone.utc) 
    # End shortly after stop out to show the "Held for days" scale
    # Stop out was Nov 4 14:32. Let's show until Nov 4 18:00
    plot_end = datetime(2024, 11, 4, 18, 0, tzinfo=timezone.utc)
    
    candles_plot = [c for c in all_candles if plot_start <= c.timestamp <= plot_end]
    
    # Run Signal Simulation on the data up to entry
    signals = run_simulation_for_signals([c for c in all_candles if c.timestamp <= plot_end])
    
    # Prepare Plot
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.set_facecolor('#1e1e1e')
    fig.patch.set_facecolor('#1e1e1e')
    ax.grid(True, color='#333333', linestyle='--', linewidth=0.5)
    
    # Plot Candles
    candle_width = 0.6 * (1.0 / (24.0 * 60.0))
    plot_candles(candles_plot, ax, width=candle_width)
    
    # --- ANNOTATIONS ---
    
    # 1. Entry
    entry_time = datetime(2024, 11, 1, 17, 50, tzinfo=timezone.utc)
    entry_price = next((c.close for c in candles_plot if c.timestamp >= entry_time), 0)
    
    ax.annotate(f'ENTRY LONG\nNov 1 17:50\n${entry_price:.2f}', 
                xy=(mdates.date2num(entry_time), entry_price), 
                xytext=(mdates.date2num(entry_time), entry_price * 0.92),
                arrowprops=dict(facecolor='yellow', shrink=0.05, width=1, headwidth=5),
                color='yellow', fontsize=10, ha='center', weight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="#333300", ec="yellow", alpha=0.9))

    # 2. Exit
    exit_time = datetime(2024, 11, 4, 14, 32, tzinfo=timezone.utc)
    exit_price = next((c.close for c in candles_plot if c.timestamp >= exit_time), 0)
    
    ax.annotate(f'STOP HIT\nNov 4 14:32\n${exit_price:.2f}', 
                xy=(mdates.date2num(exit_time), exit_price), 
                xytext=(mdates.date2num(exit_time), exit_price * 1.08),
                arrowprops=dict(facecolor='red', shrink=0.05, width=1, headwidth=5),
                color='red', fontsize=10, ha='center', weight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="#330000", ec="red", alpha=0.9))

    # 3. Indication and Correction (from Simulation)
    # Get the last indication/correction before entry
    valid_ind = [s for s in signals['indications'] if all_candles[s.index].timestamp < entry_time]
    valid_cor = [s for s in signals['corrections'] if all_candles[s.index].timestamp < entry_time]
    
    if valid_ind:
        last_ind = valid_ind[-1]
        ind_candle = all_candles[last_ind.index]
        ax.annotate('Indication (Break)', 
                    xy=(mdates.date2num(ind_candle.timestamp), last_ind.level),
                    xytext=(mdates.date2num(ind_candle.timestamp), last_ind.level * 1.01),
                    arrowprops=dict(facecolor='cyan', arrowstyle='->'),
                    color='cyan', fontsize=8, ha='center')
                    
    if valid_cor:
        last_cor = valid_cor[-1]
        cor_candle = all_candles[last_cor.index]
        ax.annotate(f'Correction ({last_cor.retracement_pct:.1%})', 
                    xy=(mdates.date2num(cor_candle.timestamp), last_cor.retracement_level),
                    xytext=(mdates.date2num(cor_candle.timestamp), last_cor.retracement_level * 0.99),
                    arrowprops=dict(facecolor='magenta', arrowstyle='->'),
                    color='magenta', fontsize=8, ha='center')

    # Formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.xticks(rotation=45, color='white')
    plt.yticks(color='white')
    plt.ylabel("Price (USD)", color='white')
    plt.title(f"Trade Analysis: SOL/USD Full ICC Sequence (Nov 2024)", color='white', size=14, pad=20)
    
    plt.tight_layout()
    output_path = os.path.join(os.getcwd(), 'sol_loss_chart_annotated.png')
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    print(f"Chart saved to {output_path}")

if __name__ == "__main__":
    main()
