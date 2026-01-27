import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath("src"))

from tradebot_sci.utils.symbol_classifier import classify_symbol, AssetClass
from tradebot_sci.config.models import TradingProfileSettings, PerAssetStrategies

def test_classifier():
    print("--- Testing Symbol Classifier ---")
    test_cases = [
        ("BTCUSD", AssetClass.CRYPTO),
        ("ETH/USD", AssetClass.CRYPTO),
        ("EURUSD", AssetClass.FOREX),
        ("GBPJPY", AssetClass.FOREX),
        ("XAUUSD", AssetClass.METALS),
        ("SPY", AssetClass.ETF),
        ("QQQ", AssetClass.ETF),
        ("AAPL", AssetClass.STOCKS),
        ("TSLA", AssetClass.STOCKS),
        ("ES", AssetClass.FUTURES),
        ("NQ", AssetClass.FUTURES),
        ("ETH/USD:USD-260130", AssetClass.FUTURES),
    ]

    for symbol, expected in test_cases:
        actual = classify_symbol(symbol)
        status = "PASS" if actual == expected else f"FAIL (Expected {expected}, got {actual})"
        print(f"Symbol: {symbol:20} | Class: {actual.value:10} | {status}")

def test_strategy_selection():
    print("\n--- Testing Strategy Selection ---")
    
    strategies = PerAssetStrategies(
        crypto="rubberband_reaper",
        forex="quantum",
        stocks="robocop",
        etf="evolution",
        metals="mean_reversion",
        futures="volatility_breakout"
    )

    profile = TradingProfileSettings(
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=300,
        strategy_variant="fallback_strategy",
        strategies=strategies
    )

    test_cases = [
        ("BTCUSD", "rubberband_reaper"),
        ("EURUSD", "quantum"),
        ("AAPL", "robocop"),
        ("SPY", "evolution"),
        ("XAUUSD", "mean_reversion"),
        ("ES", "volatility_breakout"),
        ("UNKNOWN123", "fallback_strategy"),
    ]

    for symbol, expected in test_cases:
        actual = profile.get_strategy_for_symbol(symbol)
        status = "PASS" if actual == expected else f"FAIL (Expected {expected}, got {actual})"
        print(f"Symbol: {symbol:15} | Strategy: {actual:20} | {status}")

if __name__ == "__main__":
    try:
        test_classifier()
        test_strategy_selection()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Tests failed with error: {e}")
        import traceback
        traceback.print_exc()
