import logging
import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tradebot_sci.config.models import Settings, TradingProfileSettings
from tradebot_sci.runtime.sabbath import SabbathContext
from tradebot_sci.broker.paper_broker import PaperBroker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sabbath_swap():
    # Mock settings with required fields
    profile = TradingProfileSettings(
        sabbath_enabled=True,
        sabbath_timezone="America/New_York",
        sabbath_start_local="18:00",
        sabbath_end_local="18:00",
        sabbath_astronomical=False,
        candle_timeframe="1h",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )
    
    # 1. Simulate NON-Sabbath (Friday 12:00 PM)
    non_sabbath_time = datetime(2026, 2, 6, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    s_ctx = SabbathContext(profile)
    is_active, _, _ = s_ctx.evaluate(non_sabbath_time)
    print(f"Friday 12:00 PM - Sabbath Active: {is_active} (Expected: False)")
    
    # 2. Simulate SABBATH (Friday 8:00 PM)
    sabbath_time = datetime(2026, 2, 6, 20, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    is_active, _, _ = s_ctx.evaluate(sabbath_time)
    print(f"Friday 8:00 PM - Sabbath Active: {is_active} (Expected: True)")
    
    # 3. Test Paper Broker
    paper = PaperBroker(profile)
    print(f"Paper Balance: ${paper.get_liquid_capital()}")
    
    # Mock decision to avoid pydantic validation
    decision = MagicMock()
    decision.symbol = "BTCUSD"
    decision.action = "enter_long"
    
    res, outcome = paper.execute_decision(decision)
    print(f"Paper Entry Result: {res.status}")
    print(f"Paper Positions: {paper.list_open_position_symbols()}")

if __name__ == "__main__":
    test_sabbath_swap()
