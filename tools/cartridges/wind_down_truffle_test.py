
from datetime import datetime, timezone

from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """
    Wind Down Truffle test — covers ~6 weeks of Fridays.
    Uses Forex Conductor which now includes Wind Down Truffle
    as an always-on candidate (self-gates to Friday PM).
    """
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="15m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        htf_timeframe="1h",
        ltf_timeframe="15m",
        trend_window=30,
        trend_min_swings=2,
        trend_strength_floor=0.05,
        risk_per_trade_pct=0.045,
        icc_auto_entry_enabled=True,
        icc_auto_entry_require_sweep=False,
        icc_auto_entry_min_htf_strength=0.0,
        session_gate_enabled=False,
        structure_score_threshold=0.0,
        htf_neutral_exit_bars=0,
        stop_and_reverse_enabled=True,  # SAR for spike recovery
    )

    return {
        "profile_settings": profile,
        "symbols": ["EUR/USD", "GBP/USD"],
        # ~6 weeks of data = ~6 Fridays to test
        "start_date": datetime(2026, 1, 12, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 7500.00,
        "data_dir_name": "forex_backtest",
        "force_market_open": True,
    }

def apply_overrides():
    """No overrides needed — Conductor handles routing."""
    print("[Cartridge] Wind Down Truffle — Friday test cartridge loaded")
