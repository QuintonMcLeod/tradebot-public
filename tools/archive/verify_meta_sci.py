
import sys
import os
sys.path.insert(0, os.path.abspath("src"))
import logging
import unittest
from unittest.mock import MagicMock
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.market.models import MarketSnapshot, TrendState
from tradebot_sci.strategy.decisions import AITradeDecision

# Disable logging
logging.disable(logging.CRITICAL)

class TestMetaSCI(unittest.TestCase):
    def setUp(self):
        self.mock_provider = MagicMock()
        self.mock_profile = MagicMock()
        self.mock_profile.meta_sci_enabled = True
        self.mock_profile.meta_sci_min_consensus = 1
        self.mock_profile.meta_sci_exclude_list = []
        
        # Initialize Engine 
        self.engine = StrategyEngine(None, self.mock_provider, self.mock_profile, "BTCUSD")
        self.engine._strategy = MagicMock()
        self.engine._strategy.name = "meta_sci"

    def test_ensemble_ranking(self):
        """Test that Meta-SCI selects the strategy with the highest score."""
        # Setup real trend objects
        trend_htf = TrendState(direction="long", strength=0.8)
        trend_ltf = TrendState(direction="long", strength=0.9)
        
        snapshot = MarketSnapshot(
            symbol="BTCUSD",
            timeframe="5m",
            candles=[],
            trend_htf=trend_htf,
            trend_ltf=trend_ltf
        )
        
        # Mocking sub-strategy signals
        # We MUST ensure the mock returns a REAL AITradeDecision with real strings
        def mock_load(variant):
            m = MagicMock()
            if variant == "supply_demand":
                # We mock the method itself to return a real object
                m.check_entry_signal.return_value = AITradeDecision(
                    action="enter_long", bias="long", score=75, symbol="BTCUSD", timeframe="5m",
                    phase="trend", structure_summary="Valid SND", invalidation_conditions="None", management_instructions="None", notes="SND Signal"
                )
            elif variant == "robocop":
                m.check_entry_signal.return_value = AITradeDecision(
                    action="enter_long", bias="long", score=90, symbol="BTCUSD", timeframe="5m",
                    phase="trend", structure_summary="Valid ROBO", invalidation_conditions="None", management_instructions="None", notes="ROBO Signal"
                )
            else:
                m.check_entry_signal.return_value = None
            m.name = variant
            return m
        
        # Apply the mock to the engine instance
        self.engine._load_specific_variant = mock_load
        
        # Execution
        # We call decide with explicit strings to avoid any positional mock injection
        decision = self.engine.decide(timeframe="5m", snapshot=snapshot, open_position=None)
        
        print(f"Final Decision Action: {decision.action}")
        print(f"Final Decision Notes: {decision.notes}")
        
        # Assertions
        self.assertEqual(decision.action, "enter_long")
        self.assertEqual(decision.score, 90)
        self.assertIn("ROBOCOP", decision.notes)

if __name__ == "__main__":
    unittest.main()
