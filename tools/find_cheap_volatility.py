
import os
import ccxt
import json
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

def find_gems():
    api_key = os.getenv("CCXT_API_KEY")
    api_secret = os.getenv("CCXT_SECRET")
    
    if api_secret and "\\n" in api_secret and "\n" not in api_secret:
        api_secret = api_secret.replace("\\n", "\n")

    print("[INFO] Connecting to Coinbase Futures...")
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'},
    })

    try:
        markets = exchange.load_markets()
        print(f"[INFO] Scanning {len(markets)} markets...")
        
        candidates = []
        
        for symbol, m in markets.items():
            if not m.get('linear'): continue # Only futures
            if "DEC30" in symbol: continue # Skip the generic nano ETP/BIP placeholders if duplicates
            
            info = m.get("info")
            if not info: continue
            
            price_str = info.get("price")
            if not price_str: continue
            
            price = float(price_str)
            contract_size = float(m.get("contractSize") or 1.0)
            
            # Get Margin Rate (Default to 25% if unknown)
            future_details = info.get("future_product_details") or {}
            margin_rates = future_details.get("intraday_margin_rate") or {}
            long_rate_str = margin_rates.get("long_margin_rate", "0.25")
            margin_rate = float(long_rate_str)
            
            # Calculate metrics
            notional_value = price * contract_size
            margin_req = notional_value * margin_rate
            
            # Volatility (24h Change)
            change_24h = float(info.get("price_percentage_change_24h") or 0.0)
            volume_24h = float(info.get("approximate_quote_24h_volume") or 0.0)
            
            # Filter: Margin < $70 (Leave room for fees)
            if margin_req < 70 and margin_req > 1:
                candidates.append({
                    "symbol": symbol,
                    "notional": notional_value,
                    "margin": margin_req,
                    "volatility": abs(change_24h),
                    "volume": volume_24h
                })
        
        # Sort by Volatility (High to Low)
        candidates.sort(key=lambda x: x['volatility'], reverse=True)
        
        print(f"{'SYMBOL':<25} | {'MARGIN':<10} | {'NOTIONAL':<10} | {'VOL (24H)':<10} | {'VOLUME':<15}")
        print("-" * 80)
        
        for c in candidates:
            # Filter out low liquidity junk (<$100k volume)
            if c['volume'] > 100000:
                print(f"{c['symbol']:<25} | ${c['margin']:<9.2f} | ${c['notional']:<9.2f} | {c['volatility']:<9.2f}% | ${c['volume']:<15,.0f}")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    find_gems()
