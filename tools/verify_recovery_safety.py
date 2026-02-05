from __future__ import annotations
import os
import sys
import logging
from datetime import datetime

# Setup paths
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from tradebot_sci.strategy.safety_guard import SafetyGuard
from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.strategy.decisions import AITradeDecision

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_leverage_sentry():
    print("\n--- Testing Leverage Sentry ---")
    os.environ["SAFETY_LEVERAGE_SENTRY_ENABLED"] = "true"
    os.environ["SAFETY_MAX_TOTAL_LEVERAGE"] = "3.0"
    
    # Simulate $27 capital
    capital = 27.0
    
    # 1. Existing $100 notional position (3.7x leverage)
    SafetyGuard.GLOBAL_POSITIONS = {
        "EURUSD": {"symbol": "EURUSD", "avg_price": 1.08, "size": 93} # ~100.44 value
    }
    
    from tradebot_sci.market.models import TrendState
    trend = TrendState(direction="neutral", strength=0.0)
    snapshot = MarketSnapshot(
        symbol="GBPUSD", 
        timeframe="5m", 
        candles=[Candle(timestamp=datetime.now(), open=1.27, high=1.28, low=1.26, close=1.27, volume=100)],
        trend_htf=trend,
        trend_ltf=trend
    )
    
    print(f"Scenario 1: $27 capital, $100 open position (3.7x leverage). Limit is 3.0x.")
    decision = SafetyGuard.check_entry_safety("GBPUSD", "5m", capital, snapshot)
    
    if decision and "Leverage Sentry" in decision.notes:
        print(f"✅ PASSED: Leverage Sentry blocked entry. Notes: {decision.notes}")
    else:
        print(f"❌ FAILED: Leverage Sentry did NOT block entry. Outcome: {decision}")

    # 2. Within limits
    SafetyGuard.GLOBAL_POSITIONS = {
        "EURUSD": {"symbol": "EURUSD", "avg_price": 1.08, "size": 25} # ~27 value (1x leverage)
    }
    print(f"\nScenario 2: $27 capital, $27 open position (1x leverage). Limit is 3.0x.")
    decision = SafetyGuard.check_entry_safety("GBPUSD", "5m", capital, snapshot)
    
    if decision is None:
        print("✅ PASSED: Leverage Sentry allowed entry.")
    else:
        print(f"❌ FAILED: Leverage Sentry blocked entry but shouldn't have. Reason: {decision.reason}")

if __name__ == "__main__":
    test_leverage_sentry()
