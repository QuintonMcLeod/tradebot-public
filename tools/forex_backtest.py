#!/usr/bin/env python3
"""Fetch Forex historical data from IBKR and run ICC backtest.

This script:
1. Connects to IBKR TWS/Gateway
2. Fetches historical 5m candles for major Forex pairs
3. Saves to data/ directory for backtesting
4. Runs ICC strategy backtest with proper micro-lot sizing
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta
import json

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("forex_backtest")

# Forex pairs to test
FOREX_PAIRS = [
    "EURUSD",  # Euro / US Dollar
    "GBPUSD",  # British Pound / US Dollar
    "USDJPY",  # US Dollar / Japanese Yen
    "AUDUSD",  # Australian Dollar / US Dollar
]

def fetch_forex_data(ib, symbol: str, days: int = 5) -> list:
    """Fetch historical 5m candles for a Forex pair."""
    from ib_insync import Forex
    
    contract = Forex(symbol)
    contract = ib.qualifyContracts(contract)[0]
    logger.info(f"Fetching {days} days of {symbol} data...")
    
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=f'{days} D',
        barSizeSetting='5 mins',
        whatToShow='MIDPOINT',  # Forex uses MIDPOINT
        useRTH=False,  # 24h Forex market
        formatDate=1,
        keepUpToDate=False,
    )
    
    logger.info(f"  Got {len(bars)} bars for {symbol}")
    return bars

def bars_to_candles(symbol: str, bars: list) -> list:
    """Convert ib_insync BarData to candle dicts."""
    candles = []
    for bar in bars:
        candles.append({
            "symbol": symbol,
            "timestamp": bar.date.isoformat() if hasattr(bar.date, 'isoformat') else str(bar.date),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": 0,  # Forex doesn't have meaningful volume
        })
    return candles

def main():
    import time
    from ib_insync import IB
    
    print("=" * 80)
    print("FOREX BACKTEST - IBKR DATA FETCH")
    print("=" * 80)
    
    # Connect to IBKR
    ib = IB()
    client_id = int(time.time()) % 10000 + 300
    
    try:
        ib.connect('127.0.0.1', 7497, clientId=client_id, timeout=5)
        logger.info(f"Connected to IBKR (clientId={client_id})")
    except Exception as e:
        logger.error(f"Failed to connect to IBKR: {e}")
        return 1
    
    # Fetch data for all pairs
    all_candles = {}
    for symbol in FOREX_PAIRS:
        try:
            bars = fetch_forex_data(ib, symbol, days=5)
            if bars:
                all_candles[symbol] = bars_to_candles(symbol, bars)
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
    
    ib.disconnect()
    
    # Save data
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'forex_backtest')
    os.makedirs(data_dir, exist_ok=True)
    
    for symbol, candles in all_candles.items():
        filepath = os.path.join(data_dir, f'{symbol}_5m.json')
        with open(filepath, 'w') as f:
            json.dump(candles, f, indent=2)
        logger.info(f"Saved {len(candles)} candles to {filepath}")
    
    # Summary
    print("\n" + "=" * 80)
    print("DATA FETCH COMPLETE")
    print("=" * 80)
    for symbol, candles in all_candles.items():
        if candles:
            print(f"  {symbol}: {len(candles)} bars, {candles[0]['timestamp'][:10]} to {candles[-1]['timestamp'][:10]}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
