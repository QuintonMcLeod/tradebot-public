import os
import unittest
from unittest.mock import patch, MagicMock
from helpers import make_test_profile
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker

class TestGeminiMapping(unittest.TestCase):
    @patch('tradebot_sci.broker.ccxt_broker.ccxt')
    @patch('tradebot_sci.broker.ccxt_broker.os.getenv')
    def test_gemini_symbol_map(self, mock_getenv, mock_ccxt):
        # Mock environment
        def getenv_side_effect(key, default=None):
            env = {
                'CCXT_EXCHANGE': 'gemini',
                'CCXT_API_KEY': 'fake',
                'CCXT_SECRET': 'fake',
            }
            return env.get(key, default)
        mock_getenv.side_effect = getenv_side_effect

        # Mock CCXT exchange
        mock_gemini_cls = MagicMock()
        mock_gemini_inst = MagicMock()
        mock_ccxt.gemini = mock_gemini_cls
        mock_gemini_cls.return_value = mock_gemini_inst

        profile = make_test_profile(
            name="test",
            candle_timeframe="5m",
            market_poll_interval_seconds=60,
            ai_decision_interval_seconds=300
        )
        broker = CCXTExchangeBroker(profile)
        
        # Verify Gemini specific mappings
        assert broker.symbol_map["GUSDUSD"] == "GUSD/USD"
        assert broker.symbol_map["PEPEUSD"] == "PEPE/USD"
        assert broker.symbol_map["HYPEUSD"] == "HYPE/USD"
        
        # Verify Coinbase derivatives are NOT in Gemini map
        assert "ETP-20DEC30-CDE" not in broker.symbol_map
        assert "BTC/USD:USD-260130" not in broker.symbol_map

    @patch('tradebot_sci.broker.ccxt_broker.ccxt')
    @patch('tradebot_sci.broker.ccxt_broker.os.getenv')
    def test_coinbase_symbol_map(self, mock_getenv, mock_ccxt):
        # Mock environment
        def getenv_side_effect(key, default=None):
            env = {
                'CCXT_EXCHANGE': 'coinbase',
            }
            return env.get(key, default)
        mock_getenv.side_effect = getenv_side_effect
        
        # Mock CCXT exchange
        mock_coinbase_cls = MagicMock()
        mock_coinbase_inst = MagicMock()
        mock_ccxt.coinbase = mock_coinbase_cls
        mock_coinbase_cls.return_value = mock_coinbase_inst

        profile = make_test_profile(
            name="test",
            candle_timeframe="5m",
            market_poll_interval_seconds=60,
            ai_decision_interval_seconds=300
        )
        broker = CCXTExchangeBroker(profile)
        
        # Verify Coinbase specific mappings
        assert broker.symbol_map["ETP-20DEC30-CDE"] == "ETP-20DEC30-CDE"
        assert broker.symbol_map["BTC/USD:USD-260130"] == "BTC/USD:USD-260130"
        
        # Verify Gemini specific mappings are NOT in Coinbase map
        assert "GUSDUSD" not in broker.symbol_map
        assert "HYPEUSD" not in broker.symbol_map

if __name__ == '__main__':
    unittest.main()
