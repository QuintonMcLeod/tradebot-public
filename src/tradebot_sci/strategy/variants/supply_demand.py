from __future__ import annotations
import logging
import os
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
        
        # 1. Try Profile
        if "profile" in gates:
            max_daily = getattr(gates["profile"], "max_daily_trades", None) or 100
            
        # 2. Try Env (Override)
        env_limit = os.getenv("MAX_DAILY_TRADES")
        if env_limit:
            try:
                max_daily = int(env_limit)
            except ValueError:
                pass
        
        # KEY: Symbol + Date
        daily_key = f"{snapshot.symbol}_{current_date}"
        trades_today = GLOBAL_DAILY_COUNTS.get(daily_key, 0)

        # DEBUG PRINT
        # print(f"[DEBUG] {snapshot.symbol} {current_date} | Count: {trades_today} | Max: {max_daily}")
        
        if trades_today >= max_daily:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Daily Limit Reached ({trades_today}/{max_daily})")

        # Step 1: Find a Trend
        trend_dir = snapshot.trend_htf.direction
        
        # [ANTIGRAVITY] Relaxation: If HTF is neutral, check LTF. 
        # We need at least ONE timeframe to have a directional bias.
        if trend_dir == "neutral":
            trend_dir = snapshot.trend_ltf.direction
            
        if trend_dir not in {"long", "short"}:
            return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: No directional bias (HTF & LTF Neutral)")

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
                 # Calculate Trade Params
                atr = last_candle.high - last_candle.low # Fallback
                if hasattr(last_candle, 'atr') and last_candle.atr:
                    atr = last_candle.atr
                
                stop_loss = zone.bottom - (atr * 0.1)
                risk_dist = last_candle.close - stop_loss
                if risk_dist <= 0: risk_dist = atr
                take_profit = last_candle.close + (risk_dist * self.RR_TARGET)

                action = "enter_long"
                if open_position:
                        # Safety: Defer to profile setting for pyramid limit (default 4 for SND)
                        max_pyramid = 4
                        if "profile" in gates:
                            max_pyramid = getattr(gates["profile"], "max_pyramid_entries", 4)
                        
                        if open_position.get("pyramid_count", 0) >= max_pyramid:
                             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Max Pyramids reached ({max_pyramid})")
                        
                        # Only scale in if the new zone is HIGHER than entry (for long)
                        entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0)
                        if zone.bottom <= entry_price:
                             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Scale-in zone not higher than entry")
                        
                        action = "scale_in"
                        logger.info(f"[SND] PYRAMID OPPORTUNITY: {snapshot.symbol} @ {last_candle.close}")

                # [SAFEGUARD] Increment count (Global) - Only for initial entries
                if not open_position:
                    GLOBAL_DAILY_COUNTS[daily_key] = trades_today + 1
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action=action,
                    entry_price=last_candle.close, stop_loss=stop_loss, take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"SND: Demand Zone Tap & Break (BOS at idx {zone.bos_index})",
                    invalidation_conditions="Zone Break / Structure Invalidation",
                    management_instructions="SND Target or Trailing Stop",
                    urgency="medium",
                    notes=f"SND Zone: {zone.bottom:.4f}-{zone.top:.4f}" + (" (Pyramid)" if action == "scale_in" else "")
                )
            else:
                return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Tapping Demand, waiting for candle break")
        
        else: # supply
            # Supply: Price rallies into the zone
            is_tapping = last_candle.high >= zone.bottom and last_candle.close <= zone.top
            
            if is_tapping:
                # Calculate Trade Params
                atr = last_candle.high - last_candle.low # Fallback
                if hasattr(last_candle, 'atr') and last_candle.atr:
                    atr = last_candle.atr

                stop_loss = zone.top + (atr * 0.1)
                risk_dist = stop_loss - last_candle.close
                if risk_dist <= 0: risk_dist = atr
                take_profit = last_candle.close - (risk_dist * self.RR_TARGET)

                action = "enter_short"
                if open_position:
                        # Safety: Defer to profile setting for pyramid limit
                        max_pyramid = 4
                        if "profile" in gates:
                            max_pyramid = getattr(gates["profile"], "max_pyramid_entries", 4)
                        
                        if open_position.get("pyramid_count", 0) >= max_pyramid:
                             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Max Pyramids reached ({max_pyramid})")
                        
                        # Only scale in if the new zone is LOWER than entry (for short)
                        entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0)
                        if zone.top >= entry_price:
                             return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Scale-in zone not lower than entry")
                        
                        action = "scale_in"
                        logger.info(f"[SND] PYRAMID OPPORTUNITY: {snapshot.symbol} @ {last_candle.close}")

                # [SAFEGUARD] Increment count (Global) - Only for initial entries
                if not open_position:
                    GLOBAL_DAILY_COUNTS[daily_key] = trades_today + 1
                
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action=action,
                    entry_price=last_candle.close, stop_loss=stop_loss, take_profit=take_profit,
                    risk_per_trade_pct=self.get_risk_pct(),
                    structure_summary=f"SND: Supply Zone Tap & Break (BOS at idx {zone.bos_index})",
                    invalidation_conditions="Zone Break / Structure Invalidation",
                    management_instructions="SND Target or Trailing Stop",
                    urgency="medium",
                    notes=f"SND Zone: {zone.bottom:.4f}-{zone.top:.4f}" + (" (Pyramid)" if action == "scale_in" else "")
                )
            else:
                return stand_aside_decision(snapshot.symbol, snapshot.timeframe, "SND: Tapping Supply, waiting for candle break")

        return stand_aside_decision(snapshot.symbol, snapshot.timeframe, f"SND: Waiting for retest of {zone.side} zone")

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, current_capital: Optional[float] = None, **kwargs) -> Optional[AITradeDecision]:
        """
        Dynamic Risk Management:
        1. Move to Breakeven when price reaches 1R (Profit protection)
        2. peak-5% Trailing Stop (Capital preservation)
        """
        if not open_position:
            return None

        # [SAFETY] Managed by StrategyEngine via SafetyGuard (ATR Armor, etc)
        # We only implement SND-specific management here (Price Action / Structure)

        try:
            # [ANTIGRAVITY FIX] Resilient Field Access
            # Support both 'entry_price' (standard) and 'avg_price' (common in snapshots)
            entry_price = float(open_position.get("entry_price") or open_position.get("avg_price") or 0.0)
            if entry_price == 0:
                return None

            if not snapshot.candles:
                return None
            current_price = snapshot.candles[-1].close
            # Support both 'direction' and 'side'
            direction = open_position.get("direction") or open_position.get("side")
            if not direction:
                return None
                
            current_stop = float(open_position.get("stop_price") or 0.0)
            
            # Calculate Risk/Reward distance
            initial_risk = abs(entry_price - current_stop)
            if initial_risk == 0: return None
            
            profit_dist = (current_price - entry_price) if direction == "long" else (entry_price - current_price)
            r_multiple = profit_dist / initial_risk
        except Exception as e:
            logger.error(f"[SND-MGMT] Error evaluating active trade for {snapshot.symbol}: {e}")
            return None

        # 1. Breakeven Stop (Move to entry if 1R reached)
        is_breakeven = False
        if direction == "long":
            is_breakeven = current_stop >= (entry_price - 0.0001)
            if not is_breakeven and r_multiple >= 1.0:
                return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="long", phase="trend", action="hold",
                    stop_loss=entry_price, # Move to BE
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R reached)",
                    structure_summary="Management trigger",
                    invalidation_conditions="N/A", 
                    management_instructions="Update Stop Loss"
                )
        else: # short
            is_breakeven = current_stop <= (entry_price + 0.0001)
            if not is_breakeven and r_multiple >= 1.0:
                 return AITradeDecision(
                    symbol=snapshot.symbol, timeframe=snapshot.timeframe,
                    bias="short", phase="trend", action="hold",
                    stop_loss=entry_price, # Move to BE
                    notes="[MANAGEMENT] Moved stop to BREAKEVEN (1R reached)",
                    structure_summary="Management trigger",
                    invalidation_conditions="N/A",
                    management_instructions="Update Stop Loss"
                )

        # 2. Take Profit Check (Static Target)
        tp_target = float(open_position.get("take_profit") or 0.0)
        if tp_target > 0:
            if (direction == "long" and current_price >= tp_target) or \
               (direction == "short" and current_price <= tp_target):
                return close_position_decision(
                    snapshot.symbol, 
                    snapshot.timeframe, 
                    reason=f"SND: Take Profit Hit @ {tp_target:.4f}"
                )

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
