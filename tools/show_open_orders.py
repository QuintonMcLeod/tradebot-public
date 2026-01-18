import asyncio
import os
import sys
from ib_insync import IB

async def main():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 7497, clientId=145)
    except Exception as e:
        print(f"Could not connect: {e}")
        return

    # Use the CORRECT method now :)
    trades = ib.openTrades()
    orders = ib.openOrders()
    
    print(f"--- Connected. Found {len(orders)} Raw Orders and {len(trades)} Trade Wrappers ---")
    
    if not orders:
        print("No open orders found.")
    else:
        for o in orders:
            print(f"OPEN ORDER: {o.action} {o.totalQuantity} {o.contract.localSymbol} @ {o.lmtPrice or o.auxPrice or 'MKT'} ({o.orderType})")
            print(f"   Status: {o.orderStatus if hasattr(o, 'orderStatus') else 'Unknown'}")
            print(f"   Ref: {o.orderRef}")
            print("-" * 20)

    ib.disconnect()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
