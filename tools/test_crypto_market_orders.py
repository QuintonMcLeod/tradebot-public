import sys
import os
from types import SimpleNamespace
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from tradebot_sci.broker.ibkr_executor import IbkrExecutor
from tradebot_sci.config.models import RuntimeSettings, TradingProfileSettings
from tradebot_sci.market.symbols import AssetClass
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.market.symbols import SYMBOL_METADATA, SymbolMetadata

# Mock IB Client
class _MockIB:
    def __init__(self):
        self.client = SimpleNamespace(getReqId=lambda: 1000)
        self.placed_orders = []

    def placeOrder(self, contract, order):
        self.placed_orders.append((contract, order))
        return order


def test_place_crypto_market_order():
    """Verify that setting crypto_order_type='MARKET' sends a MarketOrder."""
    print("Running test_place_crypto_market_order...")
    
    # Setup Executor with MARKET setting
    profile = TradingProfileSettings(
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        crypto_order_type="MARKET", # <--- Key setting
        crypto_fractional_enabled=True,
    )
    
    mock_ib = _MockIB()
    executor = IbkrExecutor(
        ib_client=mock_ib,
        runtime_settings=RuntimeSettings(),
        profile_settings=profile,
        allowed_symbols=["BTCUSD"]
    )

    # Mock contract resolution to ZEROHASH
    original_contract_for_symbol = executor._contract_for_symbol
    def mock_contract(symbol):
        c = SimpleNamespace()
        c.symbol = "BTC"
        c.currency = "USD"
        c.exchange = "ZEROHASH"
        return c
    executor._contract_for_symbol = mock_contract

    # Create Decision
    decision = AITradeDecision(
        symbol="BTCUSD",
        action="enter_long",
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=51000.0,
        risk_per_trade_pct=0.01,
        timestamp=datetime.now(timezone.utc),
        structure_summary="test",
        invalidation_conditions="test",
        management_instructions="test",
        notes="test"
    )

    # Force metadata to be CRYPTO
    SYMBOL_METADATA["BTCUSD"] = SymbolMetadata(
        symbol="BTCUSD",
        contract_symbol="BTC",
        currency="USD",
        asset_class=AssetClass.CRYPTO,
        exchange="ZEROHASH",
        min_tick=0.01
    )

    # Execute
    executor.get_net_liquidation = lambda: 10000.0
    executor._fetch_symbol_state = lambda s: {
        "position_shares": 0, "open_bracket_risk": 0.0, 
        "direction": None, "open_parent_shares": {}, 
        "working_orders": 0, "working_order_statuses": []
    }

    executor._place_entry_bracket(
        symbol="BTCUSD",
        direction="long",
        quantity=0.01,
        entry_price=50000.0,
        take_profit=51000.0,
        stop_loss=49000.0,
        metadata=SYMBOL_METADATA["BTCUSD"]
    )

    # Verify
    if len(mock_ib.placed_orders) != 1:
        print("FAIL: Expected 1 order, got", len(mock_ib.placed_orders))
        return False
    contract, order = mock_ib.placed_orders[0]
    
    if order.orderType != "MKT":
        print(f"FAIL: Expected 'MKT', got '{order.orderType}'")
        return False
    if order.action != "BUY":
        print("FAIL: Expected BUY")
        return False
    if order.totalQuantity != 0.01:
        print("FAIL: Expected 0.01 qty")
        return False
    if getattr(order, 'transmit', False) is not True:
        print("FAIL: Expected transmit=True")
        return False
    
    print("PASS: Market Order Placed Successfully")
    return True

def test_place_crypto_limit_order_default():
    """Verify default remains LIMIT order."""
    print("Running test_place_crypto_limit_order_default...")
    
    # Setup Executor with DEFAULT setting (LIMIT)
    profile = TradingProfileSettings(
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        # Default crypto_order_type is LIMIT
    )
    
    mock_ib = _MockIB()
    executor = IbkrExecutor(
        ib_client=mock_ib,
        runtime_settings=RuntimeSettings(),
        profile_settings=profile,
        allowed_symbols=["BTCUSD"]
    )

    # Mock contract
    executor._contract_for_symbol = lambda s: SimpleNamespace(symbol="BTC", currency="USD", exchange="ZEROHASH")

    decision = AITradeDecision(
        symbol="BTCUSD",
        action="enter_long",
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=51000.0,
        risk_per_trade_pct=0.01,
        timestamp=datetime.now(timezone.utc),
        structure_summary="test",
        invalidation_conditions="test",
        management_instructions="test",
        notes="test"
    )
     # Force metadata to be CRYPTO
    SYMBOL_METADATA["BTCUSD"] = SymbolMetadata(
        symbol="BTCUSD",
        contract_symbol="BTC",
        currency="USD",
        asset_class=AssetClass.CRYPTO,
        exchange="ZEROHASH",
        min_tick=0.01
    )

    executor.get_net_liquidation = lambda: 10000.0
    executor._fetch_symbol_state = lambda s: {
        "position_shares": 0, "open_bracket_risk": 0.0, 
        "direction": None, "open_parent_shares": {}, 
        "working_orders": 0, "working_order_statuses": []
    }

    executor._place_entry_bracket(
        symbol="BTCUSD",
        direction="long",
        quantity=0.01,
        entry_price=50000.0,
        take_profit=51000.0,
        stop_loss=49000.0,
        metadata=SYMBOL_METADATA["BTCUSD"]
    )

    if len(mock_ib.placed_orders) != 1:
        print("FAIL: Expected 1 order")
        return False
    contract, order = mock_ib.placed_orders[0]
    
    if order.orderType != "LMT":
        print(f"FAIL: Expected 'LMT', got '{order.orderType}'")
        return False
        
    print("PASS: Default Limit Order Verified")
    return True

if __name__ == "__main__":
    p1 = test_place_crypto_market_order()
    p2 = test_place_crypto_limit_order_default()
    if p1 and p2:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("TESTS FAILED")
        sys.exit(1)
