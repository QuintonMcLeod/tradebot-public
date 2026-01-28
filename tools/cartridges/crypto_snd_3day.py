from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """Return configuration dictionary."""
    
    # Define the Profile
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
        candle_timeframe="5m",
        htf_timeframe="1h", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.015,
        max_loss_per_trade_dollars=0.0,
        allow_loss_exit_after_hold=True,
        max_daily_trades=1,
        max_daily_loss_pct=0.04,
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        "start_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 27, 18, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 500.00,
        "data_dir_name": "crypto_backtest",
        "force_market_open": True, 
    }

def apply_overrides():
    """Apply any runtime patches."""
    print("[Cartridge] Running Crypto Supply & Demand 3-Day Backtest...")
