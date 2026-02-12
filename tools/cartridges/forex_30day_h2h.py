"""30-Day Forex Head-to-Head Cartridge: Meta-SCI vs Bearish Engulfing."""
from datetime import datetime, timezone

class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # Full 29-day range (Jan 1 - Jan 29)
    start_date = datetime(2026, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 29, 22, 0, 0, tzinfo=timezone.utc)
    
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
        icc_entry_score_threshold=60.0
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 2000.0,
        "data_dir_name": "marathon_30d",
        "force_market_open": True,
    }

def apply_overrides():
    print("[Cartridge] 30-Day Forex Head-to-Head...")
