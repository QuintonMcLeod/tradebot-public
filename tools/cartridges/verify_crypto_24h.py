from datetime import datetime, timezone, timedelta

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # Target the window where we saw discrepancies
    end_date = datetime(2026, 1, 28, 18, 0, 0, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=1)
    
    # EXACT MIRROR OF 'crypto_247'
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
        candle_timeframe="5m",
        htf_timeframe="1h", 
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
        icc_entry_score_threshold=60.0,
        crypto_min_notional_usd=20.0,
        pair_selector_enabled=True,
        pair_selector_max_pairs=6
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 221.75, # Use your ACTUAL balance
        "data_dir_name": "crypto_marathon",
        "force_market_open": True
    }

def apply_overrides():
    print("[Cartridge] Running 100% SYNCED 'crypto_247' Backtest...")
