
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings, UserConfig

def get_config():
    """Return configuration dictionary."""
    
    # Define the Profile (Mirroring Production Rubberband Reaper defaults)
    profile = TradingProfileSettings(
        strategy_variant="rubberband_reaper",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.20,
        icc_auto_entry_enabled=True, 
        icc_auto_entry_require_sweep=False, 
        icc_auto_entry_min_htf_strength=0.0, 
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "USD/CHF"
        ],
        "start_date": datetime(2026, 1, 19, 13, 0, 0, tzinfo=timezone.utc), # 8AM EST
        "end_date": datetime(2026, 1, 19, 17, 0, 0, tzinfo=timezone.utc),   # 12PM EST
        "initial_capital": 1000.00,
        "data_dir_name": "forex_backtest",
        "force_market_open": True, 
        # Add buffer to ensure we have warmup data if provider logic assumes rigid start
        # Actually mega_backtester relies on what's on disk.
    }

def apply_overrides():
    """Apply any runtime patches."""
    print("[Cartridge] Running Last Monday Scan (08:00-12:00 EST)...")
