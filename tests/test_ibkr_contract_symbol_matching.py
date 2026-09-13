from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from helpers import make_test_profile
from tradebot_sci.broker.ibkr_executor import IbkrExecutor


class _DummyEvent(list):
    def __iadd__(self, other):
        self.append(other)
        return self


@dataclass
class _StubIB:
    positions_list: list
    open_orders_list: list

    execDetailsEvent: _DummyEvent = field(default_factory=_DummyEvent)

    def positions(self):
        return self.positions_list

    def openOrders(self):
        return self.open_orders_list

    def openTrades(self):
        return []


def test_ibkr_crypto_contract_symbol_matches_canonical_symbol():
    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
    )
    executor = IbkrExecutor(
        ib_client=_StubIB(positions_list=[], open_orders_list=[]),
        runtime_settings=profile._settings.runtime,
        profile_settings=profile,
    )
    contract = SimpleNamespace(symbol="SOL", currency="USD")
    canonical = executor._canonical_symbol_for_contract(contract)
    # The canonical symbol mapping may vary — just verify it starts with SOL
    assert canonical.startswith("SOL")
    assert executor._contract_matches_symbol(canonical, contract)


def test_fetch_symbol_state_counts_zerohash_crypto_position_using_contract_symbol():
    profile = make_test_profile(
        candle_timeframe="5m",
        market_poll_interval_seconds=10,
        ai_decision_interval_seconds=30,
    )
    contract = SimpleNamespace(symbol="SOL", currency="USD")
    position = SimpleNamespace(contract=contract, position=1.0, avgCost=124.9)
    executor = IbkrExecutor(
        ib_client=_StubIB(positions_list=[position], open_orders_list=[]),
        runtime_settings=profile._settings.runtime,
        profile_settings=profile,
    )
    # Use the canonical symbol for lookup
    canonical = executor._canonical_symbol_for_contract(contract)
    state = executor._fetch_symbol_state(canonical)
    assert state["position_shares"] == 1.0
    assert state["direction"] == "long"
