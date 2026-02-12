"""Recent 27-Day Forex Backtest: Jan 15 - Feb 10, 2026. Higher ICC threshold."""
from datetime import datetime, timezone

class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    start_date = datetime(2026, 1, 15, 22, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 10, 22, 0, 0, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        strategy_variant="meta_sci",
        candle_timeframe="15m",
        htf_timeframe="15m",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        risk_per_trade_pct=0.05,
        max_concurrent_positions=6,
        multi_position_enabled=True,
        max_pyramid_entries=4,
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=70.0  # Raised from 60 -> 70 to cut marginal trades
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 2000.0,
        "data_dir_name": "marathon_recent",
        "force_market_open": True,
    }
