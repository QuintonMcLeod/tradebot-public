from datetime import datetime, timezone
import json
import os
import sys

from tradebot_sci.config.settings_manager import load_settings, load_active_profile
from tradebot_sci.runtime.provider_factory import build_exchange_broker

settings = load_settings('/home/qchan/.config/tradebot-sci/config.json')
profile = load_active_profile(settings)

broker = build_exchange_broker(settings, profile)
print(f"Prop FTMO Enabled in Profile: {getattr(profile, 'prop_ftmo_enabled', False)}")
print(f"Prop FTMO Enabled in Settings: {settings.risk.prop_ftmo_enabled}")
print(f"Broker class: {type(broker)}")
print(f"Liquid Capital: {broker.get_liquid_capital()}")
print(f"Display Cash: {broker.get_display_cash()}")
