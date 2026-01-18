
import os
import unittest
from unittest.mock import MagicMock, patch
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.config.models import TradingProfileSettings
from tradebot_sci.strategy.decisions import AITradeDecision

class TestCCXTUpgrade(unittest.TestCase):
    def setUp(self):
        self.profile = TradingProfileSettings(
            profile_name="test",
            description="test",
            allow_day_trades=True,
            initial_capital_usd=10000.0,
            risk_per_trade_pct=0.01,
            max_open_trades=5,
            min_hold_seconds=300,
            crypto_min_notional_usd=10.0,
            candle_timeframe="5m",
            market_poll_interval_seconds=1.0,
            ai_decision_interval_seconds=60,
        )
        os.environ["CCXT_EXCHANGE"] = "binance"
        os.environ["CCXT_API_KEY"] = "mock"
        os.environ["CCXT_SECRET"] = "mock"
    
    @patch("ccxt.binance")
    def test_capabilities_spot_vs_future(self, mock_cls):
        # Default (Spot)
        os.environ["CCXT_DEFAULT_TYPE"] = "spot"
        broker = CCXTExchangeBroker(self.profile)
        caps = broker.get_execution_capabilities("BTCUSD")
        self.assertFalse(caps["supports_short"])
        self.assertTrue(caps["long_only"])
        
        # Future
        os.environ["CCXT_DEFAULT_TYPE"] = "future"
        broker = CCXTExchangeBroker(self.profile)
        caps = broker.get_execution_capabilities("BTCUSD")
        self.assertTrue(caps["supports_short"])
        self.assertFalse(caps["long_only"])
        self.assertTrue(caps["supports_native_stops"])

    @patch("ccxt.binance")
    def test_enter_short_future(self, mock_cls):
        os.environ["CCXT_DEFAULT_TYPE"] = "future"
        mock_ex = mock_cls.return_value
        mock_ex.fetch_ticker.return_value = {"last": 50000.0, "bid": 49990.0, "ask": 50010.0}
        # Mock create_order to return an ID
        mock_ex.create_order.return_value = {"id": "12345"}
        
        broker = CCXTExchangeBroker(self.profile)
        broker._exchange = mock_ex # Ensure mock is used
        
        decision = AITradeDecision(
            symbol="BTCUSD",
            timeframe="5m",
            bias="short",
            phase="trend",
            action="enter_short",
            entry_price=50000.0,
            stop_loss=51000.0, # SL above entry for short
            take_profit=48000.0,
            structure_summary="test",
            invalidation_conditions="test",
            management_instructions="test",
            notes="test"
        )
        
        res, outcome = broker.execute_decision(decision)
        
        # Verify Entry
        # Arg 2 is 'market', Arg 3 is 'sell'
        mock_ex.create_order.assert_any_call("BTC/USDT", "market", "sell", 10.0/50000.0)
        
        # Verify Stop
        # Should be 'stop_market', 'buy'
        # Check calls. We expect 2 calls.
        self.assertEqual(mock_ex.create_order.call_count, 2)
        
        # Check Stop Order params
        # create_order(symbol, type, side, amount, price, params)
        # We need to inspect call args details
        calls = mock_ex.create_order.call_args_list
        stop_call = calls[1]
        args, kwargs = stop_call
        self.assertEqual(args[0], "BTC/USDT")
        self.assertEqual(args[1], "stop_market")
        self.assertEqual(args[2], "buy")
        # Params is 6th arg (index 5)
        params_arg = args[5] if len(args) > 5 else kwargs.get('params', {})
        self.assertEqual(str(params_arg.get('stopPrice')), "51000.0")
        self.assertTrue(params_arg.get('reduceOnly'))

    @patch("ccxt.binance")
    def test_position_tracking_future(self, mock_cls):
        os.environ["CCXT_DEFAULT_TYPE"] = "future"
        mock_ex = mock_cls.return_value
        mock_ex.has = {'fetchPositions': True}
        # Mock fetch_positions return
        # CCXT returns list of dicts.
        # Short position: size 0.1, side 'short'
        mock_ex.fetch_positions.return_value = [{
            "symbol": "BTC/USDT",
            "contracts": 0.1,
            "side": "short",
            "entryPrice": 50000.0
        }]
        
        broker = CCXTExchangeBroker(self.profile)
        broker._exchange = mock_ex
        
        pos = broker.get_open_position_snapshot("BTCUSD")
        self.assertIsNotNone(pos)
        self.assertEqual(pos["side"], "short")
        self.assertEqual(pos["size"], -0.1) # Signed size
        
if __name__ == '__main__':
    unittest.main()
