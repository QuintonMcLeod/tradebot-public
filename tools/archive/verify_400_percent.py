from __future__ import annotations
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Setup pathing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.optimize_strategies import PortfolioBacktester
from tradebot_sci.strategy.variants.mean_reversion import MeanReversionStrategy
from tradebot_sci.config.models import UserConfig

def main():
    # PURE FOREX PORTFOLIO (As requested: No Gold/Metals)
    symbols = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'NZDUSD']
    print(f"Settings: P=15, SD=2.5, RSI=25, Risk=10%, Pyramiding=INFINITE")
    print(f"Leverage Caps: Initial 30x, Pyramid 100x")
    
    # Enable Infinite Mode in Config for the run
    UserConfig.INFINITE_PYRAMIDING = True
    UserConfig.MAX_PYRAMID_ENTRIES = 1000

    # 10% Risk is the sweet spot for Forex majors with Infinite Pyramiding
    tester = PortfolioBacktester(symbols, 0.10, compound=True)
    
    # MeanReversion now defaults to these optimized pure-Forex settings
    final_cap = tester.run(MeanReversionStrategy, {})
    
    print(f"\n--- FINAL RESULTS ---")
    print(f"Initial Capital: $100.00")
    print(f"Final Capital:   ${final_cap:.2f}")
    print(f"PnL %:           {(final_cap/100-1)*100:.2f}% (Over 18 Days)")
    print(f"Weekly Average:  ~{((final_cap/100)**(1/2.5)-1)*100:.1f}%")

if __name__ == '__main__':
    main()
