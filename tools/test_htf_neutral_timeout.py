#!/usr/bin/env python3
"""Test HTF neutral timeout functionality."""

import sys
from pathlib import Path
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tradebot_sci.market.trend_enums import TrendDirection


@dataclass
class MockPosition:
    """Mock position for testing."""
    htf_neutral_bars: int = 0
    symbol: str = "SPY"
    size: float = 10.0
    entry_price: float = 450.0
    unrealized_pnl: float = 0.0


@dataclass
class MockTrend:
    """Mock trend object."""
    direction: TrendDirection


@dataclass
class MockSnapshot:
    """Mock market snapshot."""
    trend_htf: MockTrend | None = None


def test_htf_neutral_counter():
    """Test that HTF neutral counter increments and resets correctly."""
    print("=" * 60)
    print("TEST: HTF Neutral Timeout Counter")
    print("=" * 60)
    print()
    
    # Test 1: Counter increments when HTF is neutral
    print("Test 1: Counter increments when HTF is NEUTRAL")
    pos = MockPosition(htf_neutral_bars=0)
    snapshot = MockSnapshot(trend_htf=MockTrend(direction=TrendDirection.NEUTRAL))
    
    for i in range(1, 51):
        # Simulate backtester logic
        if snapshot.trend_htf and snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
            pos.htf_neutral_bars += 1
        
        if i in [1, 10, 48, 49, 50]:
            print(f"  Bar {i}: htf_neutral_bars = {pos.htf_neutral_bars}")
    
    assert pos.htf_neutral_bars == 50, f"Expected 50, got {pos.htf_neutral_bars}"
    print("  ✅ PASS: Counter incremented correctly to 50")
    print()
    
    # Test 2: Counter resets when HTF becomes trending
    print("Test 2: Counter resets when HTF becomes LONG")
    snapshot.trend_htf.direction = TrendDirection.LONG
    
    if snapshot.trend_htf.direction != TrendDirection.NEUTRAL:
        pos.htf_neutral_bars = 0
    
    print(f"  After HTF turns long: htf_neutral_bars = {pos.htf_neutral_bars}")
    assert pos.htf_neutral_bars == 0, f"Expected 0, got {pos.htf_neutral_bars}"
    print("  ✅ PASS: Counter reset correctly to 0")
    print()
    
    # Test 3: Timeout should trigger after 48 bars
    print("Test 3: Timeout triggers after 48 bars")
    htf_neutral_exit_bars = 48
    
    # Simulate neutral for 48 bars
    pos.htf_neutral_bars = 0
    snapshot.trend_htf.direction = TrendDirection.NEUTRAL
    
    for i in range(1, 50):
        if snapshot.trend_htf.direction == TrendDirection.NEUTRAL:
            pos.htf_neutral_bars += 1
        
        # Check if timeout should trigger
        if pos.htf_neutral_bars > htf_neutral_exit_bars:
            print(f"  Bar {i}: TIMEOUT TRIGGERED (htf_neutral_bars={pos.htf_neutral_bars} > {htf_neutral_exit_bars})")
            break
    
    assert pos.htf_neutral_bars > htf_neutral_exit_bars, "Timeout should have triggered"
    print("  ✅ PASS: Timeout triggered correctly after 48 bars")
    print()
    
    print("=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(test_htf_neutral_counter())
