#!/usr/bin/env python3
"""
Scans Gemini via CCXT for high-volume USD pairs.
"""
import ccxt
import sys

def main():
    print("Connecting to Gemini public API...")
    try:
        gemini = ccxt.gemini()
        markets = gemini.load_markets()
    except Exception as e:
        print(f"Error connecting to Gemini: {e}")
        sys.exit(1)

    print(f"Loaded {len(markets)} markets.")
    
    # Filter for USD pairs
    usd_pairs = []
    print("Scanning markets...")
    for symbol, market in markets.items():
        # if not market.get('active'):
        #     print(f"DEBUG: {symbol} inactive")
        #     continue
        if market.get('quote') != 'USD':
            # print(f"DEBUG: {symbol} quote is {market.get('quote')}")
            continue
        if market.get('base') in ['GUSD', 'USDT', 'USDC', 'DAI']: 
            continue
            
        try:
            # print(f"DEBUG: Fetching ticker for {symbol}")
            ticker = gemini.fetch_ticker(symbol)
            vol_usd = ticker.get('quoteVolume')
            if vol_usd is None:
                # Fallback if quoteVolume isn't direct
                vol_base = ticker.get('baseVolume')
                last_price = ticker.get('last')
                if vol_base and last_price:
                    vol_usd = vol_base * last_price
            
            # print(f"DEBUG: {symbol} vol_usd={vol_usd}")
            
            if vol_usd is not None:
                usd_pairs.append({
                    'symbol': symbol,
                    'base': market.get('base'),
                    'volume_usd': vol_usd,
                    'last': ticker.get('last')
                })
        except Exception as e:
            # print(f"DEBUG: Error fetching {symbol}: {e}")
            pass

    # Sort by volume descending
    usd_pairs.sort(key=lambda x: x['volume_usd'], reverse=True)

    print("\nTop 10 High-Volume USD Pairs on Gemini:")
    print(f"{'Symbol':<10} {'Price':<10} {'24h Volume (USD)':<20}")
    print("-" * 45)
    
    for p in usd_pairs[:10]:
        vol_str = f"${p['volume_usd']:,.0f}"
        print(f"{p['symbol']:<10} ${p['last']:<9.2f} {vol_str:<20}")

    print("\nRecommended Top 6 for Config:")
    top_6 = [p['symbol'].replace('/USD', 'USD') for p in usd_pairs[:6]]
    print(", ".join(top_6))

if __name__ == "__main__":
    main()
