
from datetime import datetime, timezone
from tradebot_sci.config.models import TradingProfileSettings, UserConfig

def get_config():
    """Return configuration dictionary."""
    
    # Define the Profile
    profile = TradingProfileSettings(
        strategy_variant="rubberband_reaper",
        candle_timeframe="5m",               # 5m High Res
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        htf_timeframe="5m",                  # [FIX] 5m HTF to match Direct Script sensitivity
        ltf_timeframe="5m",
        trend_window=30,
        trend_min_swings=2,                  # [FIX] Relax to 2 (was 3) to match "Direct Script" volume
        trend_strength_floor=0.05,           # [FIX] Lower floor (was 0.1)
        risk_per_trade_pct=0.20,             # Aggressive 20%
        # [FIX] UNLOCK AUTO-ENTRIES (Matches Direct Script Logic)
        icc_auto_entry_enabled=True,         # CRITICAL: Allow robot to enter without AI veto
        icc_auto_entry_require_sweep=False,  # Allow pure continuation
        icc_auto_entry_min_htf_strength=0.0, # Ignore HTF strength gate
        session_gate_enabled=False,          # Disable volume/time gating
        structure_score_threshold=0.0,       # Disable score gate (No Robocop needed)
        htf_neutral_exit_bars=0,
        max_pyramid_entries=3
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"], # Core 4 Majors
        "start_date": datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc), # Start Mon Jan 19 for Warmup
        "end_date": datetime(2026, 1, 24, 0, 0, 0, tzinfo=timezone.utc),
        "wind_down_days": 7,                  # [NEW] Allow 1 week for positions to close naturally
        "initial_capital": 25.00,
        "data_dir_name": "forex_backtest",
        "force_market_open": True, # Ensure we can trade if data has UTC offsets
    }

def apply_overrides():
    """Apply any runtime patches or global config changes."""
    print("[Cartridge] Enabling Friday Fade Logic...")
    UserConfig.FRIDAY_FADE_ENABLED = True
