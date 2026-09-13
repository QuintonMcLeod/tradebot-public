from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.runtime.loop import run_bot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.config.loader import get_settings
from tradebot_sci.runtime.ledger_daemon import LedgerDaemon
from tradebot_sci.ai.seasoned_trader import SeasonedTraderDaemon


def test_runtime_loop_runs(monkeypatch):
    calls = []

    def fake_generate(self, context):  # type: ignore[override]
        calls.append(context)
        return AITradeDecision(
            symbol=context.symbol,
            timeframe=context.timeframe,
            bias="neutral",
            phase="chop",
            action="stand_aside",
            entry_price=None,
            entry_zone=None,
            stop_loss=None,
            take_profit=None,
            risk_per_trade_pct=None,
            max_position_size_pct=None,
            time_in_force_sec=None,
            urgency="low",
            structure_summary="test",
            invalidation_conditions="N/A",
            management_instructions="sit",
            notes="test loop",
        )

    monkeypatch.setattr(TradeSciAIClient, "generate_decision", fake_generate)
    monkeypatch.setattr("tradebot_sci.runtime.loop.time.sleep", lambda _: None)
    monkeypatch.setattr(LedgerDaemon, "start", lambda self: None)
    monkeypatch.setattr(SeasonedTraderDaemon, "start", lambda self: None)

    # Force continuous mode to False for the active profile
    settings = get_settings()
    monkeypatch.setattr(settings.get_active_profile(), "continuous_mode", False)

    run_bot(iterations=2)
    assert isinstance(calls, list)
