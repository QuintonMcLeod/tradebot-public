import json
import os
from datetime import datetime

def main():
    path = "data/forex_backtest/EURUSD_5m.json"
    if not os.path.exists(path):
        print("Error: File not found")
        return

    with open(path, 'r') as f:
        data = json.load(f)

    # Filter Jan 5, 6, 7, 2026
    start_date = "2026-01-05"
    end_date = "2026-01-07 23:59:59"
    
    filtered = []
    for bar in data:
        ts = bar['timestamp']
        if start_date <= ts <= end_date:
            filtered.append(bar)

    print(f"## Appendix A: Reference Market Data (EUR/USD Jan 5-7 2026)")
    print(f"**Context**: This dataset covers the 'Choppy' period leading into the volatility event.")
    print("```json")
    print("[")
    # Print first 5, middle 5, last 5 to keep it concise but representative? 
    # User said "3 days worth so other AIs have something to work with".
    # 3 days of 5m data = roughly 864 bars. That's a lot of text for an LLM prompt.
    # I will provide a condensed View: Open, High, Low, Close, Timestamp.
    # Actually, offering the full JSON for a shorter window (e.g. the specific crash hours) might be better, 
    # but the user asked for 3 days.
    # I'll output the first 50 bars key moments to save tokens, OR just dump it all to a separate file 
    # and reference it.
    # Wait, the user wants me to put it IN the dissertation.
    # 864 lines is too long for a markdown artifact meant for chat.
    # I will compress it: 1H candles? Or just specific 5m bars?
    # No, I'll output the full JSON structure but truncated to the first 100 bars of the crash day (Jan 7)
    # as a sample, and describe the rest.
    # User said "3 days worth". This implies they want the data.
    # I will format it as CSV, it's more compact.
    print("timestamp,open,high,low,close")
    for bar in filtered:
        print(f"{bar['timestamp']},{bar['open']},{bar['high']},{bar['low']},{bar['close']}")
    print("]")
    print("```")

if __name__ == "__main__":
    main()
