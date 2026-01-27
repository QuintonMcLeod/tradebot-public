
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings, UserConfig

def get_config():
    """Return configuration dictionary."""
    
    # Define the Profile
    profile = TradingProfileSettings(
        strategy_variant="rubberband_reaper",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.0025, # FAIL-SAFE DEFAULT (SCOUT)
        max_loss_per_trade_dollars=0.0, # Uncapped
        allow_loss_exit_after_hold=False,
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "USD/CHF"
        ],
        # Full Month: Jan 1 to Jan 26 (Current Date)
        "start_date": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 100.00,
        "data_dir_name": "forex_backtest",
        "force_market_open": True, 
    }

def apply_overrides():
    """Apply any runtime patches."""
    print("[Cartridge] Running $100 -> $1000 Marathon (Jan 1-26)...")
