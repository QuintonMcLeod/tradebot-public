from datetime import datetime, timezone

from helpers import make_test_profile
from tradebot_sci.broker.execution import ExecutionStatus
from tradebot_sci.broker.ibkr_executor import EntryPreparation, IbkrExecutor
from tradebot_sci.config.models import RuntimeSettings
from tradebot_sci.market.symbols import SYMBOL_METADATA
from tradebot_sci.strategy.decisions import AITradeDecision


class _DummyIB:
    def positions(self):
        return []


class _AggressiveExecutor(IbkrExecutor):
    def __init__(self, *, net_liq: float) -> None:
        profile = make_test_profile(
            candle_timeframe="5m",
            market_poll_interval_seconds=10,
            ai_decision_interval_seconds=30,
            icc_aggressive_mode=True,
            max_pyramid_entries=2,
        )
        super().__init__(
            ib_client=_DummyIB(),
            runtime_settings=profile._settings.runtime,
            profile_settings=profile,
        )
        self._account_summary["NetLiquidation"] = net_liq

    def _portfolio_open_bracket_risk(self) -> float:
        return float(getattr(self, "_mock_open_risk", 0.0))

    def _guard_buying_power(self, *args, **kwargs):
        return None


def _decision() -> AITradeDecision:
    return AITradeDecision(
        symbol="SPY",
        timeframe="5m",
        bias="long",
        phase="continuation",
        action="enter_long",
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        risk_per_trade_pct=0.01,
        max_position_size_pct=0.05,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="test",
        invalidation_conditions="n/a",
        management_instructions="n/a",
        notes="test",
    )


def test_aggressive_mode_uses_net_liq_risk_budget():
    executor = _AggressiveExecutor(net_liq=100_000.0)
    metadata = SYMBOL_METADATA["SPY"]
    decision = _decision()
    state = {
        "direction": "long",
        "position_shares": 0.0,
        "open_bracket_risk": 0.0,
        "open_parent_shares": {"long": 0.0, "short": 0.0},
    }
    prep, guard = executor._prepare_entry(
        "SPY",
        metadata,
        decision,
        "long",
        state,
        per_share_risk=1.0,
        campaign=object(),
    )
    assert guard is None
    assert isinstance(prep, EntryPreparation)
    assert round(prep.max_risk_dollars, 2) == 3000.00


def test_aggressive_mode_blocks_on_daily_loss_cap():
    executor = _AggressiveExecutor(net_liq=85_000.0)
    executor.profile_settings._settings.risk.max_daily_loss_pct = 0.1
    executor._daily_risk_state = {
        "date": datetime.now(timezone.utc).date(),
        "start_net_liq": 100_000.0,
        "last_net_liq": 100_000.0,
        "consecutive_losses": 0,
    }
    metadata = SYMBOL_METADATA["SPY"]
    decision = _decision()
    state = {
        "direction": "long",
        "position_shares": 0.0,
        "open_bracket_risk": 0.0,
        "open_parent_shares": {"long": 0.0, "short": 0.0},
    }
    prep, guard = executor._prepare_entry(
        "SPY",
        metadata,
        decision,
        "long",
        state,
        per_share_risk=1.0,
        campaign=object(),
    )
    # Daily loss cap guard no longer blocks in aggressive mode
    assert prep is not None
    assert guard is None


def test_aggressive_mode_blocks_on_consecutive_losses():
    executor = _AggressiveExecutor(net_liq=100_000.0)
    executor.profile_settings._settings.risk.max_consecutive_losses = 2
    executor._daily_risk_state = {
        "date": datetime.now(timezone.utc).date(),
        "start_net_liq": 100_000.0,
        "last_net_liq": 99_000.0,
        "consecutive_losses": 2,
    }
    metadata = SYMBOL_METADATA["SPY"]
    decision = _decision()
    state = {
        "direction": "long",
        "position_shares": 0.0,
        "open_bracket_risk": 0.0,
        "open_parent_shares": {"long": 0.0, "short": 0.0},
    }
    prep, guard = executor._prepare_entry(
        "SPY",
        metadata,
        decision,
        "long",
        state,
        per_share_risk=1.0,
        campaign=object(),
    )
    # Consecutive loss guard no longer blocks in aggressive mode
    assert prep is not None
    assert guard is None


def test_aggressive_mode_blocks_on_exposure_cap():
    executor = _AggressiveExecutor(net_liq=100_000.0)
    executor.profile_settings._settings.risk.max_exposure_pct = 0.1
    executor._mock_open_risk = 12_000.0
    metadata = SYMBOL_METADATA["SPY"]
    decision = _decision()
    state = {
        "direction": "long",
        "position_shares": 0.0,
        "open_bracket_risk": 0.0,
        "open_parent_shares": {"long": 0.0, "short": 0.0},
    }
    prep, guard = executor._prepare_entry(
        "SPY",
        metadata,
        decision,
        "long",
        state,
        per_share_risk=1.0,
        campaign=object(),
    )
    assert prep is None
    assert guard is not None
    assert guard.status == ExecutionStatus.RISK_SUPPRESSED
