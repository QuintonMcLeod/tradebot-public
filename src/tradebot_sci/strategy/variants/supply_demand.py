from __future__ import annotations
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel

from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision, stand_aside_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import (
    detect_indication,
    calculate_atr
)

logger = logging.getLogger(__name__)


class SNDZone(BaseModel):
    side: str  # "supply" or "demand"
    top: float
    bottom: float
    is_fresh: bool = True
    bos_index: int

# [SAFEGUARD] Global Persistence for Strategy Instances
GLOBAL_DAILY_COUNTS = {}

# [AGGRO MODE] $200 -> $6000 Target - RECOVERY MARTINGALE
FEET_WET_RISK = 0.25     # Start at 25% Risk
FEET_WET_MIN = 0.25      # Reset to 25% after WIN
FEET_WET_STEP = 0.25     # +25% per LOSS (aggressive recovery)
FEET_WET_MAX = 1.00      # Cap at 100%

def feet_wet_on_trade_closed(pnl: float):
    """RECOVERY MARTINGALE: Increase risk after loss to recover. Reset on win."""
    global FEET_WET_RISK
    if pnl > 0:
        # WIN: Reset to base (we recovered)
        FEET_WET_RISK = FEET_WET_MIN
    else:
        # LOSS: Increase risk to recover (capped at max)
        FEET_WET_RISK = min(FEET_WET_RISK + FEET_WET_STEP, FEET_WET_MAX)
    print(f"[MARTINGALE] PnL={pnl:.2f} -> Risk={FEET_WET_RISK*100:.0f}%")

class SupplyDemandStrategy(BaseStrategy):
    """
    Supply and Demand Strategy (Her Trading Methodology)
    
    4 Easy Steps:
    1. Find a Trend (Directional Bias)
    2. Wait for Break of Structure (BOS)
    3. Wait for Price to Come Back and Tap Your Zone
    4. Take an Entry (Candle Break)
    """
    
    def __init__(self):
        super().__init__("SupplyDemand")
        self.RISK_PCT = 0.01  # 1% Risk (Profitable)
        self.RR_TARGET = 2.0  # 2R Target - OPTIMAL
        self.ZONE_WINDOW = 100

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        # [SAFEGUARD] Over-Trading Protection
        # Check max_daily_trades from profile settings (in gates or kwargs usually, but let's be robust)
        # Note: Backtester injects profile settings into gates? Usually 'profile' key.
        # Use snapshot time for date
        if not snapshot.candles: return None
        
        current_date = snapshot.candles[-1].timestamp.strftime("%Y-%m-%d")
        
        # Get limit
        max_daily = 100 # Default high
        if "profile" in gates:
            max_daily = getattr(gates["profile"], "max_daily_trades", None) or 20
        else:
            max_daily = 20
        
        # KEY: Symbol + Date
        daily_key = f"{snapshot.symbol}_{current_date}"
        trades_today = GLOBAL_DAILY_COUNTS.get(daily_key, 0)

        # DEBUG PRINT
        # print(f"[DEBUG] {snapshot.symbol} {current_date} | Count: {trades_today} | Max: {max_daily}")
        
        if trades_today >= max_daily:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Daily Limit Reached ({trades_today}/{max_daily})")

        # Step 1: Find a Trend
        trend_dir = snapshot.trend_htf.direction
        if trend_dir not in {"long", "short"}:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: No clear trend (HTF)")

        # Step 2: Wait for Break of Structure (BOS)
        # We use 'detect_indication' which finds breaks of recent swing highs/lows
        bos = detect_indication(snapshot.candles, swing_lookback=2, window=self.ZONE_WINDOW)
        if not bos or bos.direction != trend_dir:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: No BOS in trend direction ({trend_dir})")

        # Step 3: Identify the Zone (The "Base" before the BOS)
        zone = self._find_base_zone(snapshot.candles, bos)
        if not zone:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Could not identify valid base zone (Imbalance Missing)")

        last_candle = snapshot.candles[-1]
        prev_candle = snapshot.candles[-2]
        
        # Step 4: Wait for Tap & Entry
        # A "Tap" means price touches the zone.
        is_tapping = False
        if zone.side == "demand":
            # Demand: Price dips into the zone
            is_tapping = last_candle.low <= zone.top and last_candle.close >= zone.bottom
            
            if is_tapping:
                # Execution: "Break the Candle" (Last candle high break)
                # Ensure the candle being broken was a down candle (part of the pullback) or neutral
                valid_setup = prev_candle.close <= prev_candle.open
                
                if valid_setup and last_candle.close > prev_candle.high:
                    atr = calculate_atr(snapshot.candles) or (last_candle.close * 0.001)
                    # STRICT SL: Zone Bottom only. Ignore entry candle wick.
                    stop_loss = zone.bottom - (atr * 0.2)
                    take_profit = last_candle.close + (abs(last_candle.close - stop_loss) * self.RR_TARGET)
                    
                    # [SAFEGUARD] Increment count (Global)
                    GLOBAL_DAILY_COUNTS[daily_key] = trades_today + 1
                    
                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="long", phase="trend", action="enter_long",
                        entry_price=last_candle.close, stop_loss=stop_loss, take_profit=take_profit,
                        risk_per_trade_pct=FEET_WET_RISK,
                        structure_summary=f"SND: Demand Zone Tap & Break (BOS at idx {zone.bos_index}) [FW:{FEET_WET_RISK*100:.0f}%]",
                        invalidation_conditions="Zone Break / Structure Invalidation",
                        management_instructions="SND Target or Trailing Stop",
                        urgency="medium",
                        notes=f"SND Zone: {zone.bottom:.4f}-{zone.top:.4f}"
                    )
                else:
                    return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Tapping Demand, waiting for candle break")
        
        else: # supply
            # Supply: Price rallies into the zone
            is_tapping = last_candle.high >= zone.bottom and last_candle.close <= zone.top
            
            if is_tapping:
                # Execution: "Break the Candle" (Last candle low break)
                valid_setup = prev_candle.close >= prev_candle.open

                if valid_setup and last_candle.close < prev_candle.low:
                    atr = calculate_atr(snapshot.candles) or (last_candle.close * 0.001)
                    # STRICT SL: Zone Top only. Ignore entry candle wick.
                    stop_loss = zone.top + (atr * 0.2)
                    take_profit = last_candle.close - (abs(last_candle.close - stop_loss) * self.RR_TARGET)
                    
                    # [SAFEGUARD] Increment count (Global)
                    GLOBAL_DAILY_COUNTS[daily_key] = trades_today + 1

                    return AITradeDecision(
                        symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                        bias="short", phase="trend", action="enter_short",
                        entry_price=last_candle.close, stop_loss=stop_loss, take_profit=take_profit,
                        risk_per_trade_pct=FEET_WET_RISK,
                        structure_summary=f"SND: Supply Zone Tap & Break (BOS at idx {zone.bos_index}) [FW:{FEET_WET_RISK*100:.0f}%]",
                        invalidation_conditions="Zone Break / Structure Invalidation",
                        management_instructions="SND Target or Trailing Stop",
                        urgency="medium",
                        notes=f"SND Zone: {zone.bottom:.4f}-{zone.top:.4f}"
                    )
                else:
                    return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Tapping Supply, waiting for candle break")

        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Waiting for retest of {zone.side} zone")

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        # Basic exit on target or structural change
        # (Standard Trailing or Invalidation can be added later)
        return None

    def _find_base_zone(self, candles: list[Candle], bos) -> Optional[SNDZone]:
        """
        Identifies the 'Base' candle(s) that preceded the BOS move.
        Requires an IMPULSE move away from the base (Imbalance).
        """
        bos_idx = bos.index
        atr = calculate_atr(candles) or 0.0
        
        if bos.direction == "long":
            # Bullish BOS: Find the last bearish candle before the rally
            for i in range(bos_idx - 1, max(0, bos_idx - 20), -1):
                c = candles[i]
                # Found the base?
                if c.close < c.open: 
                    # CHECK FOR IMBALANCE: Did the *next* candle explode away?
                    if (i + 1) < len(candles):
                        next_c = candles[i+1]
                        # Imbalance Check: Next candle is bullish AND (Large Body OR Gap)
                        is_bullish = next_c.close > next_c.open
                        body_size = abs(next_c.close - next_c.open)
                        is_large = body_size > (atr * 0.5) 
                        
                        if is_bullish and is_large:
                            return SNDZone(
                                side="demand",
                                top=float(c.high),
                                bottom=float(c.low),
                                bos_index=bos_idx
                            )
            return None # No proper base found
            
        else: # Bearish BOS
            # Bearish BOS: Find the last bullish candle before the drop
            for i in range(bos_idx - 1, max(0, bos_idx - 20), -1):
                c = candles[i]
                if c.close > c.open: 
                    # CHECK FOR IMBALANCE
                    if (i + 1) < len(candles):
                        next_c = candles[i+1]
                        # Imbalance Check: Next candle is bearish AND Large
                        is_bearish = next_c.close < next_c.open
                        body_size = abs(next_c.close - next_c.open)
                        is_large = body_size > (atr * 0.5)
                        
                        if is_bearish and is_large:
                            return SNDZone(
                                side="supply",
                                top=float(c.high),
                                bottom=float(c.low),
                                bos_index=bos_idx
                            )
        return None
