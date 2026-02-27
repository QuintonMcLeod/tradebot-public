"""
Conductor $7,500 Cartridge — Full Strategy
Based on RTFM/32_CONDUCTOR_STRATEGY.md specifications:
  - 95% guillotine at -0.3R (scale_out_fraction=0.95)
  - Stop-and-Reverse (4.5% risk, 1R TP, cost-aware)
  - Entry risk: 1%
  - Max pyramids: 50
  - Min hold: 5 min (0.08 hours)
  - No fixed TP (Conductor's dynamic ATR trail manages exits)
  - R-milestone management (30% initial / 4% subsequent, every 0.5R)
  - Momentum acceleration (0.3R displacement)
  - Pullback re-pyramiding (0.5R bounce)
  - Dynamic ATR trailing (1.5x/1.0x/0.7x)
"""
from datetime import datetime, timezone, timedelta

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # ~1 week of recent forex data from Kraken
    start_date = datetime(2026, 2, 19, 9, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 26, 20, 0, 0, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        # === STRATEGY ===
        strategy_variant="forex_conductor",
        
        # === TIMEFRAMES ===
        candle_timeframe="15m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        
        # === TREND DETECTION ===
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        
        # === ENTRY RISK (RTFM: 1%) ===
        risk_per_trade_pct=0.01,
        
        # === MULTI-POSITION ===
        max_concurrent_positions=6,
        multi_position_enabled=True,
        
        # === PYRAMIDING (RTFM: max 50, Conductor hardcodes 30%/4% per milestone) ===
        max_pyramid_entries=50,
        
        # === POLLING ===
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0,
        
        # === STOP-AND-REVERSE (RTFM: Uno Reverse Card) ===
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,              # 1R quick exit
        reversal_risk_per_trade=0.045,   # 4.5% of capital
        reversal_cost_aware_tp=True,     # Pad TP for spread
        
        # === HOLD GUARDS (RTFM: min hold 5 min) ===
        min_hold_hours=0.08,             # 5 minutes
        max_hold_hours=0,                # No max hold (dynamic trail handles exit)
        
        # === EXIT LOGIC ===
        htf_neutral_exit_bars=0,         # Disabled — Conductor manages exits
        
        # === SCALE OUT (RTFM: 95% guillotine) ===
        # Engine reads this from runtime settings, BUT we also set on
        # profile for any code paths that read it from profile
        scale_out_fraction=0.95,
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 7500.0,
        "data_dir_name": "marathon",
        "force_market_open": True,
        # Runtime settings (injected into Settings.runtime by mega_backtester)
        "runtime_settings": {
            "scale_out_fraction": 0.95,   # 95% guillotine
        },
    }

def apply_overrides():
    print("[Cartridge] Running FULL Conductor Strategy ($7,500 capital)")
    print("[Cartridge] Features: 95% guillotine, SAR 4.5%, 1R TP, ATR trail, max 50 pyramids")
