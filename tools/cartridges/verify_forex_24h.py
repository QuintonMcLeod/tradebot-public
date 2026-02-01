from datetime import datetime, timezone, timedelta

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # End date based on available data in forex_backtest
    end_date = datetime(2026, 1, 29, 7, 55, 0, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=1)
    
    # EXACT MIRROR OF 'forex_crypto_hybrid'
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
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
        "data_dir_name": "forex_backtest",
        "force_market_open": True
    }

def apply_overrides():
    print("[Cartridge] Running IDENTICAL 24H Forex Backtest (Synced with Live)...")
