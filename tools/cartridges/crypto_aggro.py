
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """AGGRO MODE: Maximum risk for maximum returns. $200 -> $6000 target."""
    
    profile = TradingProfileSettings(
        strategy_variant="robocop",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.50,  # 50% RISK PER TRADE - AGGRESSIVE
        max_loss_per_trade_dollars=0.0,  # Uncapped
        allow_loss_exit_after_hold=True,
        max_daily_trades=5,  # Multiple trades per day
        max_daily_loss_pct=0.80,  # 80% daily loss limit (survive to fight another day)
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        "start_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 27, 18, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 200.00,  # User's actual capital
        "data_dir_name": "crypto_backtest",
        "force_market_open": True, 
    }

def apply_overrides():
    """Apply any runtime patches."""
    print("[Cartridge] AGGRO MODE: $200 -> $6000 TARGET")
