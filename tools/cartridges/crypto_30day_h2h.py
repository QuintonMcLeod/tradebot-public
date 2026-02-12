"""30-Day Crypto Head-to-Head Cartridge: Meta-SCI vs Bearish Engulfing."""
from datetime import datetime, timezone

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # Full 32-day range matching the crypto_marathon data (Dec 27 - Jan 28)
    start_date = datetime(2025, 12, 27, 8, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 28, 8, 0, 0, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        strategy_variant="meta_sci",
        candle_timeframe="5m",
        htf_timeframe="1h",  # Will be resampled from 5m
        ltf_timeframe="5m",
        trend_window=18,
        ltf_trend_window=12,
        trend_swing_lookback=3,
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
        "symbols": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 500.0,
        "data_dir_name": "crypto_marathon",
        "force_market_open": True,
    }

def apply_overrides():
    print("[Cartridge] 30-Day Crypto Head-to-Head...")
