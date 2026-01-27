
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    profile = TradingProfileSettings(
        strategy_variant="rubberband_reaper",
        candle_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        htf_timeframe="15m",
        ltf_timeframe="5m",
        trend_window=30,
        trend_min_swings=3,
        trend_strength_floor=0.1,
        risk_per_trade_pct=0.05,
        htf_neutral_exit_bars=0,
        max_pyramid_entries=1
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["UNI/USD"], 
        "start_date": datetime(2026, 1, 23, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 100.00,
        "data_dir_name": "forex_backtest",
        "force_market_open": True,
    }
