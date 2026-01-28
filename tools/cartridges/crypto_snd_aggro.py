
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """Supply/Demand AGGRO: Best win rate (47%) + aggressive compounding."""
    
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
        candle_timeframe="5m",
        htf_timeframe="1h",  # Proven 1H trend filter
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.25,  # 25% RISK - aggressive but not suicidal
        max_loss_per_trade_dollars=0.0,
        allow_loss_exit_after_hold=True,
        max_daily_trades=3,  # More opportunities
        max_daily_loss_pct=0.50,  # 50% daily loss limit
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
    print("[Cartridge] Supply/Demand AGGRO MODE - 47% WR + 25% Risk")
