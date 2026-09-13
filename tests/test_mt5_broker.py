import pytest
from unittest.mock import patch, MagicMock
from tradebot_sci.broker.mt5_zmq_broker import MT5ZMQBroker
from tradebot_sci.strategy.decisions import AITradeDecision

def test_mt5_broker_serialization():
    mock_profile = MagicMock()
    mock_profile.risk_per_trade_pct = 0.02
    
    with patch('zmq.Context') as mock_context:
        # Mock the underlying ZMQ socket explicitly
        mock_socket = MagicMock()
        mock_socket.recv.return_value = b'{"status": "success", "ticket": 999}'
        mock_context.return_value.socket.return_value = mock_socket
        
        broker = MT5ZMQBroker(mock_profile, req_port=5555)
        
        # Test basic execution
        decision = AITradeDecision(
            symbol="EURUSD",
            action="enter_long",
            stop_loss=1.0500,
            take_profit=1.0600,
            timeframe="5m",
            bias="long",
            phase="trend"
        )
        
        # The broker initializes with a refresh_account_summary which consumes the first recv()
        # Reset the mock to track execute_decision cleanly
        mock_socket.send.reset_mock()
        mock_socket.recv.return_value = b'{"status": "success", "ticket": 10293}'
        
        res, outcome = broker.execute_decision(decision)
        
        # Check that it serialized correctly
        assert mock_socket.send.called
        sent_args = mock_socket.send.call_args[0][0]
        import json
        payload = json.loads(sent_args.decode('utf-8'))
        
        assert payload["action"] == "EXECUTE"
        assert payload["symbol"] == "EURUSD"
        assert payload["type"] == "BUY"
        assert payload["sl"] == 1.0500
        assert payload["tp"] == 1.0600
        
        # Assert result parses correctly
        assert res.status.value == "executed"
        assert outcome.status.value == "success_submitted"
