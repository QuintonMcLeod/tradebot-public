#!/usr/bin/env python3
"""
Check actual Coinbase balance via CCXT to debug the $59.09 vs $39.42 discrepancy.
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
print("COINBASE BALANCE CHECK")
print("=" * 80)

# Initialize Coinbase exchange
exchange = ccxt.coinbase({
    "apiKey": api_key,
    "secret": secret,
    "password": password,
    "enableRateLimit": True,
    "timeout": 30000,
    "options": {
        "createMarketBuyOrderRequiresPrice": False
    }
})

print("\n1. Loading markets...")
exchange.load_markets()
print(f"   Loaded {len(exchange.markets)} markets")

print("\n2. Fetching balance...")
balance = exchange.fetch_balance()

print("\n3. RAW BALANCE DATA:")
print("-" * 80)
pprint(balance)

print("\n4. FREE BALANCES (available for trading):")
print("-" * 80)
free = balance.get("free", {})
for currency, amount in free.items():
    if amount > 0:
        print(f"   {currency}: {amount}")

print("\n5. TOTAL BALANCES (free + used):")
print("-" * 80)
total = balance.get("total", {})
for currency, amount in total.items():
    if amount > 0:
        print(f"   {currency}: {amount}")

print("\n6. USED BALANCES (locked in orders):")
print("-" * 80)
used = balance.get("used", {})
for currency, amount in used.items():
    if amount > 0:
        print(f"   {currency}: {amount}")

print("\n7. BOT CALCULATION (what get_liquid_capital() returns):")
print("-" * 80)
usd_free = float(free.get("USD", 0.0) or 0.0)
usdt_free = float(free.get("USDT", 0.0) or 0.0)
liquid_capital = usd_free + usdt_free

print(f"   USD free: ${usd_free:.2f}")
print(f"   USDT free: ${usdt_free:.2f}")
print(f"   TOTAL LIQUID CAPITAL: ${liquid_capital:.2f}")

print("\n8. COMPARISON WITH SCREENSHOT:")
print("-" * 80)
print("   Expected USDT: $39.42 (from screenshot)")
print(f"   Actual USDT: ${usdt_free:.2f}")
print(f"   Difference: ${abs(39.42 - usdt_free):.2f}")

if abs(liquid_capital - 59.09) < 0.5:
    print("\n⚠️  WARNING: Bot is seeing $59.09, but screenshot shows only $39.42 USDT available!")
    print("   This suggests the balance includes XRP value ($9.43) somehow.")
    print("   Need to investigate why fetch_balance() is returning incorrect data.")
elif abs(liquid_capital - 39.42) < 0.5:
    print("\n✅ GOOD: Balance matches screenshot ($39.42 USDT available)")
else:
    print(f"\n❓ UNEXPECTED: Balance is ${liquid_capital:.2f}, different from both $59.09 and $39.42")

print("\n" + "=" * 80)
print("END OF BALANCE CHECK")
print("=" * 80)
