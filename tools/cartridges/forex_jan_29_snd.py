import os
import sys
from datetime import datetime, timezone

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    return {
        "profile_settings": TradingProfileSettings(
            strategy_variant="supply_demand",
            candle_timeframe="15m",
            htf_timeframe="1h", 
            ltf_timeframe="15m",
            trend_window=18,
            ltf_trend_window=12,
            trend_swing_lookback=3,
            trend_min_swings=2,
            trend_strength_floor=0.3,
            risk_per_trade_pct=0.05,
            max_concurrent_positions=4,
            multi_position_enabled=True,
            max_pyramid_entries=4,
            market_poll_interval_seconds=60,
            ai_decision_interval_seconds=300,
            auto_flatten_on_close=False,
            min_hold_hours=0.0,
            backtest_disable_stops=False,
            profit_exit_after_hold=False,
            allow_loss_exit_after_hold=False,
            max_hold_hours=0.0,
            htf_neutral_exit_bars=0,
            # Strategy specific internal params if needed
            icc_entry_score_threshold=60.0,
        ),
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "start_date": datetime(2026, 1, 23, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 29, 6, 0, tzinfo=timezone.utc),
        "initial_capital": 2000.0,
        "data_dir_name": "forex_backtest",
        "force_market_open": True
    }
