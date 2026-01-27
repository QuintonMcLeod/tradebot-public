import logging
from tradebot_sci.simulation.backtester import Backtester

# SRE Telemetry: Global tracker for consecutive losses per symbol
STREAK_TRACKER = {}

class TradingProfileSettings(dict):
    """
    A dictionary that supports dot notation. 
    Satisfies Pydantic validation while allowing attribute access for prints.
    """
    def __getattr__(self, item):
        return self.get(item)
    def __setattr__(self, key, value):
        self[key] = value

def get_config():
    """
    Defines simulation parameters using the DotDict helper.
    """
    return {
        "profile_settings": TradingProfileSettings(
            strategy_variant="rubberband_reaper",
            leverage_cap=200,
        ),
        "symbols": ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF"],
        "start_date": "2026-01-01",
        "end_date": "2026-01-20",
        "initial_capital": 1000.0,
        "data_dir_name": "forex_backtest",
        "force_market_open": True 
    }

def apply_overrides():
    """
    Monkey-patches the Core Engine to track streaks and apply the 
    Streak-Resistant Reaper logic.
    """
    print("[OVERRIDE] Initializing Streak-Resistant Circuit Breaker...")

    # 1. Patch the Backtester to track performance metadata
    # We target _handle_trade_exit to capture the result of every trade
    original_handle_exit = Backtester._handle_trade_exit 
    
    def patched_handle_exit(self, trade):
        # Run original logic (PnL calculation, logging)
        original_handle_exit(self, trade)
        
        symbol = trade.symbol
        if symbol not in STREAK_TRACKER:
            STREAK_TRACKER[symbol] = 0
            
        if trade.pnl < 0:
            STREAK_TRACKER[symbol] += 1
            # Real-time telemetry for the user
            print(f"  [STREAK WARNING] {symbol} consecutive losses: {STREAK_TRACKER[symbol]}")
        else:
            STREAK_TRACKER[symbol] = 0 # Reset on success

    Backtester._handle_trade_exit = patched_handle_exit

    # 2. Patch the Strategy Risk Logic
    try:
        from tradebot_sci.strategies.rubberband_reaper import RubberbandReaper
        
        def streak_resistant_risk(self, current_balance, initial_balance):
            """
            Asymmetric Risk Scaling: Throttles risk based on streak telemetry.
            """
            # Use getattr to safely handle symbol identification
            symbol = getattr(self, "current_symbol", "UNKNOWN")
            streak = STREAK_TRACKER.get(symbol, 0)
            
            # Base aggressive tiering
            if current_balance < 1000:
                base_risk = 0.20 
            elif current_balance < 5000:
                base_risk = 0.10
            else:
                base_risk = 0.02

            # Circuit Breaker Multipliers: 
            # 0 loss: 100% | 1 loss: 60% | 2 loss: 20% | 3+ loss: 5% (Survival)
            multipliers = {0: 1.0, 1: 0.60, 2: 0.20}
            risk_multiplier = multipliers.get(streak, 0.05)

            # Principal Floor Protection: Revert to 'Safe Winner' if below seed
            if current_balance < initial_balance:
                return min(base_risk * risk_multiplier, 0.05)

            return max(base_risk * risk_multiplier, 0.01)

        # Apply the hot-fix to the Strategy class
        RubberbandReaper._get_tiered_risk = streak_resistant_risk
        print("[OVERRIDE] Logic successfully injected into RubberbandReaper.")
        
    except ImportError as e:
        print(f"[CRITICAL] Could not override Strategy: {e}")
