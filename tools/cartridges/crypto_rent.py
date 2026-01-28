
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings

def get_config():
    """Supply/Demand AGGRO: 5-day to Feb 2nd with Recovery Martingale."""
    
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
        candle_timeframe="5m",
        htf_timeframe="1h",  # Proven 1H trend filter
        ltf_timeframe="5m",
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        risk_per_trade_pct=0.25,  # 25% base (Martingale will scale)
        max_loss_per_trade_dollars=0.0,
        allow_loss_exit_after_hold=True,
        max_daily_trades=10,  # More opportunities
        max_daily_loss_pct=0.80,  # 80% daily loss limit
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ZECUSD", "BCHUSD"
        ],
        # 5 days: Jan 24 to Jan 29 (simulating Jan 28 to Feb 2)
        "start_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "end_date": datetime(2026, 1, 29, 0, 0, 0, tzinfo=timezone.utc),
        "initial_capital": 200.00,
        "data_dir_name": "crypto_backtest",
        "force_market_open": True, 
    }

def apply_overrides():
    print("[Cartridge] 5-Day Sprint: $200 -> $6000 TARGET")
