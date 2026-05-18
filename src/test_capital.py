from datetime import datetime, timezone
import json
import os
import sys

from tradebot_sci.config.loader import load_settings
from tradebot_sci.runtime.provider_factory import build_exchange_broker

settings = load_settings()
profile = settings.get_active_profile()

broker = build_exchange_broker(settings, profile, shared_ib=None, allowed_symbols=None)
print(f"Prop FTMO Enabled in Profile: {getattr(profile, 'prop_ftmo_enabled', False)}")
print(f"Prop FTMO Enabled in Settings: {settings.risk.prop_ftmo_enabled}")
print(f"Broker class: {type(broker)}")
print(f"Liquid Capital: {broker.get_liquid_capital()}")
print(f"Display Cash: {broker.get_display_cash()}")
