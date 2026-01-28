from datetime import datetime, timezone, timedelta
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """Return configuration dictionary for 30-day Marathon."""
    
    # Range: Dec 27, 2025 -> Jan 27, 2026
    start_date = datetime(2025, 12, 27, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 27, 23, 59, 59, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        strategy_variant="robocop",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.02, # 2% Initial Probe
        max_loss_per_trade_dollars=0.0, # Uncapped
        allow_loss_exit_after_hold=True,
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 500.00,
        "data_dir_name": "crypto_marathon", 
        "force_market_open": True, 
    }

def apply_overrides():
    """Apply runtime patches."""
    print("[Cartridge] Running Crypto RoboCop 30-Day MARATHON (Iteration 17)...")
