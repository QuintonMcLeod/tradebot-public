from __future__ import annotations
import logging
from datetime import time, datetime, timedelta
from typing import Optional, Tuple, List
from zoneinfo import ZoneInfo
from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy

logger = logging.getLogger(__name__)

class ORBStrategy(BaseStrategy):
    """
    NY Session Opening Range Breakout (ORB) Strategy.
    
    SESSION_PROFILE: us_open
    """
    SESSION_PROFILE = "orb_breakout:us_open"
    """
    Logic:
    1. Define Range (09:30 - 09:45 ET).
    2. Wait for BREAK (Candle Close outside Range).
    3. Wait for RETEST (Price touches Range Level).
    4. Wait for FLAG (Consolidation/Inside Bar at Level).
    5. ENTRY on Break of Flag.
    """
    
    def __init__(self, range_start="09:30", duration_minutes=15, **kwargs):
        super().__init__("ORB Breakout")
        self.range_start = time.fromisoformat(range_start)
        self.duration_minutes = int(duration_minutes)
        # I store state implicitly by scanning the day's candles
        # each time to find the ORB range and look for breakout ticks.

    def _get_ny_time(self, dt: datetime) -> datetime:
        # Convert to NY time for session logic
        if dt.tzinfo is None:
            # Assume UTC if naive (or system time) - ideally I rely on snapshot timestamps being aware
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/New_York"))

    def _get_orb_range(self, snapshot: MarketSnapshot) -> Optional[Tuple[float, float, List[Candle]]]:
        # Filter for today's NY Session candles
        if not snapshot.candles:
            return None
            
        latest_ny = self._get_ny_time(snapshot.candles[-1].timestamp)
        today_date = latest_ny.date()
        
        range_end_time = (datetime.combine(today_date, self.range_start) + timedelta(minutes=self.duration_minutes)).time()
        
        range_candles = []
        for c in snapshot.candles:
            c_ny = self._get_ny_time(c.timestamp)
            if c_ny.date() == today_date:
                t = c_ny.time()
                if t >= self.range_start and t < range_end_time:
                    range_candles.append(c)
        
        if not range_candles:
            return None
            
        # Ensure we have the full 15 minutes (approx) to define range
        # If current time is BEFORE range_end, we don't have a range yet
        if latest_ny.time() < range_end_time:
            return None

        # Calculate High/Low
        high = max(c.high for c in range_candles)
        low = min(c.low for c in range_candles)
        
        return low, high, range_candles

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        orb_data = self._get_orb_range(snapshot)
        if not orb_data:
            return None
            
        low_lvl, high_lvl, range_candles = orb_data
        
        # I need to analyze candles *after* the range to find the pattern
        # Sequence: Break -> Retest -> Flag -> Trigger
        
        # 1. Isolate post-range candles
        latest_c_ny = self._get_ny_time(snapshot.candles[-1].timestamp)
        # [GATING] Session timing is handled by the Global Scheduler.
        # We no longer need the hardcoded 13:00 cutoff here.
            
        last_range_ts = range_candles[-1].timestamp
        post_candles = [c for c in snapshot.candles if c.timestamp > last_range_ts]
        
        if len(post_candles) < 3: # Need at least a few candles for Break + Retest + Flag
            return None
            
        # [TREND GUIDANCE] Follow the trend direction from HTF analysis
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()

        # STATE MACHINE SIMULATION
        # I simulate the state by iterating through post-candles
        
        state = "RANGE" # Start state
        bias = None # 'bull' or 'bear'
        breakout_candle = None
        retest_found = False
        flag_candle = None
        trigger_candle_idx = None  # index of the bar that broke the flag
        
        for c in post_candles:
            if state == "RANGE":
                # Check for Breakout Close (only in trend direction)
                if htf_dir in ("long", "neutral") and c.close > high_lvl:
                    state = "BROKEN"
                    bias = "bull"
                    breakout_candle = c
                elif htf_dir in ("short", "neutral") and c.close < low_lvl:
                    state = "BROKEN"
                    bias = "bear"
                    breakout_candle = c
            
            elif state == "BROKEN":
                # Look for Retest (Touching the level)
                if bias == "bull":
                    # Retest: Low touches High Level (or dips below it slightly but holds structure?)
                    # Strict: Low <= High Level
                    if c.low <= (high_lvl * 1.0005): # Tolerance 0.05%
                        state = "RETESTED"
                        retest_found = True
                elif bias == "bear":
                    # Retest: High >= Low Level
                    if c.high >= (low_lvl * 0.9995):
                        state = "RETESTED"
                        retest_found = True
                        
            elif state == "RETESTED":
                # Look for Flag (Consolidation) CLOSE to the level
                # Definition: Small Body (Body < 50% of Candle Range) OR Inside Bar
                # AND it must be near the level (High/Low closest to level)
                
                body_size = abs(c.close - c.open)
                candle_range = c.high - c.low
                is_small_body = (body_size < (candle_range * 0.5)) if candle_range > 0 else True
                
                # Check proximity
                is_near = False
                if bias == "bull":
                     # Support check: Low is near High Level
                     dist = abs(c.low - high_lvl)
                     if dist < (high_lvl * 0.002): # 0.2% proximity
                         is_near = True
                else: # bear
                     dist = abs(c.high - low_lvl)
                     if dist < (low_lvl * 0.002):
                         is_near = True
                
                if is_small_body and is_near:
                    state = "FLAGGED"
                    flag_candle = c
                    # I only care about the *latest* valid flag if I haven't triggered yet
                    # Actually, if we find a flag, the NEXT candle is our trigger opportunity
                    # So we break loop? No, we need to see if we already missed the trigger.
                    # Let's assume the CURRENT candle is the one potentially breaking the flag.
                    if c == post_candles[-1]:
                        # The LAST candle IS the flag. I wait for the NEXT tick to break it.
                        return None # Signal requires BREAK of flag.
                
            elif state == "FLAGGED":
                # Check for Trigger (Break of Flag)
                c_idx = post_candles.index(c)
                
                if bias == "bull":
                    if c.close > flag_candle.high:
                        trigger_candle_idx = c_idx
                        # Allow entry within 3 bars of the flag break
                        bars_since = len(post_candles) - 1 - c_idx
                        if bars_since <= 3:
                            return self._build_decision(snapshot, "long", snapshot.candles[-1].close, flag_candle.low, high_lvl)
                        else:
                            # Missed this trigger — reset to look for new patterns
                            state = "RETESTED"
                            flag_candle = None
                elif bias == "bear":
                    if c.close < flag_candle.low:
                        trigger_candle_idx = c_idx
                        bars_since = len(post_candles) - 1 - c_idx
                        if bars_since <= 3:
                            return self._build_decision(snapshot, "short", snapshot.candles[-1].close, flag_candle.high, low_lvl)
                        else:
                            state = "RETESTED"
                            flag_candle = None
                            
        # End of Loop
        return None

    def _build_decision(self, snapshot: MarketSnapshot, direction: str, entry: float, stop: float, level: float) -> AITradeDecision:
        risk = abs(entry - stop)
        if risk == 0: risk = entry * 0.001 # Safety
        
        target = entry + (risk * 2.0) if direction == "long" else entry - (risk * 2.0)
        
        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            action=f"enter_{direction}",
            bias=direction,
            phase="continuation",
            entry_price=entry,
            stop_loss=stop,
            take_profit=None,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=f"ORB {direction.title()} (Flag Break @ {entry:.2f})",
            invalidation_conditions="Close back inside ORB range",
            management_instructions="Target 2R, Trail Stop below Flag",
            notes="Strategies: ORB Break & Retest",
            urgency="high"
        )

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        # Standard exit logic + Trailing
        # ORB moves fast, maybe trail 1R?
        return None # Delegate to SafetyGuard/Runner
