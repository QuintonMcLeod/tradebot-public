
import os
import ccxt
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(".env")
exchange = ccxt.coinbase({
    'apiKey': os.getenv("CCXT_API_KEY"),
    'secret': os.getenv("CCXT_SECRET"),
    'options': {'defaultType': 'future'}
})

def hunt():
    print(f"\n--- Deep Scan: Affordable US Futures (Cost < $150) ---")
    print(f"{'SYMBOL':<20} {'ID':<18} {'NOTIONAL':<10} {'MARGIN%':<8} {'COST($)':<10}")
    print("-" * 80)
    
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"Error loading markets: {e}")
        return

    candidates = []

    for symbol, m in markets.items():
        mid = m['id']
        
        # STRICTLY US Derivatives (CDE)
        if 'CDE' not in mid:
            continue
            
        try:
            # Get Price (Use info price or fetch ticker if needed, but ticker is slow for all)
            info = m.get('info', {})
            settle_price = float(info.get('settlement_price', 0))
            if settle_price == 0:
                 # Fallback to ticker
                 tk = exchange.fetch_ticker(symbol)
                 settle_price = tk['last']
            
            c_size = float(m.get('contractSize', 1.0))
            notional = settle_price * c_size
            
            # Margin Rate
            intra = info.get('intraday_margin_rate', {})
            # Default to 20% if missing, or max of L/S
            raw_rate = max(float(intra.get('long_margin_rate', 0.2)), float(intra.get('short_margin_rate', 0.2)))
            
            cost = notional * raw_rate
            
            candidates.append({
                'symbol': symbol,
                'id': mid,
                'notional': notional,
                'rate': raw_rate,
                'cost': cost
            })
            
        except Exception as e:
            # print(f"Skip {symbol}: {e}")
            pass

    # Sort by Cost
    candidates.sort(key=lambda x: x['cost'])
    
    found_any = False
    for c in candidates:
        # Show anything under $150
        if c['cost'] < 160:
            found_any = True
            mark = "✅" if c['cost'] < 80 else "❌"
            print(f"{mark} {c['symbol']:<18} {c['id']:<18} ${c['notional']:<9.2f} {c['rate']*100:<7.1f}% ${c['cost']:<9.2f}")
            
    if not found_any:
        print("No assets found under $150 margin cost.")

if __name__ == "__main__":
    hunt()
