import sys
import logging
from tradebot_sci.config.loader import load_settings

logging.basicConfig(level=logging.INFO)
settings = load_settings()

print("\n--- OANDA CONFIG ---")
print(settings.oanda.model_dump_json(indent=2))
print("--- END ---")
