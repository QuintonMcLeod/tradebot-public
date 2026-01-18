
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.append(os.getcwd() + "/src")

from tradebot_sci.config.models import TradingProfileSettings
from tradebot_sci.runtime.loop import SabbathContext, _is_sabbath_now

# Mock settings
profile = TradingProfileSettings(
    candle_timeframe="5m",
    market_poll_interval_seconds=60,
    ai_decision_interval_seconds=60,
    sabbath_enabled=True,
    sabbath_timezone="America/New_York",
    sabbath_start_local="18:00",
    sabbath_end_local="18:00"
)

# Current time (approximate based on user metadata)
# User said 18:07 EST
now_est = datetime.now(ZoneInfo("America/New_York"))
now_utc = datetime.now(ZoneInfo("UTC"))

print(f"Current Time (EST): {now_est}")
print(f"Current Time (UTC): {now_utc}")

context = SabbathContext(profile, None)
is_active, _, _ = context.evaluate(now_utc)

print(f"Sabbath Active via Context: {is_active}")

# Test underlying function
is_active_func, end_time = _is_sabbath_now(now_utc, profile, False)
print(f"Sabbath Active via Function: {is_active_func}")
print(f"Sabbath End Time: {end_time}")
