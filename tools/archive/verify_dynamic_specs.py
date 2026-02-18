
import os
import ccxt
from tradebot_sci.broker.ccxt_broker import CCXTExchangeBroker
from tradebot_sci.market.providers import CCXTMarketDataProvider
from tradebot_sci.config.models import TradingProfileSettings

def test_dynamic_detection():
    # Setup - mock settings
    profile = TradingProfileSettings(
        name="coinbase_futures", 
        symbols=["BTCUSD"],
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300
    )
    
    # Initialize Broker (this will call load_markets)
    os.environ["CCXT_EXCHANGE"] = "coinbase"
    broker = CCXTExchangeBroker(profile, default_type="future")
    
    # Initialize Provider
    provider = CCXTMarketDataProvider(broker.exchange, broker.symbol_map_data)
    
    # Test a known futures symbol (Nano BTC)
    # The internal symbol might be BIP-20DEC30-CDE or just something from markets
    # Let's find a real one from broker.exchange.markets
    futures_syms = [s for s in broker.exchange.markets if broker.exchange.markets[s].get('future')]
    if not futures_syms:
        print("No futures symbols found in load_markets!")
        return
        
    test_sym = futures_syms[0]
    print(f"Testing dynamic lookup for: {test_sym}")
    
    mdef = provider.get_market_definition(test_sym)
    if mdef:
        multiplier = mdef.get('contractSize')
        print(f"Detected Multiplier for {test_sym}: {multiplier}")
        # Validate it's not None
        assert multiplier is not None
    else:
        print(f"Failed to get market definition for {test_sym}")

if __name__ == "__main__":
    test_dynamic_detection()
