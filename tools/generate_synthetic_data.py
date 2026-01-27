
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Config
# Friday Jan 23 2026
START_TIME = datetime(2026, 1, 23, 8, 0, 0, tzinfo=timezone.utc) # 8 AM UTC (3 AM EST)
# End at Saturday morning
END_TIME = datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"
OUTPUT_FILE = OUTPUT_DIR / "EURUSD_1m.json"

def generate_candle(timestamp, base_price, volatility):
    # Create a candle with some noise and volatility
    # Volatility determines the high/low range
    # Trend determines close relative to open
    
    # Random walk
    change = (random.random() - 0.5) * volatility
    
    open_p = base_price
    close_p = base_price + change
    
    high_p = max(open_p, close_p) + (random.random() * volatility * 0.5)
    low_p = min(open_p, close_p) - (random.random() * volatility * 0.5)
    
    return {
        "timestamp": timestamp.isoformat(),
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "volume": random.randint(100, 5000)
    }

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    candles = []
    current_time = START_TIME
    price = 1.1000
    
    # Phases:
    # 08:00 - 16:00 UTC (3am - 11am EST): MORNING SESSION
    # Normal volatility, some trends.
    
    # 16:00 - 17:00 UTC (11am - 12pm EST): LUNCH
    # Flat.
    
    # 17:00 - 22:00 UTC (12pm - 5pm EST): AFTERNOON "DRIFT" (= KILL ZONE)
    # High volatility, whipsaws. This is where Friday Fade saves us.
    
    # 18:00 UTC = 13:00 EST (1 PM). Fade starts at 12 PM EST (17:00 UTC).
    
    while current_time < END_TIME:
        # Determine strict UTC hour
        h = current_time.hour
        
        # Volatility Profile
        if 8 <= h < 17: 
            # Morning (Pre-Fade). Good trading.
            # Make price sine-wave to trigger mean reversion (Reaper loves this)
            # Period: 1 hour. Amplitude: 0.0020
            elapsed_min = (current_time - START_TIME).total_seconds() / 60
            wave = math.sin(elapsed_min / 60.0 * 2 * math.pi) * 0.0020
            base = 1.1000 + wave
            vol = 0.0005 # Tight enough for signals
        elif 17 <= h < 22:
            # Afternoon (Fade Active). High Risk.
            # Whipsaws.
            # Period: 15 mins (FAST). Amplitude: 0.0030
            elapsed_min = (current_time - START_TIME).total_seconds() / 60
            wave = math.sin(elapsed_min / 15.0 * 2 * math.pi) * 0.0030
            base = 1.1000 + wave
            vol = 0.0010 # High vol
        else:
            # Overnight / Late
            base = 1.1000
            vol = 0.0001
            
        c = generate_candle(current_time, base, vol)
        candles.append(c)
        current_time += timedelta(minutes=1)
        
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(candles, f, indent=2)
        
    print(f"Generated {len(candles)} candles to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
