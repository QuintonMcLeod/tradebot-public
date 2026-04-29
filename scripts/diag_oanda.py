import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from tradebot_sci.config.loader import load_settings
from tradebot_sci.runtime.provider_factory import build_market_provider

settings = load_settings()
provider = build_market_provider(settings, shared_ib=None)

print(f"Provider: {provider}")
candles = provider.get_latest_candles("EURUSD", "1h", 100)
print(f"Got {len(candles)} candles for EURUSD 1h")
if candles:
    print(f"Last candle: {candles[-1]}")

from tradebot_sci.strategy.engine import StrategyEngine
engine = StrategyEngine(
    ai_client=None,
    market_provider=provider,
    profile=settings.profiles.get("forex_continuous"),
    symbol="EURUSD",
    settings=settings
)

from tradebot_sci.strategy.variants.forex_conductor import ForexConductorStrategy
engine._strategy = ForexConductorStrategy(profile_settings=settings.profiles.get("forex_continuous"))

# Run decide
print("Running decide()...")
snapshot = provider.get_latest_snapshot("EURUSD", "1m")
decision = engine.decide(timeframe="1h", open_position=None, snapshot=snapshot)
print(f"Engine Decision: {decision.action if decision else 'None'}")
print(f"Engine Last Grade: {engine.last_strat_grade}")
print(f"Gates Score: {engine.last_gates.get('score')}")
print(f"Gates Grade: {engine.last_gates.get('grade')}")
print(f"Market Regime: {engine.last_gates.get('market_regime')}")

