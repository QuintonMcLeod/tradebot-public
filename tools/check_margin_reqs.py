
import os
import ccxt
import json
from dotenv import load_dotenv

load_dotenv(".env")
exchange = ccxt.coinbase({
    'apiKey': os.getenv("CCXT_API_KEY"),
    'secret': os.getenv("CCXT_SECRET"),
    'options': {'defaultType': 'future'}
})

def check_margin():
    print("--- US Futures Margin Requirements ---")
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"Error: {e}")
        return

    targets = ['DOG', 'LTC', 'ETH', 'SOL', 'AVA', 'LNK', 'BIT']
    
    print(f"{'SYMBOL':<15} {'ID':<18} {'NOTIONAL':<10} {'INTRA(LEV)':<12} {'COST($)':<9} {'OVERN($)'}")
    print("-" * 90)

    for symbol, m in markets.items():
        mid = m['id']
        # Filter for our specific targets (Nano/CDE)
        is_target = False
        for t in targets:
            if t in mid and 'CDE' in mid:
                is_target = True
                break
        
        if is_target:
            try:
                # Fetch price
                ticker = exchange.fetch_ticker(symbol)
                price = ticker['last'] or 0
                c_size = float(m.get('contractSize', 1.0))
                notional = price * c_size
                
                info = m.get('info', {})
                
                # Parse Margin Rates
                intra = info.get('intraday_margin_rate', {})
                over = info.get('overnight_margin_rate', {})
                
                # Get max of long/short to be safe
                i_rate = float(max(intra.get('long_margin_rate', 0.2), intra.get('short_margin_rate', 0.2)))
                o_rate = float(max(over.get('long_margin_rate', 1.0), over.get('short_margin_rate', 1.0)))
                
                # Calculate $ Cost
                cost_intra = notional * i_rate
                cost_over = notional * o_rate
                
                # Margin = 1/Rate (e.g. 0.10 = 10x)
                lev_intra = int(1/i_rate) if i_rate > 0 else 1
                
                print(f"{symbol:<15} {mid:<18} ${notional:<9.2f} {i_rate*100:<5.1f}% ({lev_intra}x) ${cost_intra:<8.2f} ${cost_over:<8.2f}")
                
            except Exception as e:
                print(f"Err {symbol}: {e}")
                pass
                
            except Exception as e:
                pass

    # print("\n[NOTE] Fetching raw info for one example (ETH) to find margin keys...")
    # for symbol, m in markets.items():
    #     if 'ETH' in symbol and 'CDE' in m['id']:
    #          print(json.dumps(m['info'], indent=2))
    #          break
             
if __name__ == "__main__":
    check_margin()
