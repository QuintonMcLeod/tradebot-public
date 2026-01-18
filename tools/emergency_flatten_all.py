#!/usr/bin/env python3
"""
EMERGENCY POSITION FLATTEN SCRIPT

PURPOSE: Close ALL open positions and consolidate capital back to USD.

WHEN TO USE THIS:
- Bot has multiple stuck positions
- Capital is fragmented across many assets
- Need to start fresh with clean slate

WHAT THIS DOES:
1. Connects to Coinbase exchange
2. Checks ALL your crypto balances
3. Sells EVERYTHING back to USD
4. Shows final USD balance

IMPORTANT: This will close ALL positions. Make sure you want to do this!
"""

import ccxt
import os
import sys
import time
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("=" * 60)
    print("EMERGENCY POSITION FLATTEN SCRIPT")
    print("=" * 60)
    print()

    # Connect to exchange
    print("Step 1: Connecting to Coinbase...")
    try:
        # [ANTIGRAVITY FIX] Normalize PEM key newlines
        api_secret = os.getenv('CCXT_SECRET', '')
        if api_secret:
            api_secret = api_secret.replace('\\n', '\n')

        exchange = ccxt.coinbase({
            'apiKey': os.getenv('CCXT_API_KEY'),
            'secret': api_secret,
        })
        print("✅ Connected to Coinbase\n")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)

    # Get all balances
    print("Step 2: Fetching all balances...")
    try:
        balance = exchange.fetch_balance()
        print("✅ Balances retrieved\n")
    except Exception as e:
        print(f"❌ Failed to fetch balance: {e}")
        sys.exit(1)

    # Show current state
    print("=" * 60)
    print("CURRENT POSITIONS:")
    print("=" * 60)

    total_usd = balance['total'].get('USD', 0)
    print(f"USD: ${total_usd:.2f}\n")

    positions_to_close = []
    for currency, amount in balance['total'].items():
        if currency == 'USD':
            continue
        if amount > 0:
            print(f"{currency}: {amount}")
            positions_to_close.append((currency, amount))

    if not positions_to_close:
        print("\n✅ No positions to close. You're already all in USD.")
        print(f"Final balance: ${total_usd:.2f}")
        return

    print(f"\nFound {len(positions_to_close)} position(s) to close.\n")

    # Confirm with user
    print("=" * 60)
    print("⚠️  WARNING: This will SELL ALL positions above!")
    print("=" * 60)
    response = input("\nType 'YES' to proceed with flattening: ")

    if response != 'YES':
        print("❌ Cancelled. No positions closed.")
        return

    print("\n" + "=" * 60)
    print("CLOSING POSITIONS:")
    print("=" * 60)
    print()

    # Close each position
    closed_count = 0
    failed_count = 0

    for currency, amount in positions_to_close:
        symbol = f"{currency}/USD"
        print(f"Closing {symbol}: {amount} units...")

        try:
            # Cancel open orders logic (Manual fetch + cancel)
            try:
                open_orders = exchange.fetch_open_orders(symbol)
                for order in open_orders:
                    print(f"  Cancelling order {order['id']}...")
                    exchange.cancel_order(order['id'], symbol)
                    time.sleep(0.5)
                if open_orders:
                    print(f"  ✅ Cancelled {len(open_orders)} open orders for {symbol}")
                    time.sleep(2) # Wait for unlock
            except Exception as e:
                print(f"  ⚠️  Failed to cancel orders for {symbol}: {e}")
                
            # Place market sell order
            # Re-fetch balance to get full unlocked amount
            # (Skipping full re-fetch for speed, assuming unlocked amount is close enough)
            order = exchange.create_market_sell_order(symbol, amount)
            print(f"  ✅ Sold {amount} {currency}")
            print(f"     Order ID: {order['id']}")
            closed_count += 1
            time.sleep(1)  # Small delay between orders

        except Exception as e:
            print(f"  ❌ Failed to close {symbol}: {e}")
            failed_count += 1

        print()

    # Wait for orders to settle
    print("Waiting 3 seconds for orders to settle...")
    time.sleep(3)

    # Check final balance
    print("\n" + "=" * 60)
    print("FINAL STATE:")
    print("=" * 60)

    try:
        final_balance = exchange.fetch_balance()
        final_usd = final_balance['total'].get('USD', 0)

        print(f"\n✅ Final USD balance: ${final_usd:.2f}")

        # Check for any remaining positions
        remaining = []
        for currency, amount in final_balance['total'].items():
            if currency == 'USD':
                continue
            if amount > 0:
                remaining.append((currency, amount))

        if remaining:
            print("\n⚠️  WARNING: Some positions remain:")
            for currency, amount in remaining:
                print(f"  {currency}: {amount}")
            print("\nThese may be:")
            print("  - Dust amounts too small to trade")
            print("  - Positions that failed to close")
        else:
            print("\n✅ All positions successfully closed!")

    except Exception as e:
        print(f"❌ Failed to fetch final balance: {e}")

    print("\n" + "=" * 60)
    print(f"SUMMARY:")
    print(f"  Closed: {closed_count} position(s)")
    print(f"  Failed: {failed_count} position(s)")
    print("=" * 60)

if __name__ == "__main__":
    main()
