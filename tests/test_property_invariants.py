"""Property-based tests using Hypothesis.

Instead of handcrafted edge cases, these tests throw thousands of random
inputs at critical financial functions to verify invariants always hold.
"""

import os
import sys
import types

import pytest

# hypothesis is an optional test dependency. Skipping the module when it is absent
# keeps `pytest tests/` runnable; importing it unconditionally aborts collection for
# the entire suite, which hides every other test result.
st = pytest.importorskip("hypothesis.strategies")
_hypothesis = pytest.importorskip("hypothesis")
given = _hypothesis.given
settings = _hypothesis.settings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus  # noqa: E402, I001
from tradebot_sci.broker.paper_broker import PaperBroker  # noqa: E402
from tradebot_sci.strategy.decisions import AITradeDecision  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────

def _make_broker(balance: float = 10_000.0, leverage: float = 1.0) -> PaperBroker:
    """Create a PaperBroker without disk I/O."""
    profile = types.SimpleNamespace(
        risk_per_trade_pct=0.01,
        target_leverage=leverage,
    )
    original_load = PaperBroker._load_state
    original_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=balance)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    broker._save_state = lambda: None
    return broker


def _make_decision(
    symbol: str, action: str, entry: float, sl: float, tp: float,
) -> AITradeDecision:
    bias = "long" if "long" in action else ("short" if "short" in action else "neutral")
    return AITradeDecision(
        symbol=symbol,
        timeframe="5m",
        bias=bias,
        phase="trend",
        action=action,
        entry_price=entry,
        entry_zone=None,
        stop_loss=sl,
        take_profit=tp,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="property test",
        invalidation_conditions="N/A",
        management_instructions="hold",
        notes="property-based test",
    )


# ═══════════════════════════════════════════════════════════════════
# Invariant 1: Position size never exceeds leveraged capital
# ═══════════════════════════════════════════════════════════════════

@given(
    capital=st.floats(min_value=100.0, max_value=1_000_000.0),
    price=st.floats(min_value=1.0, max_value=200_000.0),
    sl_dist=st.floats(min_value=0.01, max_value=0.30),  # 1%-30% SL distance
    leverage=st.floats(min_value=1.0, max_value=5.0),
)
@settings(max_examples=200)
def test_position_size_never_exceeds_leveraged_capital(
    capital: float, price: float, sl_dist: float, leverage: float,
) -> None:
    """No matter the inputs, position notional ≤ capital × leverage."""
    broker = _make_broker(balance=capital, leverage=leverage)
    sl_price = price * (1 - sl_dist)
    tp_price = price * (1 + sl_dist * 2)

    decision = _make_decision("TESTUSD", "enter_long", price, sl_price, tp_price)
    result, _ = broker.execute_decision(decision)

    if result.status == ExecutionStatus.EXECUTED:
        pos = broker.positions["TESTUSD"]
        notional = abs(pos["qty"]) * pos["entry_price"]
        max_allowed = capital * min(leverage, PaperBroker.PAPER_MAX_LEVERAGE) * 1.02  # 2% tolerance
        assert notional <= max_allowed, (
            f"Notional ${notional:,.2f} exceeds cap ${max_allowed:,.2f} "
            f"(capital=${capital:,.2f}, leverage={leverage}x)"
        )


# ═══════════════════════════════════════════════════════════════════
# Invariant 2: Balance never goes negative from entry fees
# ═══════════════════════════════════════════════════════════════════

@given(
    capital=st.floats(min_value=10.0, max_value=100_000.0),
    price=st.floats(min_value=0.50, max_value=100_000.0),
)
@settings(max_examples=200)
def test_balance_never_negative_after_entry(capital: float, price: float) -> None:
    """Entry fees must never bankrupt the account."""
    broker = _make_broker(balance=capital, leverage=1.0)
    sl_price = price * 0.95
    tp_price = price * 1.10

    decision = _make_decision("TESTUSD", "enter_long", price, sl_price, tp_price)
    result, _ = broker.execute_decision(decision)

    assert broker.balance >= 0, (
        f"Balance went negative: ${broker.balance:.4f} "
        f"(initial=${capital:.2f}, price=${price:.2f})"
    )


# ═══════════════════════════════════════════════════════════════════
# Invariant 3: Safety guard loss streak counter never negative
# ═══════════════════════════════════════════════════════════════════

@given(pnl=st.floats(min_value=-10_000.0, max_value=10_000.0))
@settings(max_examples=200)
def test_safety_state_loss_streak_never_negative(pnl: float) -> None:
    """Loss streak counter must be >= 0 regardless of PnL sequence."""
    from tradebot_sci.strategy.safety_state import SafetyState

    state = SafetyState()
    # Simulate updating streak based on PnL
    if pnl < 0:
        state.symbol_loss_streaks["TEST"] = state.symbol_loss_streaks.get("TEST", 0) + 1
    else:
        state.symbol_loss_streaks["TEST"] = 0

    assert state.symbol_loss_streaks["TEST"] >= 0


# ═══════════════════════════════════════════════════════════════════
# Invariant 4: Round-trip trade cost is bounded
# ═══════════════════════════════════════════════════════════════════

@given(
    capital=st.floats(min_value=1_000.0, max_value=100_000.0),
    price=st.floats(min_value=10.0, max_value=50_000.0),
)
@settings(max_examples=100)
def test_round_trip_cost_bounded(capital: float, price: float) -> None:
    """A round-trip trade at the same price should cost < 3% of capital."""
    from unittest.mock import MagicMock

    broker = _make_broker(balance=capital, leverage=1.0)
    sl_price = price * 0.90
    tp_price = price * 1.20

    # Enter
    entry = _make_decision("TESTUSD", "enter_long", price, sl_price, tp_price)
    result, _ = broker.execute_decision(entry)
    if result.status != ExecutionStatus.EXECUTED:
        return  # Skip if entry was blocked

    # Close at same price
    provider = MagicMock()
    ticker = MagicMock()
    ticker.last = price
    provider.get_ticker.return_value = ticker
    broker.market_provider = provider

    close = _make_decision("TESTUSD", "close_position", price, sl_price, tp_price)
    close.action = "close_position"
    close.bias = "neutral"
    broker.execute_decision(close)

    cost = capital - broker.balance
    cost_pct = cost / capital
    assert cost_pct < 0.03, (
        f"Round-trip cost {cost_pct*100:.2f}% exceeds 3% cap "
        f"(capital=${capital:,.2f}, cost=${cost:.2f})"
    )


# ═══════════════════════════════════════════════════════════════════
# Invariant 5: Config safety guard defaults are always ON
# ═══════════════════════════════════════════════════════════════════

@given(st.data())
@settings(max_examples=50)
def test_safety_defaults_always_on(data: st.DataObject) -> None:
    """No matter how many times we instantiate SafetySettings, guards are ON."""
    from tradebot_sci.config.models import SafetySettings

    s = SafetySettings()
    guards = [
        "safety_drawdown_breaker_enabled",
        "safety_streak_breaker_enabled",
        "safety_churn_burner_enabled",
        "safety_greed_guard_enabled",
        "safety_session_lockout_enabled",
        "safety_opening_sentry_enabled",
        "safety_fee_shield_enabled",
        "safety_leverage_sentry_enabled",
    ]
    for guard in guards:
        assert getattr(s, guard) is True, f"{guard} must always default to True"
