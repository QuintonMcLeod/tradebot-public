#!/usr/bin/env python3
"""Download Forex historical data from IBKR for backtesting.

Connects to TWS/Gateway and downloads 15m candles for all forex symbols.
"""

import sys
import json
import os
import socket
import re
from datetime import datetime, timedelta
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ib_insync import IB, Contract, util

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"

# Forex symbols from the forex_intraday profile
FOREX_SYMBOLS = [
    # Forex pairs
    ("EURUSD", "EUR", "CASH", "IDEALPRO"),
    ("GBPUSD", "GBP", "CASH", "IDEALPRO"),
    ("USDJPY", "USD", "CASH", "IDEALPRO"),  # Note: USD is base for JPY
    ("AUDUSD", "AUD", "CASH", "IDEALPRO"),
    ("USDCAD", "USD", "CASH", "IDEALPRO"),
    ("USDCHF", "USD", "CASH", "IDEALPRO"),
    ("NZDUSD", "NZD", "CASH", "IDEALPRO"),
    # Commodities (CFDs)
    ("XAUUSD", "XAUUSD", "CFD", "SMART"),
    ("XAGUSD", "XAGUSD", "CFD", "SMART"),
    # Crypto
    ("BTCUSD", "BTC", "CRYPTO", "PAXOS"),
    ("ETHUSD", "ETH", "CRYPTO", "PAXOS"),
    ("SOLUSD", "SOL", "CRYPTO", "PAXOS"),
]


def create_forex_contract(symbol, base_currency, sec_type, exchange):
    """Create IBKR contract for forex pair."""
    contract = Contract()

    if sec_type == "CASH":
        # Forex pair: symbol is base currency, currency is quote (USD)
        contract.symbol = base_currency
        contract.secType = "CASH"
        contract.currency = "USD" if not symbol.startswith("USD") else symbol[3:]
        contract.exchange = exchange
    elif sec_type == "CFD":
        contract.symbol = symbol
        contract.secType = "CFD"
        contract.currency = "USD"
        contract.exchange = exchange
    elif sec_type == "CRYPTO":
        contract.symbol = base_currency
        contract.secType = "CRYPTO"
        contract.currency = "USD"
        contract.exchange = exchange

    return contract


def download_historical(ib, contract, symbol_name, duration="18 D", bar_size="15 mins"):
    """Download historical bars from IBKR."""
    print(f"Downloading {symbol_name} {bar_size}...")

    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',  # Now
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow='MIDPOINT' if contract.secType == "CASH" else 'TRADES',
            useRTH=False,  # Include extended hours
            formatDate=1,
        )

        if not bars:
            print(f"  No data returned for {symbol_name}")
            return None

        print(f"  Got {len(bars)} bars")
        return bars

    except Exception as e:
        print(f"  Error downloading {symbol_name}: {e}")
        return None


def save_bars(bars, filename):
    """Save bars to JSON file."""
    data = []
    for bar in bars:
        data.append({
            "timestamp": bar.date.isoformat() if hasattr(bar.date, 'isoformat') else str(bar.date),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume if bar.volume else 0,
        })

    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Saved to {filepath}")


def main():
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DOWNLOADING FOREX DATA FROM IBKR")
    print("=" * 60)
    print(f"Symbols: {[s[0] for s in FOREX_SYMBOLS]}")
    print()
    duration = os.getenv("IBKR_DURATION", "1 D")

    # Connect to IBKR
    host = "127.0.0.1"
    port = 7497
    client_id = 99
    config_path = Path(__file__).resolve().parents[1] / "config" / "broker_ibkr.yaml"
    if config_path.exists():
        with open(config_path, "r") as f:
            for line in f:
                match = re.match(r"\\s*client_id\\s*:\\s*(\\d+)\\s*$", line)
                if match:
                    client_id = int(match.group(1))
                    break
    env_client_id = os.getenv("IBKR_CLIENT_ID")
    if env_client_id and env_client_id.isdigit():
        client_id = int(env_client_id)
    ib = IB()

    print(f"Connecting to IBKR at {host}:{port} (clientId={client_id})")

    # Preflight TCP check to avoid silent hangs.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((host, port))
        print("TCP check ok: port is open.")
    except Exception as e:
        print(f"TCP check failed: {e}")
        print("Is TWS/Gateway running and API enabled on this port?")
        return 1
    finally:
        sock.close()

    max_tries = 5
    for attempt in range(max_tries):
        active_id = client_id + attempt
        try:
            ib.connect(host, port, clientId=active_id, timeout=10)
            print(f"Connected to IBKR (clientId={active_id})")
            break
        except Exception as e:
            msg = str(e).lower()
            if "client id" in msg and "already" in msg:
                print(f"ClientId {active_id} in use, trying next...")
                continue
            print(f"Failed to connect to IBKR: {e}")
            print("Make sure TWS/Gateway is running and API is enabled")
            return 1
    else:
        print("Failed to connect: all tested clientIds are in use.")
        return 1

    try:
        for symbol_name, base_currency, sec_type, exchange in FOREX_SYMBOLS:
            contract = create_forex_contract(symbol_name, base_currency, sec_type, exchange)

            # Qualify the contract
            try:
                ib.qualifyContracts(contract)
            except Exception as e:
                print(f"Could not qualify {symbol_name}: {e}")
                continue

            # Download 15m bars
            bars = download_historical(ib, contract, symbol_name, duration, "15 mins")
            if bars:
                save_bars(bars, f"{symbol_name}_15m.json")

            # Rate limit
            time.sleep(1)

            # Download 5m bars
            bars = download_historical(ib, contract, symbol_name, duration, "5 mins")
            if bars:
                save_bars(bars, f"{symbol_name}_5m.json")

            # Rate limit between symbols
            time.sleep(2)

    finally:
        ib.disconnect()
        print("\nDisconnected from IBKR")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
