
import sys
import os

strategies = [
    "tradebot_sci.strategy.variants.breakout",
    "tradebot_sci.strategy.variants.evolution",
    "tradebot_sci.strategy.variants.hyper_scalper",
    "tradebot_sci.strategy.variants.icc_core",
    "tradebot_sci.strategy.variants.london_breakout",
    "tradebot_sci.strategy.variants.mean_reversion",
    "tradebot_sci.strategy.variants.quantum",
    "tradebot_sci.strategy.variants.robocop",
    "tradebot_sci.strategy.variants.rubberband_reaper",
    "tradebot_sci.strategy.variants.supply_demand",
]

print("Verifying Strategy Imports...")
for s in strategies:
    try:
        __import__(s)
        print(f"✅ {s} imported successfully.")
    except Exception as e:
        print(f"❌ {s} FAILED: {e}")
        sys.exit(1)
        
print("All strategies verify OK.")
