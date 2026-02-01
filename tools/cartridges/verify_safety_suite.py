
import os
import sys
import logging
from datetime import datetime
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.safety_guard import SafetyGuard
from tradebot_sci.market.models import MarketSnapshot, Candle, TrendState
from tradebot_sci.strategy.decisions import AITradeDecision

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SafetyVerifier")

def create_mock_snapshot(price=100.0, atr_val=1.0):
    c = Candle(timestamp=datetime.now(), open=price, high=price+1, low=price-1, close=price, volume=1000)
    snapshot = MarketSnapshot(
        symbol="TESTUSD",
        timeframe="5m",
        candles=[c] * 50, # Enough for ATR
        trend_htf=TrendState(direction="neutral", strength=0.5),
        trend_ltf=TrendState(direction="neutral", strength=0.5)
    )
    return snapshot

def test_greed_guard():
    logger.info("Testing Greed Guard...")
    os.environ["SAFETY_GREED_GUARD_ENABLED"] = "true"
    os.environ["SAFETY_GREED_GUARD_TARGET"] = "50.0"
    
    # Simulate hitting target
    SafetyGuard._update_daily_stats(1000.0) # Start
    SafetyGuard._update_daily_stats(1060.0) # Current (+60 profit)
    
    snap = create_mock_snapshot()
    decision = SafetyGuard.check_entry_safety("TESTUSD", "5m", 1060.0, snap)
    
    if decision and "Greed Guard Active" in decision.notes:
        logger.info("[PASS] Greed Guard blocked entry.")
    else:
        logger.error(f"[FAIL] Greed Guard failed to block. Decision: {decision}")

def test_churn_burner():
    logger.info("Testing Churn Burner...")
    os.environ["SAFETY_CHURN_BURNER_ENABLED"] = "true"
    os.environ["SAFETY_CHURN_BURNER_MAX"] = "2"
    
    SafetyGuard.TRADE_TIMESTAMPS = [] # Reset
    SafetyGuard.notify_entry()
    SafetyGuard.notify_entry()
    # Should be at limit now (2 entries)
    
    snap = create_mock_snapshot()
    decision = SafetyGuard.check_entry_safety("TESTUSD", "5m", 1000.0, snap)
    
    if decision and "Churn Burner Active" in decision.notes:
        logger.info("[PASS] Churn Burner blocked entry.")
    else:
        logger.error(f"[FAIL] Churn Burner failed to block. Decision: {decision}")

def test_streak_breaker():
    logger.info("Testing Streak Breaker...")
    os.environ["SAFETY_STREAK_BREAKER_ENABLED"] = "true"
    SafetyGuard.SYMBOL_LOSS_STREAKS["TESTUSD"] = 3
    
    snap = create_mock_snapshot()
    decision = SafetyGuard.check_entry_safety("TESTUSD", "5m", 1000.0, snap)
    
    if decision and "Streak Breaker Triggered" in decision.notes:
        logger.info("[PASS] Streak Breaker blocked entry.")
    else:
        logger.error(f"[FAIL] Streak Breaker failed to block. Decision: {decision}")

if __name__ == "__main__":
    test_greed_guard()
    test_churn_burner()
    test_streak_breaker()
