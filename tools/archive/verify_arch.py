
import os
import logging
from tradebot_sci.market.symbols import FUTURES_CONTRACT_SPECS
from tradebot_sci.config.models import Settings
from tradebot_sci.runtime.provider_factory import build_market_provider, build_exchange_broker

logging.basicConfig(level=logging.INFO)

def test_architecture():
    print("\n--- Testing Symbols ---")
    etp = FUTURES_CONTRACT_SPECS.get("ETP-20DEC30-CDE")
    print(f"ETP Multiplier: {etp['multiplier']} {etp['unit']}")
    assert etp['multiplier'] == 0.1
    
    bip = FUTURES_CONTRACT_SPECS.get("BIP-20DEC30-CDE")
    print(f"BIP Multiplier: {bip['multiplier']} {bip['unit']}")
    assert bip['multiplier'] == 0.01
    
    print("\n--- Testing Factory (Mock) ---")
    # Mock settings
    from tradebot_sci.config.loader import get_settings
    settings = get_settings()
    
    # Force mode in env
    os.environ["MARKET_DATA_MODE"] = "coinbase_futures"
    os.environ["BROKER_MODE"] = "coinbase_futures"
    os.environ["ALTERNATIVE_MARKET_DATA"] = "coinbase_futures"
    
    print(f"Selected Mode: {os.getenv('MARKET_DATA_MODE')}")
    
    from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
    from tradebot_sci.config.models import TradingProfileSettings
    profile = TradingProfileSettings(
        name="test", 
        symbols=["BTCUSD", "ETHUSD"],
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )
    
    # Mock CCXTExchangeBroker to avoid real exchange init
    import unittest.mock as mock
    with mock.patch('tradebot_sci.broker.ccxt_broker.CCXTExchangeBroker._build_exchange'):
        broker = CCXTExchangeBroker(profile, default_type="future")
        print(f"Broker default_type: {broker.default_type}")
        assert broker.default_type == "future"
        
        # Test list_open_position_symbols logic
        broker._exchange = mock.Mock()
        broker._exchange.has = {'fetchPositions': True}
        broker._exchange.fetch_positions.return_value = []
        
        with mock.patch.dict('os.environ', {'CCXT_DEFAULT_TYPE': 'spot'}):
            syms = broker.list_open_position_symbols()
            print(f"Positions in future mode (even if env says spot): {syms}")
            # Should call fetch_positions because instance default_type="future" overrides env
            broker._exchange.fetch_positions.assert_called_once()
            assert syms == set()

    print("\n--- Factory Check ---")
    os.environ["BROKER_MODE"] = "coinbase_futures"
    os.environ["ALTERNATIVE_BROKER"] = "ccxt"
    # test build
    from tradebot_sci.config.loader import get_settings
    settings = get_settings()
    # Mocking build_exchange_broker's dependencies
    with mock.patch('tradebot_sci.runtime.provider_factory.CCXTExchangeBroker') as mock_ccxt:
        broker = build_exchange_broker(settings, profile, shared_ib=None, allowed_symbols=None)
        mock_ccxt.assert_called()
        # Verify it was called with default_type="future"
        call_args = mock_ccxt.call_args
        print(f"Factory passed default_type: {call_args.kwargs.get('default_type')}")
        assert call_args.kwargs.get('default_type') == "future"

if __name__ == "__main__":
    test_architecture()
