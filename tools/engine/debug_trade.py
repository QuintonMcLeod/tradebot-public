import sys
from pathlib import Path
_repo = Path(__file__).resolve().parents[2]
_src = _repo / "src"
sys.path.insert(0, str(_src))

from tradebot_sci.simulation.backtester import SimulatedTrade
import inspect

print(f"SimulatedTrade fields: {SimulatedTrade.__dataclass_fields__.keys()}")
sig = inspect.signature(SimulatedTrade)
print(f"SimulatedTrade signature: {sig}")

try:
    t = SimulatedTrade(
        symbol="GBPUSD",
        direction="long",
        entry_price=1.2,
        exit_price=1.3,
        size=1000,
        entry_time=None,
        exit_time=None,
        pnl=100,
        exit_reason="test"
    )
    print("Successfully instantiated SimulatedTrade")
except Exception as e:
    print(f"Failed to instantiate: {e}")
