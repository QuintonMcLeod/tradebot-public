import pytest
from unittest.mock import MagicMock, patch
from helpers import make_test_profile
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.runtime.provider_factory import RoutedExchangeBroker

@patch.dict("os.environ", {"CCXT_EXCHANGE": "gemini", "CCXT_API_KEY": "test", "CCXT_API_SECRET": "test"})
@patch("tradebot_sci.broker.ccxt_broker.CCXTExchangeBroker._build_exchange")
def test_ccxt_broker_sync_profile(mock_build):
    # Setup mock exchange
    mock_exchange = MagicMock()
    mock_build.return_value = mock_exchange

    # 1. Setup Initial Profile
    initial_profile = make_test_profile(
        symbols=["BTCUSD"],
        balance_cap_pct=0.90,
        target_leverage=1.0,
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )

    broker = CCXTExchangeBroker(initial_profile)

    # 2. Assert Initial State
    assert broker.profile.balance_cap_pct == 0.90

    # 3. Create New Profile
    updated_profile = make_test_profile(
        symbols=["BTCUSD"],
        balance_cap_pct=0.75,
        target_leverage=2.0,
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )

    # 4. Sync Profile
    broker.sync_profile(updated_profile)

    # 5. Assert Updated State
    assert broker.profile.balance_cap_pct == 0.75
    assert broker.profile.target_leverage == 2.0

def test_routed_broker_propagation():
    # 1. Setup Profiles
    p1 = make_test_profile(
        symbols=["BTCUSD"],
        balance_cap_pct=0.90,
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )
    p2 = make_test_profile(
        symbols=["BTCUSD"],
        balance_cap_pct=0.50,
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )
    
    # 2. Setup Mock Brokers
    mock_b1 = MagicMock()
    mock_b2 = MagicMock()
    
    routed = RoutedExchangeBroker({
        "crypto": mock_b1,
        "forex": mock_b2
    })
    
    # 3. Trigger Propagated Sync
    routed.sync_profile(p2)
    
    # 4. Assert both brokers received the update
    mock_b1.sync_profile.assert_called_with(p2)
    mock_b2.sync_profile.assert_called_with(p2)

if __name__ == "__main__":
    pytest.main([__file__])
