
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """HyperScalper AGGRO: 3R targets with aggressive risk."""
    
    profile = TradingProfileSettings(
        strategy_variant="hyper_scalper",
        candle_timeframe="5m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.30,  # 30% RISK PER TRADE
        max_loss_per_trade_dollars=0.0,
        allow_loss_exit_after_hold=True,
        max_daily_trades=10,  # Many scalp opportunities
        max_daily_loss_pct=0.60,  # 60% daily loss limit
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        "start_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 27, 18, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 200.00,
        "data_dir_name": "crypto_backtest",
        "force_market_open": True, 
    }

def apply_overrides():
    print("[Cartridge] HyperScalper AGGRO MODE")
