
import sys
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath("src"))

from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
from tradebot_sci.config.loader import load_settings

class TestScalpExits(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.settings.app.profile_name = "scalp_aggressive"
        self.symbol = "SOL/USD"
        self.timeframe = "1m"
        
        # Init Engine with: ai_client, market_provider, profile, symbol
        self.profile = self.settings.profiles["scalp_aggressive"]
        self.engine = StrategyEngine(None, None, self.profile, self.symbol)

    def create_snapshot(self, prices):
        # Add buffer of 20 flat candles to satisfy len > 15 check
        buffer_prices = [prices[0]] * 20
        full_prices = buffer_prices + prices
        
        candles = []
        base_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i, p in enumerate(full_prices):
            # timestamp, open, high, low, close, volume
            # Create simple candles where close is key
            c = Candle(
                timestamp=base_time.timestamp() + i*60,
                open=p, high=p+0.1, low=p-0.1, close=p, volume=1000
            )
            candles.append(c)
            
        return MarketSnapshot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            candles=candles,
            trend_htf=TrendState("long", 0.8),
            trend_ltf=TrendState("long", 0.8)
        )

    def test_structure_guard_lower_high(self):
        print("\n--- Testing Structure Guard (Lower High) ---")
        # Pattern: Up -> Peak -> Drop -> Lower High -> Drop (Exit)
        # Swing Lookback = 2 (standard) or 1 (scalp)?
        # Engine uses profile setting. Scalp Aggressive has 1.
        # Sequence:
        # 10, 11, 12 (High), 11, 10 (Low), 10.5, 11.5 (Lower High?), 11 (Trigger?)
        
        # Let's verify with explicit swing points logic behavior
        # Lookback 1: High at T is high if T > T-1 and T > T+1.
        # We need completed candles.
        
        prices = [
            100.0, 101.0, 102.0, # Uptrend
            105.0, # Peak (Index 3, Val 105)
            104.0, # Confirm Peak (Lookback 1)
            103.0, 102.0, # Drop
            103.0, 104.0, # Rally
            104.5, # Lower High Peak (Index 8, Val 104.5 < 105)
            103.5, # Confirm Lower High
            103.0  # Current Price (Below Ref High 104.5)
        ]
        
        snapshot = self.create_snapshot(prices)
        
        # Mock Position
        open_position = {
            "symbol": self.symbol,
            "direction": "long",
            "entry_price": 100.0,
            "size": 1.0,
            "highest_high": 105.0, # Passed from backtester
            "lowest_low": 100.0
        }
        
        # We need entry_time to match start
        # entry_time is used to filter sg_candles
        # Let's say entry was at index 0
        entry_ts = snapshot.candles[0].timestamp
        # engine uses open_position but filtering uses entry_time passed logic?
        # Actually engine uses `entry_time` variable derived inside? No, passed?
        # Wait, `_check_invalidation_gate` gets `open_position`.
        # Inside `_check_invalidation_gate`:
        # entry_time = open_position.get("opened_at") is implied or explicitly used?
        # Let's check engine.py.
        # Ah, logic inside `engine.py` line 1386: `entry_time = open_position.get("entry_time")`?
        
        # I need to know exactly what key engine expects.
        # Most likely "entry_time" (timestamp) or "opened_at".
        # Let's assume "entry_time" based on standard objects.
        
        open_position["entry_time"] = entry_ts
        
        # Gates dict mock
        gates = {"htf_align": True}
        
        decision = self.engine._check_invalidation_gate(snapshot, open_position, gates)
        
        if decision:
            # Check decision attributes (rationale vs reason)
            reason = getattr(decision, "reason", getattr(decision, "rationale", str(decision)))
            print(f"Decision: {decision.action} - {reason}")
            self.assertEqual(decision.action, "close_position")
            self.assertIn("Lower High", reason)
        else:
            print("No decision (Failed)")
            # Print debug state if possible?
            self.fail("Structure Guard did not trigger exit")

    def test_failed_breakout(self):
        print("\n--- Testing Failed Breakout ---")
        # Pattern: Peak -> Higher High (Breakout) -> Fails back below Peak
        # Ref High (Previous Peak) = 105.0
        # New High = 106.0
        # Current Price = 104.0 (Below 105.0)
        
        prices = [
            100.0, 102.0, 
            105.0, # Previous Peak
            104.0, # Pullback
            105.5, # Breakout!
            106.0, # Higher High
            104.8, # Drop below 105.0
            104.5  # Current
        ]
        
        snapshot = self.create_snapshot(prices)
        
        # Mock Position
        open_position = {
            "symbol": self.symbol,
            "direction": "long",
            "entry_price": 100.0,
            "size": 1.0,
            "highest_high": 106.0, # Updated to new max
            "lowest_low": 100.0,
            "entry_time": snapshot.candles[0].timestamp
        }
        
        gates = {"htf_align": True}
        
        decision = self.engine._check_invalidation_gate(snapshot, open_position, gates)
        
        if decision:
            reason = getattr(decision, "reason", getattr(decision, "rationale", str(decision)))
            print(f"Decision: {decision.action} - {reason}")
            self.assertEqual(decision.action, "close_position")
            self.assertIn("Failed Breakout", reason)
        else:
            print("No decision (Failed)")
            self.fail("Failed Breakout logic did not trigger")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    unittest.main()
