
import ccxt
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# Mapping of Local Symbol -> (Exchange, Remote Symbol)
# We can expand this logic or make it dynamic
FOREX_MAP = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "NZDUSD": "NZD/USD",
}

def get_exchange_for_symbol(symbol):
    """Heuristic to pick exchange."""
    # Normalize
    clean_sym = symbol.replace("/", "")
    
    if clean_sym in FOREX_MAP:
        return "kraken", FOREX_MAP[clean_sym]
    else:
        # Default to Coinbase for crypto
        # Ensure it has slash
        if "/" not in symbol:
             # Try to guess, e.g. BTCUSD -> BTC/USD
             if symbol.endswith("USD"):
                 remote = f"{symbol[:-3]}/USD"
             else:
                 remote = symbol
        else:
             remote = symbol
        return "coinbase", remote

def download_ohlcv(exchange, symbol, timeframe, start_date, end_date):
    """Download OHLCV data from exchange."""
    all_candles = []
    since = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)

    print(f"[DOWNLOADER] Fetching {symbol} {timeframe} from {exchange.id} ({start_date} -> {end_date})...")

    while since < end_ms:
        try:
            time.sleep(1.2) # Rate limit protection
            
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=720)
            if not candles:
                print("  No more candles returned.")
                break
            
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            print(f"  Fetched {len(all_candles)} candles so far... (Last: {datetime.fromtimestamp(candles[-1][0]/1000, tz=timezone.utc)})")
            
            if since >= end_ms:
                break
                
        except Exception as e:
            print(f"  [ERROR] Download failure: {e}")
            time.sleep(5)
            # Check for bad symbol error to abort early
            if "BadSymbol" in str(e) or "does not have market symbol" in str(e):
                return []
            continue

    return all_candles

def save_candles(candles, filepath):
    """Save candles to JSON file."""
    data = []
    for c in candles:
        ts = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc)
        data.append({
            "timestamp": ts.isoformat(),
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5] or 0,
        })

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"[DOWNLOADER] Saved {len(data)} candles to {filepath}")

def ensure_data_exists(symbol, timeframe, start_date, end_date, data_dir):
    """Check if file exists, if not, download it."""
    # Normalize filename
    file_symbol = symbol.replace("/", "")
    file_name = f"{file_symbol}_{timeframe}.json"
    path = os.path.join(data_dir, file_name)
    
    if os.path.exists(path):
        return True # Exists (we assume coverage is ok for simplicity)

    print(f"[AUTO-DATA] Missing {path}. Triggering download...")
    
    # Init Exchange
    ex_name, remote_symbol = get_exchange_for_symbol(symbol)
    
    if ex_name == "kraken":
        exchange = ccxt.kraken({'enableRateLimit': True})
    else:
        exchange = ccxt.coinbase({'enableRateLimit': True})
        
    try:
        candles = download_ohlcv(exchange, remote_symbol, timeframe, start_date, end_date)
        if candles:
            save_candles(candles, path)
            return True
        else:
            print(f"[AUTO-DATA] Failed to download {symbol}.")
            return False
    except Exception as e:
         print(f"[AUTO-DATA] Exception during download: {e}")
         return False
