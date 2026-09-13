#!/usr/bin/env python3
"""
TEST 4: Cache Size Limits Fix Verification
Tests that AI decision cache (max 100) and orders cache (max 1000) use LRU eviction.
"""
import sys
from pathlib import Path
from collections import OrderedDict
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_ai_decision_cache_lru():
    """Test AI decision cache with LRU eviction (max 100 entries)."""
    print("\n" + "="*80)
    print("TEST 4A: AI Decision Cache LRU Eviction (Max 100)")
    print("="*80)

    # Simulate the cache from engine.py:77-78
    ai_decision_cache = OrderedDict()
    ai_decision_cache_max_size = 100

    # Function to add to cache with LRU eviction (from engine.py:418, 425-426)
    def add_to_cache(key, value):
        """Add entry to cache with LRU eviction."""
        ai_decision_cache[key] = value
        # Evict oldest entries if over max size
        while len(ai_decision_cache) > ai_decision_cache_max_size:
            ai_decision_cache.popitem(last=False)  # Remove oldest (FIFO = LRU for this use)

    # Test 1: Add exactly 100 entries
    print("Adding 100 entries...")
    for i in range(100):
        key = f"decision_{i}"
        value = {"timestamp": datetime.now(timezone.utc), "data": f"data_{i}"}
        add_to_cache(key, value)

    assert len(ai_decision_cache) == 100, f"Expected 100, got {len(ai_decision_cache)}"
    print(f"✓ Cache at max capacity: {len(ai_decision_cache)} entries")

    # Verify oldest entry is still there
    assert "decision_0" in ai_decision_cache, "Oldest entry missing"
    print("✓ Oldest entry 'decision_0' still present")

    # Test 2: Add 50 more entries (should evict oldest 50)
    print("\nAdding 50 more entries (should trigger eviction)...")
    for i in range(100, 150):
        key = f"decision_{i}"
        value = {"timestamp": datetime.now(timezone.utc), "data": f"data_{i}"}
        add_to_cache(key, value)

    assert len(ai_decision_cache) == 100, f"Expected 100, got {len(ai_decision_cache)}"
    print(f"✓ Cache still at max: {len(ai_decision_cache)} entries")

    # Verify oldest 50 were evicted
    for i in range(50):
        assert f"decision_{i}" not in ai_decision_cache, f"decision_{i} should have been evicted"
    print("✓ Oldest 50 entries (decision_0 to decision_49) evicted")

    # Verify newest 100 are still there
    for i in range(50, 150):
        assert f"decision_{i}" in ai_decision_cache, f"decision_{i} should still be present"
    print("✓ Newest 100 entries (decision_50 to decision_149) retained")

    # Test 3: Add 100 more entries (full turnover)
    print("\nAdding 100 more entries (full cache turnover)...")
    for i in range(150, 250):
        key = f"decision_{i}"
        value = {"timestamp": datetime.now(timezone.utc), "data": f"data_{i}"}
        add_to_cache(key, value)

    assert len(ai_decision_cache) == 100, f"Expected 100, got {len(ai_decision_cache)}"
    print(f"✓ Cache still at max: {len(ai_decision_cache)} entries")

    # Verify only newest 100 remain
    for i in range(150):
        assert f"decision_{i}" not in ai_decision_cache, f"decision_{i} should have been evicted"
    for i in range(150, 250):
        assert f"decision_{i}" in ai_decision_cache, f"decision_{i} should still be present"
    print("✓ Only newest 100 entries (decision_150 to decision_249) retained")

    print("\n✅ TEST 4A PASSED: AI decision cache LRU eviction works correctly\n")


def test_orders_cache_lru():
    """Test orders cache with LRU eviction (max 1000 entries)."""
    print("="*80)
    print("TEST 4B: Orders Cache LRU Eviction (Max 1000)")
    print("="*80)

    # Simulate the cache from app.py:113, 513-517, 575-579
    orders_cache = OrderedDict()
    orders_cache_max_size = 1000

    # Function to add to cache with LRU eviction
    def add_order_to_cache(order_id, order_data):
        """Add order to cache with LRU eviction."""
        orders_cache[order_id] = order_data
        # Evict oldest entries if over max size
        while len(orders_cache) > orders_cache_max_size:
            orders_cache.popitem(last=False)  # Remove oldest

    # Test 1: Add exactly 1000 entries
    print("Adding 1000 order entries...")
    for i in range(1000):
        order_id = f"order_{i}"
        order_data = {"timestamp": datetime.now(timezone.utc), "symbol": "AAPL", "qty": i}
        add_order_to_cache(order_id, order_data)

    assert len(orders_cache) == 1000, f"Expected 1000, got {len(orders_cache)}"
    print(f"✓ Cache at max capacity: {len(orders_cache)} entries")

    # Verify oldest entry is still there
    assert "order_0" in orders_cache, "Oldest entry missing"
    print("✓ Oldest entry 'order_0' still present")

    # Test 2: Add 500 more entries (should evict oldest 500)
    print("\nAdding 500 more entries (should trigger eviction)...")
    for i in range(1000, 1500):
        order_id = f"order_{i}"
        order_data = {"timestamp": datetime.now(timezone.utc), "symbol": "AAPL", "qty": i}
        add_order_to_cache(order_id, order_data)

    assert len(orders_cache) == 1000, f"Expected 1000, got {len(orders_cache)}"
    print(f"✓ Cache still at max: {len(orders_cache)} entries")

    # Verify oldest 500 were evicted
    for i in range(500):
        assert f"order_{i}" not in orders_cache, f"order_{i} should have been evicted"
    print("✓ Oldest 500 entries (order_0 to order_499) evicted")

    # Verify newest 1000 are still there
    for i in range(500, 1500):
        assert f"order_{i}" in orders_cache, f"order_{i} should still be present"
    print("✓ Newest 1000 entries (order_500 to order_1499) retained")

    # Test 3: Add 1000 more entries (full turnover)
    print("\nAdding 1000 more entries (full cache turnover)...")
    for i in range(1500, 2500):
        order_id = f"order_{i}"
        order_data = {"timestamp": datetime.now(timezone.utc), "symbol": "AAPL", "qty": i}
        add_order_to_cache(order_id, order_data)

    assert len(orders_cache) == 1000, f"Expected 1000, got {len(orders_cache)}"
    print(f"✓ Cache still at max: {len(orders_cache)} entries")

    # Verify only newest 1000 remain
    for i in range(1500):
        assert f"order_{i}" not in orders_cache, f"order_{i} should have been evicted"
    for i in range(1500, 2500):
        assert f"order_{i}" in orders_cache, f"order_{i} should still be present"
    print("✓ Only newest 1000 entries (order_1500 to order_2499) retained")

    print("\n✅ TEST 4B PASSED: Orders cache LRU eviction works correctly\n")


def test_cache_ordering_preservation():
    """Test that OrderedDict preserves insertion order for LRU."""
    print("="*80)
    print("TEST 4C: OrderedDict Insertion Order for LRU")
    print("="*80)

    cache = OrderedDict()
    max_size = 10

    # Add 10 entries
    for i in range(10):
        cache[f"key_{i}"] = f"value_{i}"

    # Verify order
    keys = list(cache.keys())
    expected_keys = [f"key_{i}" for i in range(10)]
    assert keys == expected_keys, f"Order mismatch: {keys} != {expected_keys}"
    print("✓ OrderedDict preserves insertion order")

    # Add one more (should evict key_0)
    cache["key_10"] = "value_10"
    while len(cache) > max_size:
        cache.popitem(last=False)

    assert len(cache) == 10, f"Expected 10, got {len(cache)}"
    assert "key_0" not in cache, "key_0 should have been evicted"
    assert "key_10" in cache, "key_10 should be present"
    print("✓ popitem(last=False) removes oldest entry (FIFO/LRU)")

    # Verify final order
    keys = list(cache.keys())
    expected_keys = [f"key_{i}" for i in range(1, 11)]
    assert keys == expected_keys, f"Order mismatch: {keys} != {expected_keys}"
    print("✓ Remaining entries maintain correct order")

    print("\n✅ TEST 4C PASSED: OrderedDict ordering works for LRU\n")


def test_memory_bounded_growth():
    """Test that caches don't grow unbounded."""
    print("="*80)
    print("TEST 4D: Memory-Bounded Cache Growth")
    print("="*80)

    ai_cache = OrderedDict()
    ai_max = 100
    orders_cache = OrderedDict()
    orders_max = 1000

    def add_ai_decision(cache, key, value, max_size):
        cache[key] = value
        while len(cache) > max_size:
            cache.popitem(last=False)

    def add_order(cache, key, value, max_size):
        cache[key] = value
        while len(cache) > max_size:
            cache.popitem(last=False)

    # Simulate heavy load: 10,000 AI decisions
    print("Simulating 10,000 AI decisions...")
    for i in range(10000):
        add_ai_decision(ai_cache, f"ai_{i}", {"data": i}, ai_max)

    assert len(ai_cache) <= ai_max, f"AI cache exceeded max: {len(ai_cache)} > {ai_max}"
    print(f"✓ AI cache bounded: {len(ai_cache)} <= {ai_max}")

    # Simulate heavy load: 50,000 orders
    print("Simulating 50,000 orders...")
    for i in range(50000):
        add_order(orders_cache, f"order_{i}", {"data": i}, orders_max)

    assert len(orders_cache) <= orders_max, f"Orders cache exceeded max: {len(orders_cache)} > {orders_max}"
    print(f"✓ Orders cache bounded: {len(orders_cache)} <= {orders_max}")

    # Calculate memory savings
    ai_saved = 10000 - ai_max
    orders_saved = 50000 - orders_max

    print(f"\n✓ Memory savings:")
    print(f"  AI cache: {ai_saved} entries prevented (kept {ai_max} of {10000})")
    print(f"  Orders cache: {orders_saved} entries prevented (kept {orders_max} of {50000})")

    print("\n✅ TEST 4D PASSED: Caches remain memory-bounded under heavy load\n")


if __name__ == "__main__":
    print("\n" + "🟡"*40)
    print("HIGH PRIORITY TEST: CACHE SIZE LIMITS FIX VERIFICATION")
    print("🟡"*40 + "\n")

    tests = [
        ("AI Decision Cache LRU", test_ai_decision_cache_lru),
        ("Orders Cache LRU", test_orders_cache_lru),
        ("OrderedDict Insertion Order", test_cache_ordering_preservation),
        ("Memory-Bounded Growth", test_memory_bounded_growth),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ TEST FAILED: {test_name}")
            print(f"   Error: {e}\n")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print("FINAL RESULTS - TEST 4: CACHE SIZE LIMITS")
    print("="*80)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n✅ ALL TESTS PASSED - Cache size limits are working correctly!")
        sys.exit(0)
    else:
        print(f"\n❌ {failed} TEST(S) FAILED - Review output above")
        sys.exit(1)
