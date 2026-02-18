import sys
import os
from datetime import datetime, timezone
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.profiles import BaseProfile
from tradebot_sci.config.models import UserConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockProfile(BaseProfile):
    def __init__(self):
        self.icc_auto_entry_enabled = True
        self.icc_auto_entry_require_sweep = False
        self.icc_risk_per_trade = 0.01

def create_candles(prices):
    return [
        Candle(
            timestamp=datetime.now(timezone.utc),
            open=p, high=p*1.001, low=p*0.999, close=p, volume=100
        ) for p in prices
    ]

def test_fast_exit_logic():
    engine = StrategyEngine(ai_client=None, market_provider=None, profile=MockProfile(), symbol="TESTUSD")
    
    # 1. Test CHOP TP (3 bars of chop while in profit)
    print("\n--- Test 1: CHOP TP ---")
    prices = [100.0] * 50
    candles = create_candles(prices)
    snapshot = MarketSnapshot(
        symbol="TESTUSD",
        timeframe="5m",
        candles=candles,
        ltf_candles=candles,
        htf_candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.1),
        trend_ltf=TrendState(direction="neutral", strength=0.1)
    )
    
    open_pos = {
        "symbol": "TESTUSD",
        "direction": "long",
        "entry_price": 99.0, # Profitable
        "unrealized_pnl": 1.0,
        "size": 100
    }
    
    # Run decide multiple times to accumulate chop bars
    for i in range(4):
        decision = engine.decide("5m", open_position=open_pos, snapshot=snapshot)
        print(f"Iteration {i+1}: Action={decision.action}, Reason={decision.structure_summary}")
        if decision.action == "close_position":
            print("SUCCESS: Chop TP triggered!")
            break

    # 2. Test ROBO FAST FAIL (Opposite Armed + Lack of HTF Support)
    print("\n--- Test 2: ROBO FAST FAIL ---")
    # Simulate a bearish correction after a bullish indication (against a long position)
    # Long position, HTF neutral, LTF bearish
    prices = [100.0, 101.0, 100.5, 100.6] 
    candles = create_candles(prices)
    snapshot = MarketSnapshot(
        symbol="TESTUSD",
        timeframe="5m",
        candles=candles,
        ltf_candles=candles,
        htf_candles=candles,
        trend_htf=TrendState(direction="neutral", strength=0.1),
        trend_ltf=TrendState(direction="short", strength=0.4)
    )
    
    decision = engine.decide("5m", open_position=open_pos, snapshot=snapshot)
    print(f"Fast Fail Check: Action={decision.action}, Reason={decision.structure_summary}")

if __name__ == "__main__":
    test_fast_exit_logic()
