
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """Return configuration dictionary."""
    
    # Define the Profile
    profile = TradingProfileSettings(
        strategy_variant="robocop",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.015, # Aggressive RoboCop Risk
        max_loss_per_trade_dollars=0.0, # Uncapped
        allow_loss_exit_after_hold=True,
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        # Past 3 Days: Jan 24 to Jan 27 (Current Date)
        "start_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 27, 18, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 500.00, # Realistic crypto starting balance
        "data_dir_name": "crypto_backtest", # Assuming data exists or will be fetched
        "force_market_open": True, 
    }

def apply_overrides():
    """Apply any runtime patches."""
    print("[Cartridge] Running Crypto RoboCop 3-Day Sprint (Jan 24-27)...")
