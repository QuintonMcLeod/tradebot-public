#!/usr/bin/env python3
"""
Check if bot can detect XRP position from Coinbase balance.
"""

import os
import sys
import ccxt
from pprint import pprint

# Load env variables
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("CCXT_API_KEY")
secret = os.getenv("CCXT_SECRET")
password = os.getenv("CCXT_PASSWORD")

if not api_key or not secret:
    print("ERROR: CCXT_API_KEY and CCXT_SECRET must be set in environment")
    sys.exit(1)

print("=" * 80)
print("XRP POSITION DETECTION TEST")
print("=" * 80)

# Initialize Coinbase exchange
exchange = ccxt.coinbase({
    "apiKey": api_key,
    "secret": secret,
    "password": password,
    "enableRateLimit": True,
})

print("\n1. Loading markets...")
exchange.load_markets()

print("\n2. Fetching balance...")
balance = exchange.fetch_balance()
total = balance.get("total", {})

print("\n3. DETECTING POSITIONS (Bot Logic):")
print("-" * 80)

ignored_currencies = {"USD", "USDT", "USDC", "DAI", "FDUSD"}
symbol_map = {
    "XRPUSDT": "XRP/USDT",
    "DOGEUSDT": "DOGE/USDT",
}

open_positions = set()

for currency, amount in total.items():
    amount_float = float(amount or 0)

    # Skip stablecoins/cash
    if currency in ignored_currencies:
        print(f"   SKIP {currency}: ${amount_float:.2f} (stablecoin/cash)")
        continue

    # Skip zero balances
    if amount_float <= 0:
        continue

    print(f"   FOUND {currency}: {amount_float} units")

    # Try to map to trading symbol
    for canonical_sym, ccxt_sym in symbol_map.items():
        if currency in ccxt_sym.split("/"):
            print(f"      → Mapped to {canonical_sym} ({ccxt_sym})")
            open_positions.add(canonical_sym)
            break

print("\n4. BOT RESULT:")
print("-" * 80)
if open_positions:
    print(f"   Open positions detected: {open_positions}")
else:
    print("   ❌ NO POSITIONS DETECTED")

print("\n5. EXPECTED RESULT:")
print("-" * 80)
xrp_balance = total.get("XRP", 0)
doge_balance = total.get("DOGE", 0)

print(f"   XRP balance: {xrp_balance} (should detect XRPUSDT position)")
print(f"   DOGE balance: {doge_balance}")

if xrp_balance > 0:
    print(f"\n✅ XRP position EXISTS ({xrp_balance} XRP)")
    if "XRPUSDT" in open_positions:
        print("✅ Bot CORRECTLY detected XRP position")
    else:
        print("❌ Bot FAILED to detect XRP position!")
        print("\nDEBUGGING:")
        print(f"   - XRP is in total balance: {xrp_balance}")
        print(f"   - Symbol map has XRPUSDT: {'XRPUSDT' in symbol_map}")
        print(f"   - XRP in 'XRP/USDT'.split('/'): {'XRP' in 'XRP/USDT'.split('/')}")
else:
    print("   No XRP balance found (unexpected!)")

print("\n" + "=" * 80)
