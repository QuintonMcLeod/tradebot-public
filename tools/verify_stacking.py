
import os
import sys
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from tradebot_sci.strategy.safety_guard import SafetyGuard
from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.strategy.decisions import AITradeDecision

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY")

def test_stacking():
    print("\n--- Testing Multi-Mode Stacking (New Modes) ---")
    
    # Setup Context: Test Whale + Contrarian + Surfer
    os.environ["PERFORMANCE_MODE"] = "whale,contrarian,surfer"
    
    # Mock Candles for Whale (Volume Spike) + Contrarian (RSI Fade)
    mock_candles = []
    base_atr = 100
    for i in range(25): # Need > 20 for averages
        vol = 1000
        close = 50000 + (i*100) # Uptrend
        if i == 24: 
            vol = 5000 # Spike (Whale)
            close = 60000 # Pump (Contrarian Fade potential if short)
        
        c = Candle(timestamp=0, open=close, high=close+10, low=close-10, close=close, volume=vol)
        mock_candles.append(c)
        
    snapshot = MarketSnapshot(symbol="BTC/USD", timeframe="1h", candles=mock_candles, trend_htf="SIDEWAYS", trend_ltf="SIDEWAYS")

    # decision: Shorting into a pump (Contrarian)
    decision = AITradeDecision(
        symbol="BTC/USD", 
        timeframe="1h", 
        action="enter_short", 
        risk_per_trade_pct=0.01,
        bias="short",
        phase="trend",
        structure_summary="Test",
        invalidation_conditions="Inv",
        management_instructions="Mgmt",
        notes="Init"
    )
    
    # Run Augment
    # Base: 0.01
    # Whale: Vol 5000 > 1000*2 -> 1.3x -> 0.013
    # Contrarian: Pumped > 3% & Short -> 1.5x -> 0.0195
    # Surfer: (Requires ATR mock, not mocking perfectly here, assumes fallthrough or trigger depending on data).
    # NOTE: Surfer checks recent_atr < med_atr * 0.8.
    # Our mocked candles are uniform except last. ATR might be stable. Thus Surfer might NOT trigger.
    # We clarify this in validation expectation.
    
    augmented = SafetyGuard.augment_entry_decision(decision, score=50, htf_strength=0.5, snapshot=snapshot)
    
    print(f"Modes: {SafetyGuard.get_active_wealth_modes()}")
    print(f"Final Risk: {augmented.risk_per_trade_pct:.5f}")
    print(f"Notes: {augmented.notes}")
    
    # Validation
    # We expect at least Whale (1.3x) and Contrarian (1.5x) => 0.01 * 1.3 * 1.5 = 0.0195
    
    if augmented.risk_per_trade_pct >= 0.0195:
        print("✅ New Multipliers Verified (Whale + Contrarian triggers).")
    else:
        print(f"❌ Logic Check Failed. Risk: {augmented.risk_per_trade_pct}")

def test_ai_shield_cache():
    print("\n--- Testing AI Shield Caching ---")
    os.environ["SAFETY_SENTIMENT_SHIELD_ENABLED"] = "true"
    
    mock_ai = MagicMock()
    mock_ai.generate_text.return_value = "SAFE"
    
    snapshot = MarketSnapshot(symbol="ETH/USD", timeframe="1h", candles=[Candle(0,0,0,0,0,0)], trend_htf="UP", trend_ltf="UP")
    
    # Call 1 (Should hit API)
    print("Call 1...")
    SafetyGuard.check_entry_safety("ETH/USD", "1h", 1000, snapshot, ai_client=mock_ai)
    
    # Call 2 (Should use Cache)
    print("Call 2...")
    SafetyGuard.check_entry_safety("ETH/USD", "1h", 1000, snapshot, ai_client=mock_ai)
    
    # Verify Mock Call Count
    if mock_ai.generate_text.call_count == 1:
        print("✅ Cache verified! API was called only once.")
    else:
        print(f"❌ Cache failed. API called {mock_ai.generate_text.call_count} times.")

if __name__ == "__main__":
    test_stacking()
    test_ai_shield_cache()
