#!/usr/bin/env python3
"""
Test position snapshot logic directly.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

# Mock profile
class MockProfile:
    def __init__(self):
        self.crypto_qty_steps = {}

# Simulate the buggy code
def test_snapshot_logic():
    print("=== Testing Position Snapshot Logic ===\n")

    # Simulate balance data
    total = {
        "XRP": 4.524525,
        "DOGE": 0.02220808,
        "ADA": 39.37,  # From the order
        "USD": 19.62,
        "USDT": 39.47,
    }

    symbol = "XRPUSDT"
    sym = "XRP/USDT"
    base = "XRP"
    size = float(total.get(base, 0.0))

    print(f"Symbol: {symbol}")
    print(f"CCXT Symbol: {sym}")
    print(f"Base currency: {base}")
    print(f"Size from balance: {size}\n")

    # THE BUG: min_amount is used before being defined!
    try:
        print("Attempting to check min_amount...")
        # This line (230) will fail because min_amount doesn't exist yet
        if min_amount is None:  # ← NameError: name 'min_amount' is not defined
            print("min_amount is None")
    except NameError as e:
        print(f"❌ ERROR: {e}")
        print("This is why positions aren't being tracked!\n")
        return None

    print("✅ If we got here, min_amount was defined")
    return {"symbol": symbol, "size": size}

# Run test
result = test_snapshot_logic()
if result:
    print(f"\n✅ Position tracked: {result}")
else:
    print("\n❌ Position NOT tracked (function returned None)")
