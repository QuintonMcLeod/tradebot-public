import ccxt
import sys

def main():
    kraken = ccxt.kraken()
    print("Loading Kraken markets...")
    try:
        markets = kraken.load_markets()
    except Exception as e:
        print(f"Error loading markets: {e}")
        return

    print(f"Found {len(markets)} markets.")
    
    targets = ["XAU", "XAG", "XPD", "XPT", "GOLD", "SILVER", "EUR", "GBP", "USD", "BTC", "ETH"]
    
    print("\n--- Searching for Metals & Forex ---")
    for symbol in markets:
        # Check against targets
        for t in targets:
             if t in symbol:
                 print(f"Found potential match: {symbol} (Base: {markets[symbol]['base']}, Quote: {markets[symbol]['quote']})")
                 break

if __name__ == "__main__":
    main()
